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
    # Example:
    # LOG,INFO,Initialization complete.
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


    # Unknown message type.
    return None

    # ------------------------------------------------------------------------
    # System status
    # ------------------------------------------------------------------------
    #
    # Format:
    # STATUS,time_ms,heater_enabled,target_K,pwm,temp_K
    #

    if parts[0] == "STATUS":
        if len(parts) != 6:
            return None

        try:
            return {
                "type": "STATUS",
                "time_ms": int(parts[1]),
                "heater_enabled": bool(int(parts[2])),
                "target_k": float(parts[3]),
                "pwm": float(parts[4]),
                "temperature_k": float(parts[5]),
            }

        except ValueError:
            return None