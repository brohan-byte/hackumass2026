"""No-hardware extension example, always labeled simulation; not an ESP32 driver."""
class DemoLightAdapter:
    simulated = True
    def __init__(self, address=None, simulated=False):
        self.state = {'brightness': 40, 'warmth': 50}
    @property
    def capabilities(self):
        return {'deviceId': 'demo-light-1', 'name': 'Demo Light', 'controls': [
            {'id': 'brightness', 'label': 'Brightness', 'type': 'number', 'min': 0, 'max': 100, 'step': 1},
            {'id': 'warmth', 'label': 'Warmth', 'type': 'number', 'min': 0, 'max': 100, 'step': 1}]}
    def discover(self): pass
    def request(self, change=None):
        if change: self.state[change[0]] = change[1]
        return dict(self.state)
    def close(self): pass
