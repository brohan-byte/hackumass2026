"""Shared boundary: adapters own device semantics; UI consumes capabilities."""
from typing import Protocol

class DeviceAdapter(Protocol):
    simulated: bool
    @property
    def capabilities(self) -> dict: ...
    def discover(self) -> None: ...
    def request(self, change: tuple[str, int] | None = None) -> dict: ...
    def close(self) -> None: ...


def numeric_limits(capabilities):
    """Current renderer supports integer sliders. Reject unsupported manifests."""
    limits = {}
    controls = capabilities.get('controls', [])
    if not capabilities.get('deviceId') or not capabilities.get('name') or not controls:
        raise ValueError('Device needs identity, name and controls')
    for c in controls:
        key = c['id']
        if not isinstance(key, str) or key in limits:
            raise ValueError('Control IDs must be unique strings')
        if c['type'] != 'number' or c.get('step', 1) != 1:
            raise ValueError('Only integer sliders are currently supported')
        lo, hi = c['min'], c['max']
        if type(lo) is not int or type(hi) is not int or lo >= hi:
            raise ValueError('Invalid integer capability range')
        limits[key] = (lo, hi)
    return limits


def validate_command(limits, change):
    field, value = change
    if not isinstance(field, str) or field not in limits:
        raise ValueError('Unknown capability')
    lo, hi = limits[field]
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'Expected an integer in {lo}..{hi}')
