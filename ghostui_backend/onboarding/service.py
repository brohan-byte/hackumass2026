"""Onboarding orchestration; contains no BLE, camera, or UI implementation.

Current server hosts one integration/device. Reading state verifies connectivity,
not physical ownership or visual identity. Writes use the existing validated
command route; the user must confirm which physical object responded.
"""
from ..integrations.catalog import INTEGRATIONS, integration_catalog

class OnboardingService:
    def __init__(self, worker, recognition):
        self.worker = worker
        self.recognition = recognition

    def describe(self):
        visual = self.recognition.status()
        return {
            "integrations": integration_catalog(),
            "selectedIntegration": self.worker.integration_id,
            "integration": INTEGRATIONS[self.worker.integration_id].describe(),
            "deviceId": self.worker.capabilities["deviceId"],
            "simulated": self.worker.simulated,
            "scope": "single-device-per-server",
            "steps": [
                {"id": "integration", "status": "selected"},
                {"id": "connection", "status": "requires-verification"},
                {"id": "control", "status": "requires-user-confirmation"},
                {"id": "visual", "status": "enrolled" if visual["views"] else "not-enrolled"},
                {"id": "interface", "status": "capabilities-available"},
            ],
        }

    def verify_connection(self):
        state = self.worker.request()
        for key, (lo, hi) in self.worker.limits.items():
            value = state.get(key)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError("Device returned invalid state for " + key)
        return {"deviceId": self.worker.capabilities["deviceId"],
                "integrationId": self.worker.integration_id,
                "simulated": self.worker.simulated, "state": state,
                "connectionVerified": True, "physicalIdentityConfirmed": False}
