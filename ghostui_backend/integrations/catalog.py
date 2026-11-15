"""Supported integration families, independent of individual physical devices.

An integration is executable only when it has a tested adapter factory. Planned
protocols belong in the roadmap, never in the selectable catalog.
"""
from dataclasses import dataclass
from .marshall import MarshallAdapter
from .wled import GeneratedAdapter as WledAdapter
from .demo_light import DemoLightAdapter
from .homeassistant import HomeAssistantAdapter
from .documented_http import DocumentedHttpAdapter
from .sony import SonyAdapter
from .mac_playback import MacPlaybackAdapter

@dataclass(frozen=True)
class Integration:
    id: str
    name: str
    transport: str
    setup: str
    factory: object
    simulation_only: bool = False

    def describe(self):
        return {"id": self.id, "name": self.name, "transport": self.transport,
                "setup": self.setup, "simulationOnly": self.simulation_only}

INTEGRATIONS = {
    "sony-playback": Integration("sony-playback", "Sony XM5 · Mac playback", "mac-audio",
        "Select the XM5 as Mac sound output and build tools/setup_mac_playback.py. Controls Mac playback volume only.", MacPlaybackAdapter),
    "sony": Integration("sony", "Sony XM5 (experimental)", "bluetooth",
        "Build tools/setup_sony.py, pair/connect the XM5 to the Mac, then pass tools/probe_sony.py before registration. Classic control transport is still unverified on this Mac.", SonyAdapter),
    "generated-http": Integration("generated-http", "Documented HTTP device", "http",
        "Discovered WLED devices can be prepared from the phone; other documented HTTP devices use --onboard.", DocumentedHttpAdapter),
    "wled": Integration("wled", "WLED brightness", "wifi",
        "Enter the reachable WLED controller IP or hostname.", WledAdapter),
    "marshall": Integration("marshall", "Marshall Acton III", "ble",
        "Scan and verify the Acton III model and supported BLE characteristics, or supply its address.", MarshallAdapter),
    "demo-light": Integration("demo-light", "Demo light (simulation)", "simulation",
        "No hardware required. Exercises the same capabilities and command pipeline.", DemoLightAdapter, True),
    "homeassistant": Integration("homeassistant", "Home Assistant entity", "http",
        "Configure HOMEASSISTANT_URL and HOMEASSISTANT_TOKEN on the Mac, then enter an entity ID such as light.ceiling_lights.",
        HomeAssistantAdapter),
}

def integration_catalog():
    return [item.describe() for item in INTEGRATIONS.values()]
