"""Persistent bandwidth limits for the SHROOM Ground Station."""

import json
import math
import os
import threading
from pathlib import Path


DEFAULT_UPLINK_LIMIT_KBIT_S = 0.0
DEFAULT_DOWNLINK_LIMIT_KBIT_S = 0.0
MIN_LIMIT_KBIT_S = 2.0
MAX_LIMIT_KBIT_S = 10000.0


def valid_limit(limit_kbit_s):
    """Return whether a limit is unlimited (0) or inside the valid range."""

    return (
        math.isfinite(limit_kbit_s) and
        (
            limit_kbit_s == 0.0 or
            MIN_LIMIT_KBIT_S <= limit_kbit_s <= MAX_LIMIT_KBIT_S
        )
    )


class BandwidthSettings:
    """Store thread-safe uplink and downlink limits in kbit/s."""

    def __init__(self, settings_path=None):
        self._lock = threading.Lock()
        self._settings_path = (
            Path(settings_path) if settings_path else self._default_path()
        )
        self._uplink_limit = DEFAULT_UPLINK_LIMIT_KBIT_S
        self._downlink_limit = DEFAULT_DOWNLINK_LIMIT_KBIT_S
        self._load()

    @staticmethod
    def _default_path():
        config_root = Path(
            os.environ.get(
                "XDG_CONFIG_HOME",
                Path.home() / ".config"
            )
        )
        return config_root / "shroom-groundstation" / "settings.json"

    def get_limits(self):
        """Return the current uplink and downlink limits."""

        with self._lock:
            return self._uplink_limit, self._downlink_limit

    def set_limits(self, uplink_limit, downlink_limit):
        """Validate, activate, and persist both limits."""

        if not valid_limit(uplink_limit) or not valid_limit(downlink_limit):
            return False

        with self._lock:
            previous_uplink = self._uplink_limit
            previous_downlink = self._downlink_limit
            self._uplink_limit = uplink_limit
            self._downlink_limit = downlink_limit
            try:
                self._save()
            except OSError:
                self._uplink_limit = previous_uplink
                self._downlink_limit = previous_downlink
                raise

        return True

    def _load(self):
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
            uplink = float(data["uplink_limit_kbit_s"])
            downlink = float(data["downlink_limit_kbit_s"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return

        if valid_limit(uplink) and valid_limit(downlink):
            self._uplink_limit = uplink
            self._downlink_limit = downlink

    def _save(self):
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._settings_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(
                {
                    "uplink_limit_kbit_s": self._uplink_limit,
                    "downlink_limit_kbit_s": self._downlink_limit,
                },
                indent=2
            ) + "\n",
            encoding="utf-8"
        )
        temporary_path.replace(self._settings_path)
