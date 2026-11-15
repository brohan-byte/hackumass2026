"""Explicit Mac-playback fallback; never represents Sony private device settings."""
from pathlib import Path
from .sony import SonyAdapter, SonyBridgeError

BRIDGE=Path(__file__).resolve().parents[2]/'data/sony-sdk/bin/ghostui-mac-playback'

class MacPlaybackAdapter(SonyAdapter):
    def __init__(self,address=None,simulated=False,*,bridge=BRIDGE):
        if not Path(bridge).is_file():
            raise SonyBridgeError('Build Mac playback first: .venv-vision/bin/python tools/setup_mac_playback.py')
        super().__init__(address,simulated,bridge=bridge)

    def _receive(self,timeout=20):
        result=super()._receive(timeout)
        if 'capabilities' in result and result.get('controlSource')!='mac-playback':
            raise SonyBridgeError('Expected the explicitly labeled Mac playback bridge')
        return result
