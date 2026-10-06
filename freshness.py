"""Reception freshness for live displays; raw measurements remain unchanged."""
import math
import time

TEMPERATURE_TIMEOUT_S = 10.0
HEALTH_TIMEOUT_S = 75.0
TEMPERATURE_KEYS = ('THERMAL', 'PADS', 'HIDS') + tuple(
    f'MAX31865_{sensor}' for sensor in range(1, 10)
)


class Freshness:
    def __init__(self):
        self.samples = {}
        self.invalidated = set()
        self.health = {}

    def invalidate(self):
        """A reconnect must receive a new sample before values become current."""
        self.invalidated.update(self.samples)

    def observe(self, telemetry):
        kind = telemetry['type']
        if kind == 'HEALTH':
            key = telemetry['subsystem']
            if key in ('MAX31865', 'AIRDOS'):
                key += f"_{telemetry['sensor']}"
            self.health[key] = (dict(telemetry), time.monotonic())
        elif kind in ('THERMAL', 'PADS', 'HIDS', 'MAX31865'):
            key = kind if kind != 'MAX31865' else f"MAX31865_{telemetry['sensor']}"
            self.samples[key] = (telemetry['temperature_k'], time.monotonic())
            self.invalidated.discard(key)

    def temperature(self, key, connected):
        sample = self.samples.get(key)
        health = self.health.get(key)
        value, received = sample if sample else (None, None)
        age = None if received is None else max(0.0, time.monotonic() - received)
        if health and health[0]['state'] not in ('OK', 'VALID'):
            state = 'INVALID' if health[0]['state'] == 'FAULT' else health[0]['state']
        elif sample is None:
            state = 'WAITING'
        elif not math.isfinite(value):
            state = 'INVALID'
        else:
            state = 'OK'
        # Loss of the GS link always prevents a claim of current validity.
        if sample is not None and (not connected or key in self.invalidated or age >= TEMPERATURE_TIMEOUT_S):
            state = 'STALE'
        return {'state': state, 'age_s': age,
                'temperature_k': value if value is not None and math.isfinite(value) else None}

    def temperatures(self, connected):
        return {key: self.temperature(key, connected) for key in TEMPERATURE_KEYS}

    def label(self, key, connected):
        item = self.temperature(key, connected)
        value = item['temperature_k']
        text = '---' if value is None else f'{value - 273.15:.3f} °C'
        if item['state'] != 'OK':
            text += f" — {item['state']}"
            if item['age_s'] is not None:
                text += f" (last sample {item['age_s']:.0f} s ago)"
        return text

    def secondary_state(self, connected):
        report = self.health.get('SECONDARY')
        if report is None:
            return 'UNKNOWN (no link-status report)'
        if not connected or time.monotonic() - report[1] >= HEALTH_TIMEOUT_S:
            return 'STALE (primary status unavailable)'
        return report[0]['state']
