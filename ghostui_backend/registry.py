"""Compatibility factory API backed by the integration catalog."""
from .integrations.catalog import INTEGRATIONS

ADAPTERS = {key: item.factory for key, item in INTEGRATIONS.items()}

def adapter_names():
    return tuple(ADAPTERS)

def create_adapter(name, address=None, simulated=False, binding=None):
    if name not in ADAPTERS:
        raise ValueError("Unknown adapter: " + name)
    if name == 'generated-http':
        return ADAPTERS[name](address, simulated, binding=binding)
    if binding is not None:
        raise ValueError('Only generated-http accepts a supplied binding')
    return ADAPTERS[name](address, simulated)
