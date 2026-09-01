"""
    ███████╗██╗  ██╗██████╗  ██████╗  ██████╗ ███╗   ███╗
    ██╔════╝██║  ██║██╔══██╗██╔═══██╗██╔═══██╗████╗ ████║
    ███████╗███████║██████╔╝██║   ██║██║   ██║██╔████╔██║
    ╚════██║██╔══██║██╔══██╗██║   ██║██║   ██║██║╚██╔╝██║
    ███████║██║  ██║██║  ██║╚██████╔╝╚██████╔╝██║ ╚═╝ ██║
    ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝     ╚═╝

Stratospheric High-Altitude Radiation Observation of Organismic Mycology

ui.py
Terminal user interface for the SHROOM Ground Station.
"""

import queue
import threading

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static

from ethernet_link import ethernet_link_run


class GroundStationApp(App):
    """
    SHROOM Ground Station terminal user interface.
    """

    TITLE = "SHROOM Ground Station"
    SUB_TITLE = "BEXUS"


    CSS = """
    Screen {
        layout: vertical;
    }

    #connection {
        height: 3;
        padding: 0 2;
        border: solid white;
    }

    #data_area {
        height: 1fr;
    }

    .panel {
        width: 1fr;
        padding: 1 2;
        border: solid white;
    }

    .panel_title {
        text-style: bold;
        margin-bottom: 1;
    }

    #log {
        height: 12;
        border: solid white;
        padding: 0 1;
    }

    #command {
        height: 3;
    }
    """


    def __init__(self):
        super().__init__()

        self.command_queue = queue.Queue()
        self.connected = False

        self.health = {}


    # ========================================================================
    # UI layout
    # ========================================================================

    def compose(self) -> ComposeResult:
        yield Header()

        yield Static(
            "Connection: OFFLINE",
            id="connection"
        )

        with Horizontal(id="data_area"):

            # ----------------------------------------------------------------
            # Thermal system
            # ----------------------------------------------------------------

            with Vertical(classes="panel"):
                yield Static(
                    "THERMAL",
                    classes="panel_title"
                )

                yield Static(
                    "Controller: ---",
                    id="controller"
                )

                yield Static(
                    "Temperature: --- K",
                    id="thermal_temperature"
                )

                yield Static(
                    "Target: --- K",
                    id="thermal_target"
                )

                yield Static(
                    "Heater output: --- %",
                    id="thermal_output"
                )


            # ----------------------------------------------------------------
            # Environment
            # ----------------------------------------------------------------

            with Vertical(classes="panel"):
                yield Static(
                    "ENVIRONMENT",
                    classes="panel_title"
                )

                yield Static(
                    "PADS temperature: --- K",
                    id="pads_temperature"
                )

                yield Static(
                    "Pressure: --- Pa",
                    id="pads_pressure"
                )

            # ----------------------------------------------------------------
            # Health monitoring
            # ----------------------------------------------------------------

            with Vertical(classes="panel"):
                yield Static(
                    "HEALTH",
                    classes="panel_title"
                )

                yield Static(
                    "SD: ---\n"
                    "MAX31865: ---\n"
                    "PADS: ---\n"
                    "HIDS: ---\n"
                    "AIRDOS: ---",
                    id="health_status"
                )

        yield RichLog(
            id="log",
            wrap=True
        )

        yield Input(
            placeholder="Command: help",
            id="command"
        )

        yield Footer()


    # ========================================================================
    # Startup
    # ========================================================================

    def on_mount(self):
        """
        Start the Ethernet communication thread.
        """

        ethernet_thread = threading.Thread(
            target=ethernet_link_run,
            args=(
                self.command_queue,
                self._connection_callback,
                self._telemetry_callback,
                self._log_callback
            ),
            daemon=True
        )

        ethernet_thread.start()


    # ========================================================================
    # Ethernet callbacks
    # ========================================================================

    def _connection_callback(self, connected):
        """
        Receive connection state changes from the Ethernet thread.
        """

        self.call_from_thread(
            self._set_connection,
            connected
        )


    def _telemetry_callback(self, telemetry):
        """
        Receive parsed telemetry from the Ethernet thread.
        """

        self.call_from_thread(
            self._handle_telemetry,
            telemetry
        )


    def _log_callback(self, message):
        """
        Receive ground station log messages from the Ethernet thread.
        """

        self.call_from_thread(
            self._write_log,
            f"[GS] {message}"
        )


    # ========================================================================
    # Connection state
    # ========================================================================

    def _set_connection(self, connected):
        self.connected = connected

        connection = self.query_one(
            "#connection",
            Static
        )

        if connected:
            connection.update(
                "Connection: ONLINE"
            )

        else:
            connection.update(
                "Connection: OFFLINE"
            )


    # ========================================================================
    # Logging
    # ========================================================================

    def _write_log(self, message):
        self.query_one(
            "#log",
            RichLog
        ).write(
            message
        )


    # ========================================================================
    # Telemetry
    # ========================================================================

    def _handle_telemetry(self, telemetry):
        telemetry_type = telemetry["type"]


        # --------------------------------------------------------------------
        # Thermal control
        # --------------------------------------------------------------------

        if telemetry_type == "THERMAL":

            if telemetry["controller_active"]:
                controller_state = "ACTIVE"
            else:
                controller_state = "INACTIVE"


            self.query_one(
                "#controller",
                Static
            ).update(
                f"Controller: {controller_state}"
            )


            self.query_one(
                "#thermal_temperature",
                Static
            ).update(
                f"Temperature: "
                f"{telemetry['temperature_k']:.3f} K"
            )


            self.query_one(
                "#thermal_target",
                Static
            ).update(
                f"Target: "
                f"{telemetry['target_k']:.2f} K"
            )


            self.query_one(
                "#thermal_output",
                Static
            ).update(
                f"Heater output: "
                f"{telemetry['output_percent']:.1f} %"
            )

            return


        # --------------------------------------------------------------------
        # WSEN-PADS
        # --------------------------------------------------------------------

        if telemetry_type == "PADS":

            self.query_one(
                "#pads_temperature",
                Static
            ).update(
                f"PADS temperature: "
                f"{telemetry['temperature_k']:.3f} K"
            )


            self.query_one(
                "#pads_pressure",
                Static
            ).update(
                f"Pressure: "
                f"{telemetry['pressure_pa']:.2f} Pa"
            )

            return


        # --------------------------------------------------------------------
        # Flight computer log
        # --------------------------------------------------------------------

        if telemetry_type == "LOG":

            self._write_log(
                f"[FC] "
                f"[{telemetry['level']}] "
                f"{telemetry['message']}"
            )

            return

        # --------------------------------------------------------------------
        # Health monitoring
        # --------------------------------------------------------------------

        if telemetry_type == "HEALTH":

            subsystem = telemetry["subsystem"]

            if subsystem == "MAX31865":
                key = f"MAX31865_{telemetry['sensor']}"
            else:
                key = subsystem

            self.health[key] = telemetry

            self._update_health_panel()

            return


    # ========================================================================
    # Commands
    # ========================================================================

    def on_input_submitted(
        self,
        event: Input.Submitted
    ):
        """
        Process commands entered into the command field.
        """

        command = event.value.strip()

        event.input.value = ""

        if not command:
            return


        command_lower = command.lower()


        # --------------------------------------------------------------------
        # Local help
        # --------------------------------------------------------------------

        if command_lower == "help":

            self._write_log(
                "[GS] Available commands: help"
            )

            return


        # --------------------------------------------------------------------
        # Commands requiring an active connection
        # --------------------------------------------------------------------

        if not self.connected:

            self._write_log(
                "[GS] Cannot send command: not connected."
            )

            return


        # --------------------------------------------------------------------
        # Unknown command
        # --------------------------------------------------------------------

        self._write_log(
            f"[GS] Unknown command: {command}"
        )

    def _update_health_panel(self):
            """
            Update the permanent health overview.
            """

            lines = []

            # ------------------------------------------------------------------------
            # SD card
            # ------------------------------------------------------------------------

            sd = self.health.get("SD")

            if sd:
                lines.append(
                    f"SD: {sd['state']}  "
                    f"errors: {sd['error_count']}"
                )
            else:
                lines.append("SD: ---")

            # ------------------------------------------------------------------------
            # MAX31865 temperature sensors
            # ------------------------------------------------------------------------

            max_keys = sorted(
                key for key in self.health
                if key.startswith("MAX31865_")
            )

            if max_keys:
                for key in max_keys:
                    data = self.health[key]

                    lines.append(
                        f"TEMP {data['sensor']}: {data['state']}  "
                        f"fault: {data['fault']}  "
                        f"errors: {data['error_count']}"
                    )
            else:
                lines.append("MAX31865: ---")

            # ------------------------------------------------------------------------
            # WSEN-PADS
            # ------------------------------------------------------------------------

            pads = self.health.get("PADS")

            if pads:
                lines.append(
                    f"PADS: {pads['state']}  "
                    f"errors: {pads['error_count']}"
                )
            else:
                lines.append("PADS: ---")

            # ------------------------------------------------------------------------
            # WSEN-HIDS
            # ------------------------------------------------------------------------

            hids = self.health.get("HIDS")

            if hids:
                lines.append(
                    f"HIDS: {hids['state']}  "
                    f"errors: {hids['error_count']}"
                )
            else:
                lines.append("HIDS: ---")

            # ------------------------------------------------------------------------
            # AIRDOS
            # ------------------------------------------------------------------------

            airdos = self.health.get("AIRDOS")

            if airdos:
                age_ms = airdos["last_message_age_ms"]

                if age_ms == 0 and airdos["state"] != "OK":
                    age_text = "---"
                else:
                    age_text = f"{age_ms / 1000.0:.1f} s"

                lines.append(
                    f"AIRDOS: {airdos['state']}  "
                    f"last: {age_text}  "
                    f"overflows: {airdos['overflow_count']}"
                )
            else:
                lines.append("AIRDOS: ---")

            self.query_one(
                "#health_status",
                Static
            ).update(
                "\n".join(lines)
            )