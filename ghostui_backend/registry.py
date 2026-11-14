"""Register adapter factories here; routes and renderers require no device branches."""
from .adapters.marshall import MarshallAdapter
from .adapters.demo_light import DemoLightAdapter
ADAPTERS = {'marshall': MarshallAdapter, 'demo-light': DemoLightAdapter}

def adapter_names(): return tuple(ADAPTERS)

def create_adapter(name, address=None, simulated=False):
    if name not in ADAPTERS: raise ValueError('Unknown adapter: ' + name)
    return ADAPTERS[name](address, simulated)
