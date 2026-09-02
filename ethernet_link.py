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

from telemetry import parse_telemetry


# ============================================================================
# Ethernet configuration
# ============================================================================

TEENSY_IP = "172.16.18.131"
TEENSY_PORT = 5000


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
    """Limit sent TCP payload without delaying the Teensy flight loop."""

    def __init__(self, bandwidth_settings):
        self._settings = bandwidth_settings
        self._window_start = time.monotonic()
        self._window_bytes = 0
        self._last_limit = None

    def wait_for(self, byte_count):
        while True:
            uplink_limit, _ = self._settings.get_limits()
            now = time.monotonic()

            if uplink_limit != self._last_limit or now - self._window_start >= 1.0:
                self._last_limit = uplink_limit
                self._window_start = now
                self._window_bytes = 0

            if uplink_limit == 0.0:
                return

            maximum_bytes = int(uplink_limit * 125.0)
            if self._window_bytes + byte_count <= maximum_bytes:
                self._window_bytes += byte_count
                return

            time.sleep(max(0.0, self._window_start + 1.0 - now))


class _RateMeter:
    """Measure TCP payload rates over approximately one-second windows."""

    def __init__(self, on_rates):
        self._on_rates = on_rates
        self._window_start = time.monotonic()
        self._upload_bytes = 0
        self._download_bytes = 0

    def add_upload(self, byte_count):
        self._upload_bytes += byte_count

    def add_download(self, byte_count):
        self._download_bytes += byte_count

    def update(self):
        now = time.monotonic()
        elapsed = now - self._window_start
        if elapsed < RATE_UPDATE_INTERVAL:
            return

        self._on_rates(
            self._upload_bytes * 8.0 / elapsed / 1000.0,
            self._download_bytes * 8.0 / elapsed / 1000.0
        )
        self._window_start = now
        self._upload_bytes = 0
        self._download_bytes = 0


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
