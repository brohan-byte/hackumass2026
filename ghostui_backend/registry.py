"""Compatibility factory API backed by the integration catalog."""
from .integrations.catalog import INTEGRATIONS

ADAPTERS = {key: item.factory for key, item in INTEGRATIONS.items()}

def adapter_names():
    return tuple(ADAPTERS)

def create_adapter(name, address=None, simulated=False):
    if name not in ADAPTERS:
        raise ValueError("Unknown adapter: " + name)
    return ADAPTERS[name](address, simulated)
