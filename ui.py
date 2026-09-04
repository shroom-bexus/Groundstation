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

import math
import queue
import threading

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static

from bandwidth import (
    BandwidthSettings,
    MAX_LIMIT_KBIT_S,
    MIN_DOWNLINK_LIMIT_KBIT_S,
    MIN_UPLINK_LIMIT_KBIT_S,
    valid_limit,
)
from ethernet_link import ethernet_link_run


SHROOM_LOGO = r"""
        ███████╗██╗  ██╗██████╗  ██████╗  ██████╗ ███╗   ███╗
        ██╔════╝██║  ██║██╔══██╗██╔═══██╗██╔═══██╗████╗ ████║
        ███████╗███████║██████╔╝██║   ██║██║   ██║██╔████╔██║
        ╚════██║██╔══██║██╔══██╗██║   ██║██║   ██║██║╚██╔╝██║
        ███████║██║  ██║██║  ██║╚██████╔╝╚██████╔╝██║ ╚═╝ ██║
        ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝     ╚═╝
Stratospheric High-Altitude Radiation Observation of Organismic Mycology
"""


def _parse_bandwidth_limit(text, minimum_kbit_s):
    """Parse kbit/s or the word 'unlimited' into a numeric limit."""

    if text.lower() == "unlimited":
        return 0.0

    value = float(text)
    if not valid_limit(value, minimum_kbit_s):
        raise ValueError

    return value


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

    #logo {
        height: 8;
        content-align: center middle;
        text-style: bold;
    }

    #connection {
        height: 3;
        padding: 0 2;
        border: solid white;
        text-style: bold;
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
        height: 16;
        border: solid white;
        padding: 1 2;
    }

    #command {
        height: 5;
        border: solid white;
        padding: 1 2;
    }
    """


    def __init__(self):
        super().__init__()

        self.command_queue = queue.Queue()
        self.connected = False
        self.bandwidth = BandwidthSettings()
        self.upload_rate_kbit_s = 0.0
        self.download_rate_kbit_s = 0.0

        self.health = {}
        self.downlink_status = None


    # ========================================================================
    # UI layout
    # ========================================================================

    def compose(self) -> ComposeResult:
        yield Header()

        yield Static(
            SHROOM_LOGO,
            id="logo"
        )

        yield Static(
            self._connection_text(),
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
                    "PID: ---",
                    id="thermal_enabled"
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
                    "Controller output: --- %",
                    id="thermal_output"
                )

                yield Static(
                    "Kp: ---\n"
                    "Ki: ---\n"
                    "Kd: ---",
                    id="pid_gains"
                )

                yield Static(
                    "",
                )

                yield Static(
                    "Heater 1: --- %\n"
                    "Heater 2: --- %\n"
                    "Heater 3: --- %\n"
                    "Heater 4: --- %",
                    id="heater_outputs"
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

                yield Static(
                    "HIDS temperature: --- K",
                    id="hids_temperature"
                )

                yield Static(
                    "Relative humidity: --- %",
                    id="hids_humidity"
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
                    "SD:        ---\n"
                    "MAX31865:  ---\n"
                    "PADS:      ---\n"
                    "HIDS:      ---\n"
                    "AIRDOS:    ---",
                    id="health_status"
                )


        # --------------------------------------------------------------------
        # Console
        # --------------------------------------------------------------------

        yield RichLog(
            id="log",
            wrap=True
        )


        # --------------------------------------------------------------------
        # Command input
        # --------------------------------------------------------------------

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
                self.bandwidth,
                self._connection_callback,
                self._rate_callback,
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


    def _rate_callback(self, upload_kbit_s, download_kbit_s):
        """Receive measured payload rates from the Ethernet thread."""

        self.call_from_thread(
            self._set_rates,
            upload_kbit_s,
            download_kbit_s
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

        if not connected:
            self.upload_rate_kbit_s = 0.0
            self.download_rate_kbit_s = 0.0

        self._update_connection_panel()


    def _set_rates(self, upload_kbit_s, download_kbit_s):
        self.upload_rate_kbit_s = upload_kbit_s
        self.download_rate_kbit_s = download_kbit_s
        self._update_connection_panel()


    @staticmethod
    def _format_limit(limit_kbit_s):
        return "unlimited" if limit_kbit_s == 0.0 else f"{limit_kbit_s:.1f}"


    def _connection_text(self):
        state = "ONLINE" if self.connected else "OFFLINE"
        uplink_limit, downlink_limit = self.bandwidth.get_limits()
        return (
            f"Connection: {state}    "
            f"Upload: {self.upload_rate_kbit_s:.1f} / "
            f"{self._format_limit(uplink_limit)} kbit/s    "
            f"Download: {self.download_rate_kbit_s:.1f} / "
            f"{self._format_limit(downlink_limit)} kbit/s"
        )


    def _update_connection_panel(self):

        connection = self.query_one(
            "#connection",
            Static
        )
        connection.update(self._connection_text())


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

            if telemetry["controller_enabled"]:
                enabled_state = "ON"
            else:
                enabled_state = "OFF"

            self.query_one(
                "#thermal_enabled",
                Static
            ).update(
                f"PID: {enabled_state}"
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
                f"Controller output: "
                f"{telemetry['output_percent']:.1f} %"
            )

            return


        # --------------------------------------------------------------------
        # PID gains
        # --------------------------------------------------------------------

        if telemetry_type == "PID":

            self.query_one(
                "#pid_gains",
                Static
            ).update(
                f"Kp: {telemetry['kp']:.6g}\n"
                f"Ki: {telemetry['ki']:.6g}\n"
                f"Kd: {telemetry['kd']:.6g}"
            )

            return


        # --------------------------------------------------------------------
        # Heater outputs
        # --------------------------------------------------------------------

        if telemetry_type == "HEATERS":

            self.query_one(
                "#heater_outputs",
                Static
            ).update(
                f"Heater 1: {telemetry['heater_1']:.1f} %\n"
                f"Heater 2: {telemetry['heater_2']:.1f} %\n"
                f"Heater 3: {telemetry['heater_3']:.1f} %\n"
                f"Heater 4: {telemetry['heater_4']:.1f} %"
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
        # WSEN-HIDS
        # --------------------------------------------------------------------

        if telemetry_type == "HIDS":

            self.query_one(
                "#hids_temperature",
                Static
            ).update(
                f"HIDS temperature: "
                f"{telemetry['temperature_k']:.3f} K"
            )


            self.query_one(
                "#hids_humidity",
                Static
            ).update(
                f"Relative humidity: "
                f"{telemetry['humidity_percent']:.2f} %"
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
        # Downlink limiter / AIRDOS priority
        # --------------------------------------------------------------------

        if telemetry_type == "DOWNLINK":

            self.downlink_status = telemetry
            self._update_health_panel()

            return


        # --------------------------------------------------------------------
        # Health monitoring
        # --------------------------------------------------------------------

        if telemetry_type == "HEALTH":

            subsystem = telemetry["subsystem"]

            if subsystem in ("MAX31865", "AIRDOS"):
                key = f"{subsystem}_{telemetry['sensor']}"
            else:
                key = subsystem

            self.health[key] = telemetry

            self._update_health_panel()

            return


    # ========================================================================
    # Health monitoring
    # ========================================================================

    def _update_health_panel(self):
        """
        Update the permanent health overview.
        """

        lines = []


        # --------------------------------------------------------------------
        # SD card
        # --------------------------------------------------------------------

        sd = self.health.get("SD")

        if sd:
            lines.append(
                f"SD: {sd['state']}  "
                f"errors: {sd['error_count']}"
            )
        else:
            lines.append(
                "SD: ---"
            )


        # --------------------------------------------------------------------
        # MAX31865 temperature sensors
        # --------------------------------------------------------------------

        max_keys = sorted(
            key for key in self.health
            if key.startswith("MAX31865_")
        )

        if max_keys:

            for key in max_keys:
                data = self.health[key]

                lines.append(
                    f"TEMP {data['sensor']}: "
                    f"{data['state']}  "
                    f"fault: {data['fault']}  "
                    f"errors: {data['error_count']}"
                )

        else:
            lines.append(
                "MAX31865: ---"
            )


        # --------------------------------------------------------------------
        # WSEN-PADS
        # --------------------------------------------------------------------

        pads = self.health.get("PADS")

        if pads:
            lines.append(
                f"PADS: {pads['state']}  "
                f"errors: {pads['error_count']}"
            )
        else:
            lines.append(
                "PADS: ---"
            )


        # --------------------------------------------------------------------
        # WSEN-HIDS
        # --------------------------------------------------------------------

        hids = self.health.get("HIDS")

        if hids:
            lines.append(
                f"HIDS: {hids['state']}  "
                f"errors: {hids['error_count']}"
            )
        else:
            lines.append(
                "HIDS: ---"
            )


        # --------------------------------------------------------------------
        # AIRDOS
        # --------------------------------------------------------------------

        airdos_keys = sorted(
            (
                key for key in self.health
                if key.startswith("AIRDOS_")
            ),
            key=lambda key: int(key.split("_", 1)[1])
        )

        if airdos_keys:
            for key in airdos_keys:
                airdos = self.health[key]
                age_ms = airdos["last_message_age_ms"]

                if age_ms == 0 and airdos["state"] != "OK":
                    age_text = "---"
                else:
                    age_text = f"{age_ms / 1000.0:.1f} s"

                lines.append(
                    f"AIRDOS {airdos['sensor']}: "
                    f"{airdos['state']}  "
                    f"last: {age_text}  "
                    f"overflows: {airdos['overflow_count']}"
                )

        else:
            lines.append(
                "AIRDOS: ---"
            )


        # --------------------------------------------------------------------
        # Downlink limiter / AIRDOS priority
        # --------------------------------------------------------------------

        downlink = self.downlink_status

        if downlink:
            if downlink["limit_kbit_s"] == 0.0:
                limit_text = "unlimited"
            else:
                limit_text = f"{downlink['limit_kbit_s']:.1f} kbit/s"

            lines.append("")
            lines.append(
                f"FC downlink: {limit_text}  "
                f"AIRDOS: {downlink['airdos_selected_count']}/9 "
                f"(level {downlink['airdos_level']})"
            )
            lines.append(
                f"TX drops: {downlink['drop_count']}  "
                f"suppressed: {downlink['suppressed_count']}"
            )
            lines.append(
                f"Queues: system {downlink['system_queue']}  "
                f"AIRDOS {downlink['airdos_queue']}"
            )


        self.query_one(
            "#health_status",
            Static
        ).update(
            "\n".join(lines)
        )


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
                "[GS] Available commands:"
            )

            self._write_log(
                "  target <K>"
            )

            self._write_log(
                "  thermal <on/off>"
            )

            self._write_log(
                "  pid <Kp> <Ki> <Kd>"
            )

            self._write_log(
                "  kp <value>"
            )

            self._write_log(
                "  ki <value>"
            )

            self._write_log(
                "  kd <value>"
            )

            self._write_log(
                "  rates <upload> <download>  (kbit/s)"
            )

            self._write_log(
                "  upload <kbit/s|unlimited>"
            )

            self._write_log(
                "  download <kbit/s|unlimited>"
            )

            self._write_log(
                "  heater <1-4|all> <0-100>"
            )

            self._write_log(
                "  help"
            )

            return


        # --------------------------------------------------------------------
        # Bandwidth limits (also available while offline)
        # --------------------------------------------------------------------

        command_parts = command.split()
        bandwidth_command = command_parts[0].lower()

        if bandwidth_command in ("rates", "upload", "download"):
            if bandwidth_command == "rates" and len(command_parts) == 1:
                uplink_limit, downlink_limit = self.bandwidth.get_limits()
                self._write_log(
                    "[GS] Bandwidth limits: "
                    f"upload {self._format_limit(uplink_limit)}, "
                    f"download {self._format_limit(downlink_limit)} kbit/s"
                )
                return

            expected_parts = 3 if bandwidth_command == "rates" else 2
            if len(command_parts) != expected_parts:
                usage = (
                    "rates <upload> <download>"
                    if bandwidth_command == "rates"
                    else f"{bandwidth_command} <kbit/s|unlimited>"
                )
                self._write_log(f"[GS] Usage: {usage}")
                return

            uplink_limit, downlink_limit = self.bandwidth.get_limits()

            try:
                if bandwidth_command == "rates":
                    uplink_limit = _parse_bandwidth_limit(
                        command_parts[1],
                        MIN_UPLINK_LIMIT_KBIT_S
                    )
                    downlink_limit = _parse_bandwidth_limit(
                        command_parts[2],
                        MIN_DOWNLINK_LIMIT_KBIT_S
                    )
                elif bandwidth_command == "upload":
                    uplink_limit = _parse_bandwidth_limit(
                        command_parts[1],
                        MIN_UPLINK_LIMIT_KBIT_S
                    )
                else:
                    downlink_limit = _parse_bandwidth_limit(
                        command_parts[1],
                        MIN_DOWNLINK_LIMIT_KBIT_S
                    )
            except ValueError:
                self._write_log(
                    "[GS] Upload must be "
                    f"{MIN_UPLINK_LIMIT_KBIT_S:.0f}...{MAX_LIMIT_KBIT_S:.0f}; "
                    "download must be "
                    f"{MIN_DOWNLINK_LIMIT_KBIT_S:.0f}...{MAX_LIMIT_KBIT_S:.0f} "
                    "kbit/s, or unlimited."
                )
                return

            try:
                saved = self.bandwidth.set_limits(
                    uplink_limit,
                    downlink_limit
                )
            except OSError as error:
                self._write_log(
                    f"[GS] Could not save bandwidth limits: {error}"
                )
                return

            if not saved:
                self._write_log("[GS] Invalid bandwidth limits.")
                return

            self._update_connection_panel()

            if self.connected:
                self.command_queue.put(
                    f"CMD,SET_DL_LIMIT,{downlink_limit:.6g}"
                )

            self._write_log(
                "[GS] Bandwidth limits: "
                f"upload {self._format_limit(uplink_limit)}, "
                f"download {self._format_limit(downlink_limit)} kbit/s"
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
        # Set thermal target
        # --------------------------------------------------------------------

        if command_lower.startswith("target "):
            parts = command.split()

            if len(parts) != 2:
                self._write_log(
                    "[GS] Usage: target <K>"
                )
                return


            try:
                target_k = float(
                    parts[1]
                )

            except ValueError:
                self._write_log(
                    "[GS] Invalid target temperature."
                )
                return


            self.command_queue.put(
                f"CMD,SET_TARGET,{target_k:.2f}"
            )

            return


        # --------------------------------------------------------------------
        # Thermal controller
        # --------------------------------------------------------------------

        if command_lower == "thermal on":

            self.command_queue.put(
                "CMD,THERMAL_ON"
            )

            return


        if command_lower == "thermal off":

            self.command_queue.put(
                "CMD,THERMAL_OFF"
            )

            return


        # --------------------------------------------------------------------
        # PID gains
        # --------------------------------------------------------------------

        if command_lower.startswith("pid "):
            parts = command.split()

            if len(parts) != 4:
                self._write_log(
                    "[GS] Usage: pid <Kp> <Ki> <Kd>"
                )
                return


            try:
                kp, ki, kd = (
                    float(value) for value in parts[1:]
                )

            except ValueError:
                self._write_log(
                    "[GS] Invalid PID gains."
                )
                return


            if any(
                not math.isfinite(gain) or
                gain < 0.0 or
                gain > 1000.0
                for gain in (kp, ki, kd)
            ):
                self._write_log(
                    "[GS] PID gains must be between 0 and 1000."
                )
                return


            self.command_queue.put(
                f"CMD,SET_PID,{kp:.6g},{ki:.6g},{kd:.6g}"
            )

            return


        # --------------------------------------------------------------------
        # Individual PID gain
        # --------------------------------------------------------------------

        gain_commands = {
            "kp": "SET_KP",
            "ki": "SET_KI",
            "kd": "SET_KD",
        }

        if command_parts[0].lower() in gain_commands:
            gain_name = command_parts[0].lower()

            if len(command_parts) != 2:
                self._write_log(
                    f"[GS] Usage: {gain_name} <value>"
                )
                return


            try:
                gain_value = float(command_parts[1])

            except ValueError:
                self._write_log(
                    f"[GS] Invalid {gain_name} value."
                )
                return


            if (
                not math.isfinite(gain_value) or
                gain_value < 0.0 or
                gain_value > 1000.0
            ):
                self._write_log(
                    f"[GS] {gain_name} must be between 0 and 1000."
                )
                return


            self.command_queue.put(
                f"CMD,{gain_commands[gain_name]},"
                f"{gain_value:.6g}"
            )

            return


        # --------------------------------------------------------------------
        # Manual heater control
        # --------------------------------------------------------------------

        if command_lower.startswith("heater "):
            parts = command.split()

            if len(parts) != 3:
                self._write_log(
                    "[GS] Usage: heater <1-4|all> <0-100>"
                )
                return


            heater_argument = (
                parts[1].lower()
            )


            try:
                power_percent = float(
                    parts[2]
                )

            except ValueError:
                self._write_log(
                    "[GS] Invalid heater power."
                )
                return


            if (
                power_percent < 0.0 or
                power_percent > 100.0
            ):
                self._write_log(
                    "[GS] Heater power must be 0...100 %."
                )
                return


            # ----------------------------------------------------------------
            # All heaters
            # ----------------------------------------------------------------

            if heater_argument == "all":

                self.command_queue.put(
                    f"CMD,SET_HEATER,ALL,"
                    f"{power_percent:.1f}"
                )

                return


            # ----------------------------------------------------------------
            # Individual heater
            # ----------------------------------------------------------------

            try:
                heater_number = int(
                    heater_argument
                )

            except ValueError:
                self._write_log(
                    "[GS] Heater must be 1...4 or all."
                )
                return


            if (
                heater_number < 1 or
                heater_number > 4
            ):
                self._write_log(
                    "[GS] Heater must be 1...4 or all."
                )
                return


            self.command_queue.put(
                f"CMD,SET_HEATER,"
                f"{heater_number},"
                f"{power_percent:.1f}"
            )

            return


        # --------------------------------------------------------------------
        # Unknown command
        # --------------------------------------------------------------------

        self._write_log(
            f"[GS] Unknown command: {command}"
        )
