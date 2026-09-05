"""Local browser dashboard for SHROOM live telemetry.

The dashboard deliberately reuses the existing UDP link and telemetry parser.
It is an alternative view of the same Ground Station data, not a second
network implementation.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import queue
import random
import threading
import time
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bandwidth import BandwidthSettings
from ethernet_link import ethernet_link_run


ASSET_DIRECTORY = Path(__file__).with_name("dashboard_assets")
MAX_POINTS_PER_SERIES = 1800


class DashboardState:
    """Thread-safe state shared by the UDP and HTTP threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._started_at = time.monotonic()
        self._revision = 0
        self._connected = False
        self._upload_kbit_s = 0.0
        self._download_kbit_s = 0.0
        self._last_fc_time_s = None
        self._latest = {}
        self._health = {}
        self._series = {}
        self._airdos_counts = {}
        self._logs = deque(maxlen=80)

    def _elapsed_s(self):
        return time.monotonic() - self._started_at

    def _append(self, name, value, time_s=None):
        if value is None or not math.isfinite(float(value)):
            return
        points = self._series.setdefault(
            name,
            deque(maxlen=MAX_POINTS_PER_SERIES),
        )
        points.append([
            round(self._elapsed_s() if time_s is None else time_s, 3),
            round(float(value), 6),
        ])

    def set_connection(self, connected):
        with self._lock:
            self._connected = bool(connected)
            if not connected:
                self._upload_kbit_s = 0.0
                self._download_kbit_s = 0.0
            self._revision += 1

    def set_rates(self, upload_kbit_s, download_kbit_s):
        with self._lock:
            self._upload_kbit_s = float(upload_kbit_s)
            self._download_kbit_s = float(download_kbit_s)
            self._append("uplink", upload_kbit_s)
            self._append("downlink", download_kbit_s)
            self._revision += 1

    def add_log(self, message):
        with self._lock:
            self._logs.append({
                "time_s": round(self._elapsed_s(), 1),
                "message": str(message),
            })
            self._revision += 1

    def add_telemetry(self, telemetry):
        telemetry_type = telemetry["type"]
        time_ms = telemetry.get("time_ms")
        time_s = None if time_ms is None else time_ms / 1000.0

        with self._lock:
            if time_s is not None:
                if (
                    self._last_fc_time_s is not None
                    and time_s + 5.0 < self._last_fc_time_s
                ):
                    # A Teensy reset restarts millis(). Preserve the local link
                    # history, but begin new sensor traces at the new epoch.
                    self._series = {
                        name: points
                        for name, points in self._series.items()
                        if name in ("uplink", "downlink")
                    }
                    self._logs.append({
                        "time_s": round(self._elapsed_s(), 1),
                        "message": "Flight computer time restarted; plots reset",
                    })
                    self._last_fc_time_s = time_s
                elif (
                    self._last_fc_time_s is None
                    or time_s > self._last_fc_time_s
                ):
                    self._last_fc_time_s = time_s

            if telemetry_type == "THERMAL":
                self._latest["thermal"] = telemetry
                self._append(
                    "thermal_temperature",
                    telemetry["temperature_k"],
                    time_s,
                )
                self._append("thermal_target", telemetry["target_k"], time_s)
                self._append(
                    "thermal_output",
                    telemetry["output_percent"],
                    time_s,
                )

            elif telemetry_type == "PADS":
                self._latest["pads"] = telemetry
                self._append("pads_temperature", telemetry["temperature_k"], time_s)
                self._append("pressure", telemetry["pressure_pa"], time_s)

            elif telemetry_type == "HIDS":
                self._latest["hids"] = telemetry
                self._append("hids_temperature", telemetry["temperature_k"], time_s)
                self._append("humidity", telemetry["humidity_percent"], time_s)

            elif telemetry_type == "MAX31865":
                sensors = self._latest.setdefault("max31865", {})
                sensors[str(telemetry["sensor"])] = telemetry
                self._append(
                    f"pt1000_{telemetry['sensor']}",
                    telemetry["temperature_k"],
                    time_s,
                )

            elif telemetry_type == "HEATERS":
                self._latest["heaters"] = telemetry
                for sensor in range(1, 5):
                    self._append(
                        f"heater_{sensor}",
                        telemetry[f"heater_{sensor}"],
                        time_s,
                    )

            elif telemetry_type == "PID":
                self._latest["pid"] = telemetry

            elif telemetry_type == "DOWNLINK":
                self._latest["downlink"] = telemetry

            elif telemetry_type == "HEALTH":
                subsystem = telemetry["subsystem"]
                if subsystem in ("MAX31865", "AIRDOS"):
                    key = f"{subsystem}_{telemetry['sensor']}"
                else:
                    key = subsystem
                self._health[key] = telemetry

            elif telemetry_type == "AIRDOS":
                sensor = str(telemetry["sensor"])
                self._airdos_counts[sensor] = self._airdos_counts.get(sensor, 0) + 1
                self._latest.setdefault("airdos", {})[sensor] = {
                    "time_ms": telemetry["time_ms"],
                    "data": telemetry["data"][-160:],
                }

            elif telemetry_type == "LOG":
                self._logs.append({
                    "time_s": round(self._elapsed_s(), 1),
                    "message": (
                        f"FC [{telemetry['level']}] {telemetry['message']}"
                    ),
                })

            self._revision += 1

    def snapshot(self, bandwidth):
        with self._lock:
            uplink_limit, downlink_limit = bandwidth.get_limits()
            return {
                "revision": self._revision,
                "elapsed_s": round(self._elapsed_s(), 1),
                "connected": self._connected,
                "rates": {
                    "upload_kbit_s": round(self._upload_kbit_s, 3),
                    "download_kbit_s": round(self._download_kbit_s, 3),
                    "upload_limit_kbit_s": uplink_limit,
                    "download_limit_kbit_s": downlink_limit,
                },
                "latest": copy.deepcopy(self._latest),
                "health": copy.deepcopy(self._health),
                "series": {
                    name: list(points)
                    for name, points in self._series.items()
                },
                "airdos_counts": dict(self._airdos_counts),
                "logs": list(self._logs),
            }


def _demo_run(state):
    """Generate plausible changing data for layout work without hardware."""

    state.set_connection(True)
    state.add_log("Demo mode active — no flight computer connection")
    started_at = time.monotonic()
    next_slow = 0.0

    while True:
        elapsed = time.monotonic() - started_at
        temperature = 292.7 + math.sin(elapsed / 16.0) * 0.55
        target = 293.15
        output = 31.0 + math.sin(elapsed / 8.0) * 8.0

        state.add_telemetry({
            "type": "THERMAL",
            "time_ms": int(elapsed * 1000),
            "controller_enabled": True,
            "target_k": target,
            "temperature_k": temperature,
            "output_percent": output,
        })
        state.add_telemetry({
            "type": "HEATERS",
            "time_ms": int(elapsed * 1000),
            "heater_1": output,
            "heater_2": output,
            "heater_3": output,
            "heater_4": output,
        })
        state.set_rates(
            0.58 + random.uniform(-0.05, 0.05),
            5.4 + random.uniform(-0.35, 0.35),
        )

        if elapsed >= next_slow:
            state.add_telemetry({
                "type": "PADS",
                "time_ms": int(elapsed * 1000),
                "temperature_k": 289.3 + math.sin(elapsed / 25.0) * 0.8,
                "pressure_pa": 74200 - elapsed * 3.2 + random.uniform(-40, 40),
            })
            state.add_telemetry({
                "type": "HIDS",
                "time_ms": int(elapsed * 1000),
                "temperature_k": 290.1 + math.sin(elapsed / 28.0) * 0.7,
                "humidity_percent": 41.0 + math.sin(elapsed / 20.0) * 2.5,
            })

            for sensor in range(1, 10):
                state.add_telemetry({
                    "type": "MAX31865",
                    "time_ms": int(elapsed * 1000),
                    "sensor": sensor,
                    "temperature_k": (
                        temperature + (sensor - 5) * 0.17
                        + random.uniform(-0.035, 0.035)
                    ),
                })

            state.add_telemetry({
                "type": "DOWNLINK",
                "time_ms": int(elapsed * 1000),
                "limit_kbit_s": 8.0,
                "airdos_level": 3,
                "airdos_selected_count": 9,
                "drop_count": 0,
                "suppressed_count": int(elapsed / 31),
                "system_queue": random.randint(0, 3),
                "airdos_queue": random.randint(0, 2),
            })

            for subsystem in ("SD", "PADS", "HIDS", "ISDS"):
                state.add_telemetry({
                    "type": "HEALTH",
                    "time_ms": int(elapsed * 1000),
                    "subsystem": subsystem,
                    "state": "OK",
                    "error_count": 0,
                })

            for sensor in (1, 2):
                state.add_telemetry({
                    "type": "HEALTH",
                    "time_ms": int(elapsed * 1000),
                    "subsystem": "AIRDOS",
                    "sensor": sensor,
                    "state": "OK",
                    "last_message_age_ms": random.randint(20, 380),
                    "overflow_count": 0,
                })
                for _ in range(random.randint(2, 5)):
                    state.add_telemetry({
                        "type": "AIRDOS",
                        "time_ms": int(elapsed * 1000),
                        "sensor": sensor,
                        "data": "$E,03,18,128,0042,0017,0009",
                    })

            next_slow = elapsed + 2.0

        time.sleep(1.0)


def _handler_class(state, bandwidth):
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/state":
                body = json.dumps(
                    state.snapshot(bandwidth),
                    separators=(",", ":"),
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            asset_name = "index.html" if self.path in ("/", "/index.html") else self.path[1:]
            if asset_name not in ("index.html", "dashboard.css", "dashboard.js"):
                self.send_error(404)
                return

            path = ASSET_DIRECTORY / asset_name
            try:
                body = path.read_bytes()
            except OSError:
                self.send_error(404)
                return

            content_types = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
            }
            self.send_response(200)
            self.send_header("Content-Type", content_types[path.suffix])
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    return DashboardHandler


def main():
    parser = argparse.ArgumentParser(description="SHROOM graphical dashboard")
    parser.add_argument("--demo", action="store_true", help="use generated demo data")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    state = DashboardState()
    bandwidth = BandwidthSettings()

    if args.demo:
        worker = threading.Thread(target=_demo_run, args=(state,), daemon=True)
    else:
        command_queue = queue.Queue()
        worker = threading.Thread(
            target=ethernet_link_run,
            args=(
                command_queue,
                bandwidth,
                state.set_connection,
                state.set_rates,
                state.add_telemetry,
                lambda message: state.add_log(f"GS {message}"),
            ),
            daemon=True,
        )
    worker.start()

    address = f"http://127.0.0.1:{args.port}/"
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        _handler_class(state, bandwidth),
    )
    print(f"SHROOM dashboard: {address}")
    if args.demo:
        print("Demo data active. Press Ctrl+C to stop.")
    else:
        print("Live UDP data active. Press Ctrl+C to stop.")

    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(address,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
