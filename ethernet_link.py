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
- Simple heartbeat for connection monitoring
- Line-based message reception
"""

import socket
import time

from telemetry import parse_telemetry
# ============================================================================
# Ethernet configuration
# ============================================================================

TEENSY_IP = "172.16.18.131"
TEENSY_PORT = 5000

# Temporary heartbeat used to verify the connection.
HEARTBEAT_INTERVAL = 2.0
ACK_TIMEOUT = 3.0

# Delay before another connection attempt is made.
RECONNECT_INTERVAL = 1.0


# ============================================================================
# Connection handling
# ============================================================================

def ethernet_link_run():
    """
    Keep the Ethernet connection to the Teensy running.

    If the connection is lost, reconnect automatically.
    """

    while True:
        try:
            print(f"Connecting to {TEENSY_IP}:{TEENSY_PORT}...")

            with socket.create_connection(
                (TEENSY_IP, TEENSY_PORT),
                timeout=3.0
            ) as client:

                print("Connected.")

                _handle_connection(client)

        except (ConnectionError, OSError) as error:
            print(f"Connection lost: {error}")
            print(
                f"Reconnecting in "
                f"{RECONNECT_INTERVAL:.0f} second..."
            )

            time.sleep(RECONNECT_INTERVAL)


# ============================================================================
# Connected state
# ============================================================================

def _handle_connection(client):
    """
    Handle communication while a TCP connection is active.
    """

    # Short receive timeout keeps the program responsive.
    client.settimeout(0.5)

    receive_buffer = ""

    next_heartbeat = 0.0

    waiting_for_ack = False
    ack_start_time = 0.0


    while True:
        current_time = time.monotonic()


        # --------------------------------------------------------------------
        # Heartbeat
        # --------------------------------------------------------------------

        if (
            not waiting_for_ack and
            current_time >= next_heartbeat
        ):
            client.sendall(b"TEST\n")

            print("Sent: TEST")

            waiting_for_ack = True
            ack_start_time = current_time


        # Consider the connection lost if the Teensy does not respond.
        if (
            waiting_for_ack and
            current_time - ack_start_time >= ACK_TIMEOUT
        ):
            raise ConnectionError("No ACK received")


        # --------------------------------------------------------------------
        # Receive data
        # --------------------------------------------------------------------

        try:
            data = client.recv(4096)

        except socket.timeout:
            continue


        # An empty receive means that the remote side closed the connection.
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

            if line == "ACK":
                waiting_for_ack = False

                next_heartbeat = (
                        time.monotonic() +
                        HEARTBEAT_INTERVAL
                )

                continue

            # ----------------------------------------------------------------
            # Telemetry
            # ----------------------------------------------------------------

            telemetry = parse_telemetry(line)

            if telemetry is None:
                print(f"Unknown message: {line}")
                continue


            # ----------------------------------------------------------------
            # Parsed message handling
            # ----------------------------------------------------------------

            if telemetry["type"] == "LOG":
                print(
                    f"[TEENSY] "
                    f"[{telemetry['level']}] "
                    f"{telemetry['message']}"
                )

            elif telemetry["type"] == "PADS":
                print(
                    "PADS: "
                    f"{telemetry['temperature_k']:.3f} K, "
                    f"{telemetry['pressure_pa']:.2f} Pa, "
                    f"t={telemetry['time_ms']} ms"
                )