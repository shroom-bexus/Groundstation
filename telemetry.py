"""
    ███████╗██╗  ██╗██████╗  ██████╗  ██████╗ ███╗   ███╗
    ██╔════╝██║  ██║██╔══██╗██╔═══██╗██╔═══██╗████╗ ████║
    ███████╗███████║██████╔╝██║   ██║██║   ██║██╔████╔██║
    ╚════██║██╔══██║██╔══██╗██║   ██║██║   ██║██║╚██╔╝██║
    ███████║██║  ██║██║  ██║╚██████╔╝╚██████╔╝██║ ╚═╝ ██║
    ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝     ╚═╝

Stratospheric High-Altitude Radiation Observation of Organismic Mycology

telemetry.py
Parsing of telemetry messages received from the SHROOM flight computer.
"""


# ============================================================================
# Telemetry parser
# ============================================================================

def parse_telemetry(line):
    """
    Parse one telemetry message.

    Returns a dictionary containing the parsed values.
    Returns None if the message is unknown or invalid.
    """


    # ------------------------------------------------------------------------
    # Console log
    # ------------------------------------------------------------------------
    #
    # Format:
    # LOG,level,message
    #

    if line.startswith("LOG,"):
        parts = line.split(",", 2)

        if len(parts) != 3:
            return None

        return {
            "type": "LOG",
            "level": parts[1],
            "message": parts[2],
        }


    # ------------------------------------------------------------------------
    # AIRDOS raw data
    # ------------------------------------------------------------------------
    #
    # Format:
    # AIRDOS,time_ms,sensor,raw_uart_message
    #
    # The raw UART message itself may contain commas, so only split the first
    # three separators here.

    if line.startswith("AIRDOS,"):
        parts = line.split(",", 3)

        if len(parts) != 4:
            return None

        try:
            return {
                "type": "AIRDOS",
                "time_ms": int(parts[1]),
                "sensor": int(parts[2]),
                "data": parts[3],
            }

        except ValueError:
            return None


    # ------------------------------------------------------------------------
    # Split standard telemetry messages
    # ------------------------------------------------------------------------

    parts = line.split(",")

    if not parts:
        return None


    # ------------------------------------------------------------------------
    # MAX31865 / PT1000
    # ------------------------------------------------------------------------
    #
    # Format:
    # MAX31865,time_ms,sensor,temperature_K
    #

    if parts[0] == "MAX31865":
        if len(parts) != 4:
            return None

        try:
            return {
                "type": "MAX31865",
                "time_ms": int(parts[1]),
                "sensor": int(parts[2]),
                "temperature_k": float(parts[3]),
            }

        except ValueError:
            return None


    # ------------------------------------------------------------------------
    # WSEN-PADS
    # ------------------------------------------------------------------------
    #
    # Format:
    # PADS,time_ms,temperature_K,pressure_Pa
    #

    if parts[0] == "PADS":
        if len(parts) != 4:
            return None

        try:
            return {
                "type": "PADS",
                "time_ms": int(parts[1]),
                "temperature_k": float(parts[2]),
                "pressure_pa": float(parts[3]),
            }

        except ValueError:
            return None

    # ------------------------------------------------------------------------
    # WSEN-HIDS
    # ------------------------------------------------------------------------
    #
    # Format:
    # HIDS,time_ms,temperature_K,humidity_percent
    #

    if parts[0] == "HIDS":
        if len(parts) != 4:
            return None

        try:
            return {
                "type": "HIDS",
                "time_ms": int(parts[1]),
                "temperature_k": float(parts[2]),
                "humidity_percent": float(parts[3]),
            }

        except ValueError:
            return None

    # ------------------------------------------------------------------------
    # Thermal control
    # ------------------------------------------------------------------------
    #
    # Format:
    # THERMAL,time_ms,enabled,target_K,temperature_K,output_percent
    #

    if parts[0] == "THERMAL":
        if len(parts) != 6:
            return None

        try:
            return {
                "type": "THERMAL",
                "time_ms": int(parts[1]),
                "controller_enabled": bool(int(parts[2])),
                "target_k": float(parts[3]),
                "temperature_k": float(parts[4]),
                "output_percent": float(parts[5]),
            }

        except ValueError:
            return None

    # ------------------------------------------------------------------------
    # PID gains
    # ------------------------------------------------------------------------
    #
    # Format:
    # PID,time_ms,kp,ki,kd
    #

    if parts[0] == "PID":
        if len(parts) != 5:
            return None

        try:
            return {
                "type": "PID",
                "time_ms": int(parts[1]),
                "kp": float(parts[2]),
                "ki": float(parts[3]),
                "kd": float(parts[4]),
            }

        except ValueError:
            return None

    # ------------------------------------------------------------------------
    # Heaters
    # ------------------------------------------------------------------------
    #
    # Format:
    # HEATERS,time_ms,heater1,heater2,heater3,heater4
    #

    if parts[0] == "HEATERS":
        if len(parts) != 6:
            return None

        try:
            return {
                "type": "HEATERS",
                "time_ms": int(parts[1]),
                "heater_1": float(parts[2]),
                "heater_2": float(parts[3]),
                "heater_3": float(parts[4]),
                "heater_4": float(parts[5]),
            }

        except ValueError:
            return None


    # ------------------------------------------------------------------------
    # Downlink limiter / AIRDOS priority state
    # ------------------------------------------------------------------------
    #
    # Format:
    # DOWNLINK,time_ms,limit_kbit_s,airdos_level,airdos_selected_count,
    #          drop_count,suppressed_count,system_queue,airdos_queue
    #

    if parts[0] == "DOWNLINK":
        if len(parts) != 9:
            return None

        try:
            return {
                "type": "DOWNLINK",
                "time_ms": int(parts[1]),
                "limit_kbit_s": float(parts[2]),
                "airdos_level": int(parts[3]),
                "airdos_selected_count": int(parts[4]),
                "drop_count": int(parts[5]),
                "suppressed_count": int(parts[6]),
                "system_queue": int(parts[7]),
                "airdos_queue": int(parts[8]),
            }

        except ValueError:
            return None


    # ------------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------------
    #
    # Formats:
    #
    # HEALTH,time_ms,SD,state,error_count
    # HEALTH,time_ms,MAX31865,sensor,state,fault,error_count
    # HEALTH,time_ms,PADS,state,error_count
    # HEALTH,time_ms,HIDS,state,error_count
    # HEALTH,time_ms,ISDS,state,error_count
    # HEALTH,time_ms,AIRDOS,sensor,state,last_message_age_ms,overflow_count
    #

    if parts[0] == "HEALTH":
        if len(parts) < 5:
            return None

        try:
            time_ms = int(parts[1])
            subsystem = parts[2]

            # SD / PADS / HIDS / ISDS
            if subsystem in ("SD", "PADS", "HIDS", "ISDS"):
                if len(parts) != 5:
                    return None

                return {
                    "type": "HEALTH",
                    "time_ms": time_ms,
                    "subsystem": subsystem,
                    "state": parts[3],
                    "error_count": int(parts[4]),
                }

            # MAX31865
            if subsystem == "MAX31865":
                if len(parts) != 7:
                    return None

                return {
                    "type": "HEALTH",
                    "time_ms": time_ms,
                    "subsystem": subsystem,
                    "sensor": int(parts[3]),
                    "state": parts[4],
                    "fault": int(parts[5]),
                    "error_count": int(parts[6]),
                }

            # AIRDOS
            if subsystem == "AIRDOS":
                if len(parts) != 7:
                    return None

                return {
                    "type": "HEALTH",
                    "time_ms": time_ms,
                    "subsystem": subsystem,
                    "sensor": int(parts[3]),
                    "state": parts[4],
                    "last_message_age_ms": int(parts[5]),
                    "overflow_count": int(parts[6]),
                }

        except ValueError:
            return None

        return None

    # ------------------------------------------------------------------------
    # Unknown message
    # ------------------------------------------------------------------------

    return None
