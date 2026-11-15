import unittest
from unittest.mock import Mock
from ghostui_backend.integrations.catalog import integration_catalog
from ghostui_backend.onboarding.service import OnboardingService
from ghostui_backend.service import DeviceWorker

class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.worker = DeviceWorker(device='demo-light')
        self.addCleanup(self.worker.close)
        self.recognition = Mock()
        self.recognition.status.return_value = {'views': 0}
        self.service = OnboardingService(self.worker, self.recognition)

    def test_catalog_only_lists_implemented_integrations(self):
        catalog = {item['id']: item for item in integration_catalog()}
        self.assertEqual(set(catalog), {'marshall', 'demo-light', 'wled', 'homeassistant'})
        self.assertEqual(catalog['homeassistant']['transport'], 'http')
        self.assertTrue(catalog['demo-light']['simulationOnly'])
        self.assertEqual(catalog['marshall']['transport'], 'ble')

    def test_visual_enrollment_and_connection_are_separate(self):
        summary = self.service.describe()
        self.assertEqual(summary['selectedIntegration'], 'demo-light')
        self.assertEqual(summary['scope'], 'single-device-per-server')
        self.assertEqual(summary['steps'][3]['status'], 'not-enrolled')
        self.recognition.status.return_value = {'views': 4}
        self.assertEqual(self.service.describe()['steps'][3]['status'], 'enrolled')
        with unittest.mock.patch.object(self.worker.adapter, 'request', wraps=self.worker.adapter.request) as request:
            verified = self.service.verify_connection()
            request.assert_called_once_with(None)
        self.assertTrue(verified['connectionVerified'])
        self.assertTrue(verified['simulated'])
        self.assertFalse(verified['physicalIdentityConfirmed'])

    def test_invalid_device_readback_not_verified(self):
        for state in ({}, {'brightness': True, 'warmth': 50}, {'brightness': 101, 'warmth': 50}):
            with unittest.mock.patch.object(self.worker, 'request', return_value=state):
                with self.assertRaises(ValueError): self.service.verify_connection()

