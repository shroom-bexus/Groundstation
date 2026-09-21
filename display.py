"""GS presentation helpers. Wire values and CSV temperatures remain Kelvin."""
import math

STORAGE_LABELS = {
    "SD_INTERNAL": "Primary internal SD",
    "SD_BACKUP": "Primary backup XTSD",
    "SD_SECONDARY_INTERNAL": "Secondary internal SD",
    "SD_SECONDARY_BACKUP": "Secondary backup XTSD",
}


def celsius(kelvin):
    return kelvin - 273.15


def target_kelvin(value):
    kelvin = float(value) + 273.15
    if not math.isfinite(kelvin) or kelvin < 0:
        raise ValueError("Invalid target temperature")
    return kelvin


def storage_notice(previous, current):
    """Report first faults, state changes and changed counters, without spam."""
    label = STORAGE_LABELS.get(current["subsystem"])
    if label is None:
        return None
    state, count = current["state"], current["error_count"]
    if previous and (previous["state"], previous["error_count"]) == (state, count):
        return None
    if not previous and state in ("OK", "DISABLED", "WAITING"):
        return None
    level = "ERROR" if state in ("FAULT", "STALE") else "INFO"
    return f"[{level}] {label}: {state} — errors: {count}"
