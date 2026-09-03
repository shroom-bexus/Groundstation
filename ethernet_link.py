"""UDP communication with the SHROOM flight computer."""

import secrets
import socket
import time
from pathlib import Path

from bandwidth import estimated_packet_bits
from network_config import network_interface
from telemetry import parse_telemetry


TEENSY_IP = "172.16.18.131"
TEENSY_PORT = 5000
NETWORK_INTERFACE = network_interface()

RECEIVE_TIMEOUT = 0.1
ONLINE_TIMEOUT = 3.5
REGISTRATION_INTERVAL = 30.0
OFFLINE_REGISTRATION_INTERVAL = 5.0
ACK_TIMEOUT = 3.0
MAX_SEND_ATTEMPTS = 3
REOPEN_INTERVAL = 2.0
RATE_UPDATE_INTERVAL = 1.0

# At 1 kbit/s one packet per second leaves margin for occasional ARP traffic.
ONE_KBIT_SAFE_INTERVAL = 1.05
MIN_PACKET_INTERVAL = 0.21


class _UplinkLimiter:
    """Pace complete UDP packets using their estimated Ethernet wire size."""

    def __init__(self, bandwidth_settings):
        self._settings = bandwidth_settings
        self._next_send = time.monotonic()

    def wait_for(self, payload_bytes):
        uplink_limit, _ = self._settings.get_limits()
        if uplink_limit == 0.0:
            return

        packet_bits = estimated_packet_bits(payload_bytes)
        rate_bits_s = uplink_limit * 1000.0

        # The BEXUS burst guideline permits 0.8 seconds of the configured
        # bitrate inside one 200 ms interval.
        if packet_bits > rate_bits_s * 0.8:
            raise ValueError(
                "Command datagram is too large for the uplink burst limit"
            )

        interval = max(packet_bits / rate_bits_s, MIN_PACKET_INTERVAL)
        if uplink_limit <= 1.0:
            interval = max(interval, ONE_KBIT_SAFE_INTERVAL)

        now = time.monotonic()
        if now < self._next_send:
            time.sleep(self._next_send - now)
            now = time.monotonic()

        self._next_send = now + interval


class _RateMeter:
    """Measure all traffic on the dedicated Ethernet interface."""

    def __init__(self, on_rates, interface=NETWORK_INTERFACE):
        self._on_rates = on_rates
        self._window_start = time.monotonic()
        self._upload_bytes = 0
        self._download_bytes = 0
        self._statistics_path = (
            Path("/sys/class/net") / interface / "statistics"
        )
        self._previous_counters = self._read_interface_counters()

    def _read_interface_counters(self):
        try:
            upload = int((self._statistics_path / "tx_bytes").read_text())
            download = int((self._statistics_path / "rx_bytes").read_text())
            return upload, download
        except (OSError, ValueError):
            return None

    def add_upload(self, byte_count):
        self._upload_bytes += byte_count

    def add_download(self, byte_count):
        self._download_bytes += byte_count

    def update(self):
        now = time.monotonic()
        elapsed = now - self._window_start
        if elapsed < RATE_UPDATE_INTERVAL:
            return

        counters = self._read_interface_counters()
        if counters is not None and self._previous_counters is not None:
            upload_bytes = max(0, counters[0] - self._previous_counters[0])
            download_bytes = max(0, counters[1] - self._previous_counters[1])
        else:
            # Fallback excludes headers but works on non-Linux systems.
            upload_bytes = self._upload_bytes
            download_bytes = self._download_bytes

        self._on_rates(
            upload_bytes * 8.0 / elapsed / 1000.0,
            download_bytes * 8.0 / elapsed / 1000.0
        )
        self._window_start = now
        self._upload_bytes = 0
        self._download_bytes = 0
        self._previous_counters = counters


def _numbered_command(command_id, command):
    """Insert a command ID into the existing CMD,<name>,... format."""

    if not command.startswith("CMD,"):
        raise ValueError("Invalid command format")
    return f"CMD,{command_id},{command[4:]}"


def _send_pending(client, pending, limiter, rate_meter):
    limiter.wait_for(len(pending["payload"]))
    bytes_sent = client.send(pending["payload"])
    if bytes_sent != len(pending["payload"]):
        raise OSError("Incomplete UDP datagram")

    rate_meter.add_upload(bytes_sent)
    pending["attempts"] += 1
    pending["sent_at"] = time.monotonic()


def _reply(line):
    """Return (type, command_id, detail) for an ACK, NACK, or WARN line."""

    parts = line.split(",", 2)
    if len(parts) != 3 or parts[0] not in ("ACK", "NACK", "WARN"):
        return None
    try:
        return parts[0], int(parts[1]), parts[2]
    except ValueError:
        return None


def _report_sequence(sequence, previous_sequence, on_log):
    """Report missing, duplicate, or restarted telemetry sequences."""

    if previous_sequence is None:
        return sequence

    expected = (previous_sequence + 1) & 0xFFFFFFFF
    if sequence == previous_sequence:
        on_log(f"Duplicate telemetry datagram: {sequence}")
        return previous_sequence
    if sequence == expected:
        return sequence

    missing = (sequence - expected) & 0xFFFFFFFF
    if missing < 0x80000000:
        on_log(f"Lost telemetry datagrams: {missing}")
    else:
        on_log(f"Telemetry sequence restarted at {sequence}")
    return sequence


def ethernet_link_run(
    command_queue,
    bandwidth_settings,
    on_connection,
    on_rates,
    on_telemetry,
    on_log
):
    """Run the UDP endpoint and reopen its socket after network errors."""

    on_connection(False)

    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.connect((TEENSY_IP, TEENSY_PORT))
                client.settimeout(RECEIVE_TIMEOUT)
                on_log(f"UDP endpoint ready for {TEENSY_IP}:{TEENSY_PORT}.")

                _handle_udp(
                    client,
                    command_queue,
                    bandwidth_settings,
                    on_connection,
                    on_rates,
                    on_telemetry,
                    on_log
                )
        except OSError as error:
            on_connection(False)
            on_rates(0.0, 0.0)
            on_log(f"Ethernet error: {error}")
            time.sleep(REOPEN_INTERVAL)


def _handle_udp(
    client,
    command_queue,
    bandwidth_settings,
    on_connection,
    on_rates,
    on_telemetry,
    on_log
):
    limiter = _UplinkLimiter(bandwidth_settings)
    rate_meter = _RateMeter(on_rates)

    session_id = secrets.token_hex(4)
    next_command_id = 1
    pending = None
    previous_sequence = None
    last_received = None
    connected = False
    registered = False
    next_registration = 0.0

    while True:
        now = time.monotonic()
        rate_meter.update()

        if connected and now - last_received > ONLINE_TIMEOUT:
            connected = False
            on_connection(False)

        if pending is not None and now - pending["sent_at"] >= ACK_TIMEOUT:
            if pending["attempts"] < MAX_SEND_ATTEMPTS:
                _send_pending(client, pending, limiter, rate_meter)
            else:
                if not pending["internal"]:
                    on_log(
                        f"No response for command {pending['command_id']}"
                    )
                if pending["kind"] in ("hello", "registration"):
                    registered = False
                    next_registration = now + OFFLINE_REGISTRATION_INTERVAL
                pending = None

        if pending is None:
            command = None
            internal = False
            kind = "command"

            if not registered and now >= next_registration:
                pending = {
                    "command_id": None,
                    "detail": "HELLO",
                    "payload": f"HELLO,{session_id}\n".encode("utf-8"),
                    "attempts": 0,
                    "sent_at": 0.0,
                    "internal": True,
                    "kind": "hello",
                }
                next_registration = now + OFFLINE_REGISTRATION_INTERVAL
            elif registered and not command_queue.empty():
                command = command_queue.get_nowait()
            elif registered and now >= next_registration:
                _, downlink_limit = bandwidth_settings.get_limits()
                command = (
                    f"CMD,SET_DL_LIMIT,{downlink_limit:.6g}"
                )
                internal = True
                kind = "registration"

            if command is not None:
                command_id = next_command_id
                next_command_id = (next_command_id + 1) & 0xFFFF
                text = _numbered_command(command_id, command)
                pending = {
                    "command_id": command_id,
                    "detail": command[4:],
                    "payload": f"{text}\n".encode("utf-8"),
                    "attempts": 0,
                    "sent_at": 0.0,
                    "internal": internal,
                    "kind": kind,
                }

            if pending is not None and pending["attempts"] == 0:
                try:
                    _send_pending(client, pending, limiter, rate_meter)
                    if not pending["internal"]:
                        on_log(
                            f"Sent: CMD,{pending['command_id']},"
                            f"{pending['detail']}"
                        )
                except ValueError as error:
                    on_log(str(error))
                    pending = None

                if kind == "registration":
                    next_registration = (
                        time.monotonic() + REGISTRATION_INTERVAL
                    )

        try:
            data = client.recv(2048)
        except socket.timeout:
            continue

        if not data:
            continue

        rate_meter.add_download(len(data))
        last_received = time.monotonic()
        if not connected:
            connected = True
            on_connection(True)
            next_registration = last_received + REGISTRATION_INTERVAL

        lines = data.decode("utf-8", errors="replace").splitlines()
        if not lines:
            continue

        if lines[0] == f"ACK_SESSION,{session_id}":
            if pending is not None and pending["kind"] == "hello":
                registered = True
                pending = None
                next_registration = last_received
            continue

        response = _reply(lines[0])
        if response is not None:
            response_type, response_id, detail = response
            if pending is None or response_id != pending["command_id"]:
                on_log(f"Late command response ignored: {lines[0]}")
                continue

            if not pending["internal"]:
                labels = {
                    "ACK": "Command acknowledged",
                    "NACK": "Command rejected",
                    "WARN": "Warning",
                }
                on_log(f"{labels[response_type]}: {detail}")
            pending = None
            continue

        if not lines[0].startswith("SEQ,"):
            on_log(f"Unknown UDP datagram: {lines[0]}")
            continue

        try:
            sequence = int(lines[0][4:])
        except ValueError:
            on_log(f"Invalid telemetry sequence: {lines[0]}")
            continue

        previous_sequence = _report_sequence(
            sequence,
            previous_sequence,
            on_log
        )

        for line in lines[1:]:
            telemetry = parse_telemetry(line)
            if telemetry is None:
                on_log(f"Unknown message: {line}")
            else:
                on_telemetry(telemetry)
