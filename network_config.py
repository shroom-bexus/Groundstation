"""Read the Linux interface selected by the SHROOM network setup."""

import os
from pathlib import Path


DEFAULT_NETWORK_INTERFACE = "enp0s31f6"
SYSTEM_CONFIG_PATH = Path("/etc/shroom-groundstation/network.conf")


def network_interface():
    """Return the configured SHROOM Ethernet interface name."""

    environment_value = os.environ.get("SHROOM_NETWORK_INTERFACE")
    if environment_value:
        return environment_value

    try:
        lines = SYSTEM_CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return DEFAULT_NETWORK_INTERFACE

    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key.strip() == "SHROOM_INTERFACE":
            value = value.strip().strip("\"'")
            if value:
                return value

    return DEFAULT_NETWORK_INTERFACE
