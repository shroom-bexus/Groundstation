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
    # Split standard telemetry messages
    # ------------------------------------------------------------------------

    parts = line.split(",")

    if not parts:
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
    # Health monitoring
    # ------------------------------------------------------------------------
    #
    # Formats:
    #
    # HEALTH,time_ms,SD,state,error_count
    # HEALTH,time_ms,MAX31865,sensor,state,fault,error_count
    # HEALTH,time_ms,PADS,state,error_count
    # HEALTH,time_ms,HIDS,state,error_count
    # HEALTH,time_ms,AIRDOS,state,last_message_age_ms,overflow_count
    #

    if parts[0] == "HEALTH":
        if len(parts) < 5:
            return None

        try:
            time_ms = int(parts[1])
            subsystem = parts[2]

            # SD / PADS / HIDS
            if subsystem in ("SD", "PADS", "HIDS"):
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
                if len(parts) != 6:
                    return None

                return {
                    "type": "HEALTH",
                    "time_ms": time_ms,
                    "subsystem": subsystem,
                    "state": parts[3],
                    "last_message_age_ms": int(parts[4]),
                    "overflow_count": int(parts[5]),
                }

        except ValueError:
            return None

        return None

    # ------------------------------------------------------------------------
    # Unknown message
    # ------------------------------------------------------------------------

    return None
