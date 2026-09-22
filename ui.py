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
import time

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
from display import celsius, target_kelvin, STORAGE_LABELS, storage_notice
from freshness import Freshness
from rich.text import Text


SHROOM_BANNER = """
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
    SUB_TITLE = "BEXUS 39"


    CSS = """
    Screen {
        layout: vertical;
    }

    #brand {
        height: 8;
        content-align: center middle;
        text-style: bold;
        color: cyan;
    }

    #status_bar {
        height: 3;
    }

    #connection, #rtc {
        height: 3;
        padding: 0 1;
        border: round grey;
        content-align: left middle;
    }

    #connection {
        width: 3fr;
        text-style: bold;
    }

    #rtc {
        width: 2fr;
    }

    #connection.online {
        border: round green;
    }

    #connection.offline {
        border: round red;
    }

    #data_area {
        height: 1fr;
    }

    .panel {
        width: 1fr;
        overflow-y: auto;
        padding: 0 1;
        border: round grey;
    }

    .panel_title {
        height: 1;
        text-style: bold;
        color: cyan;
        margin-bottom: 1;
    }

    .section_title {
        height: 1;
        margin-top: 1;
        text-style: bold;
        color: grey;
    }

    #console_title {
        height: 1;
        padding: 0 1;
        text-style: bold;
        color: cyan;
    }

    #log {
        height: 10;
        border: round grey;
        padding: 0 1;
    }

    #command {
        height: 3;
        border: round cyan;
        padding: 0 1;
    }
    """


    def __init__(self):
        super().__init__()

        self.command_queue = queue.Queue()
        self.connected = False
        self.bandwidth = BandwidthSettings()
        self.upload_rate_kbit_s = 0.0
        self.download_rate_kbit_s = 0.0

        self.freshness = Freshness()
        self.rtc = None
        self.rtc_received_at = None
        self.health = {}
        self.downlink_status = None
        self.max31865_temperatures = {}


    # ========================================================================
    # UI layout
    # ========================================================================

    def compose(self) -> ComposeResult:
        yield Header()

        yield Static(SHROOM_BANNER, id="brand")

        with Horizontal(id="status_bar"):
            yield Static(
                self._connection_text(),
                id="connection",
                classes="offline"
            )
            yield Static("RTC UTC  |  waiting for data", id="rtc")

        with Horizontal(id="data_area"):

            # ----------------------------------------------------------------
            # Thermal system
            # ----------------------------------------------------------------

            with Vertical(classes="panel"):
                yield Static(
                    "THERMAL CONTROL",
                    classes="panel_title"
                )

                yield Static("CONTROL", classes="section_title")

                yield Static(
                    "Enabled       ---",
                    id="thermal_enabled"
                )

                yield Static(
                    "Temperature   --- °C",
                    id="thermal_temperature"
                )

                yield Static(
                    "Target        --- °C",
                    id="thermal_target"
                )

                yield Static(
                    "Output        --- %",
                    id="thermal_output"
                )

                yield Static("Regulator     ---", id="thermal_config")

                yield Static("PID", classes="section_title")

                yield Static(
                    "Kp  ---\n"
                    "Ki  ---\n"
                    "Kd  ---",
                    id="pid_gains"
                )

                yield Static("HEATERS", classes="section_title")

                yield Static(
                    "Heater 1      --- %\n"
                    "Heater 2      --- %\n"
                    "Heater 3      --- %\n"
                    "Heater 4      --- %",
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

                yield Static("AMBIENT", classes="section_title")

                yield Static(
                    "PADS temp.     --- °C",
                    id="pads_temperature"
                )

                yield Static(
                    "Pressure       --- Pa",
                    id="pads_pressure"
                )

                yield Static(
                    "HIDS temp.     --- °C",
                    id="hids_temperature"
                )

                yield Static(
                    "Humidity       --- %",
                    id="hids_humidity"
                )

                yield Static("PT1000 / MAX31865", classes="section_title")

                yield Static(
                    "TEMP 1  ---\n"
                    "TEMP 2  ---\n"
                    "TEMP 3  ---\n"
                    "TEMP 4  ---\n"
                    "TEMP 5  ---\n"
                    "TEMP 6  ---\n"
                    "TEMP 7  ---\n"
                    "TEMP 8  ---\n"
                    "TEMP 9  ---",
                    id="max31865_temperatures"
                )


            # ----------------------------------------------------------------
            # Health monitoring
            # ----------------------------------------------------------------

            with Vertical(classes="panel"):
                yield Static(
                    "SYSTEM HEALTH",
                    classes="panel_title"
                )

                yield Static(
                    "Primary internal SD: WAITING\n"
                    "Primary backup XTSD: WAITING\n"
                    "Secondary internal SD: WAITING\n"
                    "Secondary backup XTSD: WAITING\n"
                    "MAX31865:  ---\n"
                    "PADS:      ---\n"
                    "HIDS:      ---\n"
                    "ISDS:      ---\n"
                    "AIRDOS:    ---",
                    id="health_status"
                )


        # --------------------------------------------------------------------
        # Console
        # --------------------------------------------------------------------

        yield Static("EVENT LOG", id="console_title")

        yield RichLog(
            id="log",
            wrap=True
        )

        # --------------------------------------------------------------------
        # Command input
        # --------------------------------------------------------------------

        yield Input(
            placeholder="Enter command  •  HELP shows available commands",
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
        self.query_one("#command", Input).focus()
        self.set_interval(1.0, self._update_live_validity)
        self.set_interval(1.0, self._update_rtc_panel)


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
            self.freshness.invalidate()
            self.upload_rate_kbit_s = 0.0
            self.download_rate_kbit_s = 0.0

        self._update_connection_panel()
        self._update_live_validity()


    def _update_rtc_panel(self):
        if self.rtc is None:
            text = "waiting for data"
        else:
            text = self.rtc["timestamp_utc"] if self.rtc["valid"] else "INVALID / not synchronized"
            age = time.monotonic() - self.rtc_received_at
            text += f" (last sample, received {age:.0f} s ago)"
            if not self.connected or age > 75:
                text += " — STALE"
        self.query_one("#rtc", Static).update(f"RTC UTC  |  {text}")

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
            f"NET {state}  |  "
            f"UL {self.upload_rate_kbit_s:.1f}/{self._format_limit(uplink_limit)}  |  "
            f"DL {self.download_rate_kbit_s:.1f}/{self._format_limit(downlink_limit)} kbit/s"
        )


    def _update_connection_panel(self):

        connection = self.query_one(
            "#connection",
            Static
        )
        connection.update(self._connection_text())
        connection.remove_class("online", "offline")
        connection.add_class("online" if self.connected else "offline")


    # ========================================================================
    # Logging
    # ========================================================================

    def _write_log(self, message):
        self.query_one(
            "#log",
            RichLog
        ).write(
            Text(message, style="bold red") if "[ERROR]" in message else message
        )


    # ========================================================================
    # Telemetry
    # ========================================================================

    def _handle_telemetry(self, telemetry):
        telemetry_type = telemetry["type"]
        self.freshness.observe(telemetry)

        if telemetry_type == "RTC":
            self.rtc = telemetry
            self.rtc_received_at = time.monotonic()
            self._update_rtc_panel()
            return


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
                f"Enabled       {enabled_state}"
            )


            self.query_one(
                "#thermal_temperature",
                Static
            ).update(
                f"Temperature   {self.freshness.label('THERMAL', self.connected)}"
            )


            self.query_one(
                "#thermal_target",
                Static
            ).update(
                f"Target        "
                f"{celsius(telemetry['target_k']):.2f} °C"
            )


            self.query_one(
                "#thermal_output",
                Static
            ).update(
                f"Output        "
                f"{telemetry['output_percent']:.1f} %"
            )

            return


        # --------------------------------------------------------------------
        # PID gains
        # --------------------------------------------------------------------

        if telemetry_type == "THERMAL_CONFIG":
            fusion = telemetry.get("fusion_mode") or "---"
            self.query_one("#thermal_config", Static).update(
                f"Regulator     {telemetry['mode']}\n"
                f"Fusion        {fusion}\n"
                f"Hysteresis    ±{telemetry['hysteresis_k']:.6g} °C\n"
                f"BB power      {telemetry['bang_bang_power_percent']:.6g} %"
            )
            return

        if telemetry_type == "PID":

            self.query_one(
                "#pid_gains",
                Static
            ).update(
                f"Kp  {telemetry['kp']:.6g}\n"
                f"Ki  {telemetry['ki']:.6g}\n"
                f"Kd  {telemetry['kd']:.6g}"
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
                f"Heater 1      {telemetry['heater_1']:.1f} %\n"
                f"Heater 2      {telemetry['heater_2']:.1f} %\n"
                f"Heater 3      {telemetry['heater_3']:.1f} %\n"
                f"Heater 4      {telemetry['heater_4']:.1f} %"
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
                f"PADS temp.     {self.freshness.label('PADS', self.connected)}"
            )


            self.query_one(
                "#pads_pressure",
                Static
            ).update(
                f"Pressure       "
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
                f"HIDS temp.     {self.freshness.label('HIDS', self.connected)}"
            )


            self.query_one(
                "#hids_humidity",
                Static
            ).update(
                f"Humidity       "
                f"{telemetry['humidity_percent']:.2f} %"
            )

            return


        # --------------------------------------------------------------------
        # MAX31865 / PT1000 temperatures
        # --------------------------------------------------------------------

        if telemetry_type == "MAX31865":
            sensor = telemetry["sensor"]
            self.max31865_temperatures[sensor] = telemetry["temperature_k"]

            self._update_temperature_panel()

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

            notice = storage_notice(self.health.get(key), telemetry)
            if notice:
                self._write_log(notice)
            self.health[key] = telemetry
            self._update_temperature_panel()

            self._update_health_panel()

            return


    # ========================================================================
    # Health monitoring
    # ========================================================================

    def _update_temperature_panel(self):
        for key, widget, label in (
            ('THERMAL', '#thermal_temperature', 'Temperature  '),
            ('PADS', '#pads_temperature', 'PADS temp.    '),
            ('HIDS', '#hids_temperature', 'HIDS temp.    '),
        ):
            self.query_one(widget, Static).update(
                f"{label} {self.freshness.label(key, self.connected)}")
        lines = [
            f"TEMP {sensor:<2} {self.freshness.label(f'MAX31865_{sensor}', self.connected)}"
            for sensor in range(1, 10)
        ]
        self.query_one('#max31865_temperatures', Static).update('\n'.join(lines))

    def _update_live_validity(self):
        self._update_temperature_panel()
        self._update_health_panel()

    def _update_health_panel(self):
        """
        Update the permanent health overview.
        """

        lines = [
            "LINK",
            f"Secondary Teensy  {self.freshness.secondary_state(self.connected)}",
            "",
            "STORAGE",
        ]


        # --------------------------------------------------------------------
        # SD card
        # --------------------------------------------------------------------

        for key, label in STORAGE_LABELS.items():
            sd = self.health.get(key)
            lines.append(
                f"{label}: {sd['state']}  errors: {sd['error_count']}"
                if sd else f"{label}: WAITING"
            )
        # Older firmware only supplies the aggregate SD status.
        if "SD" in self.health and "SD_INTERNAL" not in self.health:
            sd = self.health["SD"]
            lines.append(f"SD (legacy combined): {sd['state']}  errors: {sd['error_count']}")


        # --------------------------------------------------------------------
        # MAX31865 temperature sensors
        # --------------------------------------------------------------------

        lines.extend(["", "TEMPERATURE SENSORS"])

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

        lines.extend(["", "OTHER SENSORS"])

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
        # WSEN-ISDS
        # --------------------------------------------------------------------

        isds = self.health.get("ISDS")

        if isds:
            lines.append(
                f"ISDS: {isds['state']}  "
                f"errors: {isds['error_count']}"
            )
        else:
            lines.append(
                "ISDS: ---"
            )


        # --------------------------------------------------------------------
        # AIRDOS
        # --------------------------------------------------------------------

        lines.extend(["", "AIRDOS"])

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

            lines.extend(["", "DOWNLINK"])
            lines.append(
                f"Limit: {limit_text}  "
                f"selected {downlink['airdos_selected_count']}/9 "
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
                "  target <°C>"
            )

            self._write_log(
                "  thermal <on/off/pid/bangbang>"
            )

            self._write_log(
                "  fusion <mean/median/min/max>"
            )

            self._write_log("  hysteresis <°C> (half-width, 0 < °C <= 10)")
            self._write_log("  bbpower <percent> (0..100)")

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
                    "[GS] Usage: target <°C>"
                )
                return


            try:
                target_k = target_kelvin(
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

        if command_lower in ("thermal pid", "thermal bangbang"):
            mode = "PID" if command_lower == "thermal pid" else "BANG_BANG"
            self.command_queue.put(f"CMD,SET_THERMAL_MODE,{mode}")
            return

        fusion_parts = command_lower.split()
        if (
            fusion_parts[:1] == ["fusion"] or
            fusion_parts[:2] == ["thermal", "fusion"]
        ):
            value_index = 1 if fusion_parts[:1] == ["fusion"] else 2
            if len(fusion_parts) != value_index + 1:
                self._write_log(
                    "[GS] Usage: fusion <mean|median|min|max>"
                )
                return

            fusion_modes = {
                "mean": "MEAN",
                "median": "MEDIAN",
                "min": "MINIMUM",
                "minimum": "MINIMUM",
                "max": "MAXIMUM",
                "maximum": "MAXIMUM",
            }
            fusion_mode = fusion_modes.get(fusion_parts[value_index])
            if fusion_mode is None:
                self._write_log(
                    "[GS] Fusion must be mean, median, min, or max."
                )
                return

            self.command_queue.put(
                f"CMD,SET_THERMAL_FUSION,{fusion_mode}"
            )
            return

        if command_lower.split()[0] in ("hysteresis", "bbpower"):
            parts = command_lower.split()
            try:
                if len(parts) != 2:
                    raise ValueError
                value = float(parts[1])
                valid = (0 < value <= 10) if parts[0] == "hysteresis" else (0 <= value <= 100)
                if not math.isfinite(value) or not valid:
                    raise ValueError
            except ValueError:
                self._write_log("[GS] Usage: hysteresis <°C: >0..10> or bbpower <percent: 0..100>")
                return
            name = "SET_HYSTERESIS" if parts[0] == "hysteresis" else "SET_BB_POWER"
            self.command_queue.put(f"CMD,{name},{value:.6g}")
            return

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

