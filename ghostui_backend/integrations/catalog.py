"""Supported integration families, independent of individual physical devices.

An integration is executable only when it has a tested adapter factory. Planned
protocols belong in the roadmap, never in the selectable catalog.
"""
from dataclasses import dataclass
from .marshall import MarshallAdapter
from .demo_light import DemoLightAdapter
from .homeassistant import HomeAssistantAdapter

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
    "marshall": Integration("marshall", "Marshall Acton III", "ble",
        "Scan and verify the Acton III model and supported BLE characteristics, or supply its address.", MarshallAdapter),
    "demo-light": Integration("demo-light", "Demo light (simulation)", "simulation",
        "No hardware required. Exercises the same capabilities and command pipeline.", DemoLightAdapter, True),
    "homeassistant": Integration("homeassistant", "Home Assistant entity", "http",
        "Set HOMEASSISTANT_URL and HOMEASSISTANT_TOKEN in .env, then pass an entity ID such as light.ceiling_lights.",
        HomeAssistantAdapter),
}

def integration_catalog():
    return [item.describe() for item in INTEGRATIONS.values()]
