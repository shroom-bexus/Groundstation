"""
    ███████╗██╗  ██╗██████╗  ██████╗  ██████╗ ███╗   ███╗
    ██╔════╝██║  ██║██╔══██╗██╔═══██╗██╔═══██╗████╗ ████║
    ███████╗███████║██████╔╝██║   ██║██║   ██║██╔████╔██║
    ╚════██║██╔══██║██╔══██╗██║   ██║██║   ██║██║╚██╔╝██║
    ███████║██║  ██║██║  ██║╚██████╔╝╚██████╔╝██║ ╚═╝ ██║
    ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝     ╚═╝

Stratospheric High-Altitude Radiation Observation of Organismic Mycology

ethernet_link.py
Ethernet communication with the SHROOM flight computer.

Handles:
- TCP connection to the Teensy
- Automatic reconnect after connection loss
- Heartbeat for connection monitoring
- Line-based message reception
- Ground station command transmission
"""

import socket
import time
from pathlib import Path

from bandwidth import estimated_packet_bits, TOKEN_CAPACITY_SECONDS
from telemetry import parse_telemetry


# ============================================================================
# Ethernet configuration
# ============================================================================

TEENSY_IP = "172.16.18.131"
TEENSY_PORT = 5000
NETWORK_INTERFACE = "enp0s31f6"


# ============================================================================
# Ethernet timing
# ============================================================================

CONNECT_TIMEOUT = 6.0
RECEIVE_TIMEOUT = 0.5

HEARTBEAT_INTERVAL = 10.0
ACK_TIMEOUT = 6.0

RECONNECT_INTERVAL = 5.0

RATE_UPDATE_INTERVAL = 1.0


class _UplinkLimiter:
    """Limit estimated wire traffic with a continuously refilled budget."""

    def __init__(self, bandwidth_settings):
        self._settings = bandwidth_settings
        self._last_update = time.monotonic()
        self._tokens_bits = 0.0
        self._capacity_bits = 0.0
        self._last_limit = None

    def wait_for(self, payload_bytes):
        packet_bits = estimated_packet_bits(payload_bytes)

        while True:
            uplink_limit, _ = self._settings.get_limits()
            now = time.monotonic()

            if uplink_limit != self._last_limit:
                self._last_limit = uplink_limit
                rate_bits_s = uplink_limit * 1000.0
                self._capacity_bits = (
                    rate_bits_s * TOKEN_CAPACITY_SECONDS
                )
                self._tokens_bits = self._capacity_bits
                self._last_update = now

            if uplink_limit == 0.0:
                return

            rate_bits_s = uplink_limit * 1000.0
            elapsed = now - self._last_update
            self._last_update = now
            self._tokens_bits = min(
                self._capacity_bits,
                self._tokens_bits + elapsed * rate_bits_s
            )

            if packet_bits > self._capacity_bits:
                raise ValueError(
                    "Uplink limit is too low for this command"
                )

            if packet_bits <= self._tokens_bits:
                self._tokens_bits -= packet_bits
                return

            wait_seconds = (
                packet_bits - self._tokens_bits
            ) / rate_bits_s
            time.sleep(wait_seconds)


class _RateMeter:
    """Measure the dedicated Ethernet interface once per second."""

    def __init__(self, on_rates, interface=NETWORK_INTERFACE):
        self._on_rates = on_rates
        self._window_start = time.monotonic()
        self._upload_bytes = 0
        self._download_bytes = 0
        self._statistics_path = Path(
            "/sys/class/net"
        ) / interface / "statistics"
        self._previous_counters = self._read_interface_counters()

    def _read_interface_counters(self):
        try:
            upload = int(
                (self._statistics_path / "tx_bytes").read_text()
            )
            download = int(
                (self._statistics_path / "rx_bytes").read_text()
            )
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
            # This fallback excludes protocol headers but keeps the GS usable
            # on systems without Linux interface counters.
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


def _send_line(client, line, limiter, rate_meter):
    payload = f"{line}\n".encode("utf-8")
    limiter.wait_for(len(payload))
    client.sendall(payload)
    rate_meter.add_upload(len(payload))


# ============================================================================
# Connection handling
# ============================================================================

def ethernet_link_run(
    command_queue,
    bandwidth_settings,
    on_connection,
    on_rates,
    on_telemetry,
    on_log
):
    """
    Keep the Ethernet connection to the Teensy running.

    If the connection is lost, reconnect automatically.
    """

    while True:
        try:
            on_log(
                f"Connecting to {TEENSY_IP}:{TEENSY_PORT}..."
            )

            with socket.create_connection(
                    (TEENSY_IP, TEENSY_PORT),
                    timeout=CONNECT_TIMEOUT
            ) as client:

                on_connection(True)
                on_log("Connected.")

                try:
                    _handle_connection(
                        client,
                        command_queue,
                        bandwidth_settings,
                        on_rates,
                        on_telemetry,
                        on_log
                    )

                finally:
                    on_connection(False)
                    on_rates(0.0, 0.0)

        except (ConnectionError, OSError) as error:
            on_connection(False)

            on_log(
                f"Connection lost: {error}"
            )

            time.sleep(
                RECONNECT_INTERVAL
            )


# ============================================================================
# Connected state
# ============================================================================

def _handle_connection(
    client,
    command_queue,
    bandwidth_settings,
    on_rates,
    on_telemetry,
    on_log
):
    """
    Handle communication while a TCP connection is active.
    """

    client.settimeout(
        RECEIVE_TIMEOUT
    )

    receive_buffer = ""

    next_heartbeat = 0.0

    waiting_for_ack = False
    ack_start_time = 0.0

    limiter = _UplinkLimiter(bandwidth_settings)
    rate_meter = _RateMeter(on_rates)

    # Reapply the saved Teensy-side limit after every reconnect or reset.
    _, downlink_limit = bandwidth_settings.get_limits()
    _send_line(
        client,
        f"CMD,SET_DOWNLINK_LIMIT,{downlink_limit:.6g}",
        limiter,
        rate_meter
    )


    while True:
        current_time = time.monotonic()


        # --------------------------------------------------------------------
        # Ground station commands
        # --------------------------------------------------------------------

        while not command_queue.empty():
            command = command_queue.get_nowait()

            _send_line(
                client,
                command,
                limiter,
                rate_meter
            )

            on_log(
                f"Sent: {command}"
            )


        # --------------------------------------------------------------------
        # Heartbeat
        # --------------------------------------------------------------------

        if (
            not waiting_for_ack and
            current_time >= next_heartbeat
        ):
            _send_line(
                client,
                "CMD,PING",
                limiter,
                rate_meter
            )

            waiting_for_ack = True
            ack_start_time = current_time


        if (
            waiting_for_ack and
            current_time - ack_start_time >= ACK_TIMEOUT
        ):
            raise ConnectionError(
                "No ACK received"
            )


        # --------------------------------------------------------------------
        # Receive data
        # --------------------------------------------------------------------

        try:
            data = client.recv(4096)

        except socket.timeout:
            rate_meter.update()
            continue


        if not data:
            raise ConnectionError(
                "Connection closed by Teensy"
            )

        rate_meter.add_download(len(data))
        rate_meter.update()


        receive_buffer += data.decode(
            "utf-8",
            errors="replace"
        )


        # TCP is a byte stream.
        # Process only complete newline-terminated messages.
        while "\n" in receive_buffer:
            line, receive_buffer = receive_buffer.split(
                "\n",
                1
            )

            line = line.rstrip("\r")


            if not line:
                continue


            # ----------------------------------------------------------------
            # Heartbeat response
            # ----------------------------------------------------------------

            if line == "ACK,PING":
                waiting_for_ack = False

                next_heartbeat = (
                    time.monotonic() +
                    HEARTBEAT_INTERVAL
                )

                continue


            # ----------------------------------------------------------------
            # Command acknowledgement
            # ----------------------------------------------------------------

            if line.startswith("ACK,"):
                on_log(
                    f"Command acknowledged: {line[4:]}"
                )

                continue


            if line.startswith("NACK,"):
                on_log(
                    f"Command rejected: {line[5:]}"
                )

                continue

            if line.startswith("WARN,"):
                on_log(
                    f"Warning: {line[5:]}"
                )
                continue


            # ----------------------------------------------------------------
            # Telemetry
            # ----------------------------------------------------------------

            telemetry = parse_telemetry(
                line
            )


            if telemetry is None:
                on_log(
                    f"Unknown message: {line}"
                )

                continue


            on_telemetry(
                telemetry
            )
