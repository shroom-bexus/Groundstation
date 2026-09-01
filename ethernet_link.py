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

HEARTBEAT_INTERVAL = 2.0
ACK_TIMEOUT = 3.0

RECONNECT_INTERVAL = 1.0


# ============================================================================
# Connection handling
# ============================================================================

def ethernet_link_run(
    command_queue,
    on_connection,
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
                timeout=6.0
            ) as client:

                on_connection(True)
                on_log("Connected.")

                try:
                    _handle_connection(
                        client,
                        command_queue,
                        on_telemetry,
                        on_log
                    )

                finally:
                    on_connection(False)

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
    on_telemetry,
    on_log
):
    """
    Handle communication while a TCP connection is active.
    """

    client.settimeout(0.5)

    receive_buffer = ""

    next_heartbeat = 0.0

    waiting_for_ack = False
    ack_start_time = 0.0


    while True:
        current_time = time.monotonic()


        # --------------------------------------------------------------------
        # Ground station commands
        # --------------------------------------------------------------------

        while not command_queue.empty():
            command = command_queue.get_nowait()

            client.sendall(
                f"{command}\n".encode("utf-8")
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
            client.sendall(
                b"CMD,PING\n"
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
            continue


        if not data:
            raise ConnectionError(
                "Connection closed by Teensy"
            )


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