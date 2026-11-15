import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ghostui_backend.ar_layout import ARLayoutService
from ghostui_backend.generation import template
from ghostui_backend.integrations.demo_light import DemoLightAdapter


class ARLayoutTests(unittest.TestCase):
    def setUp(self):
        self.storage = TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.capabilities = DemoLightAdapter().capabilities
        self.service = ARLayoutService(self.capabilities, self.storage.name)
        self.layout = template(self.capabilities)
        self.layout['title'] = 'Desk lighting'
        self.layout['controls'].reverse()
        self.layout['controls'][0]['label'] = 'Warm glow'
        self.result = {'layout': self.layout, 'source': 'ai', 'notice': 'Gemini validated'}

    def test_reordered_layout_persists_and_reopens_without_generation(self):
        with patch('ghostui_backend.ar_layout.generate', return_value=self.result) as generate:
            first = self.service.resolve()
            self.assertFalse(first['cached'])
            self.assertEqual(first['deviceId'], self.capabilities['deviceId'])
            self.assertEqual(first['layout']['controls'][0]['bind'], 'warmth')
            reopened = ARLayoutService(self.capabilities, self.storage.name).resolve()
            self.assertTrue(reopened['cached'])
            self.assertEqual(reopened['layout'], self.layout)
            self.assertEqual(reopened['deviceId'], self.capabilities['deviceId'])
            generate.assert_called_once()

    def test_device_and_capability_changes_do_not_reuse_layout(self):
        different = copy.deepcopy(self.capabilities)
        different['controls'][0]['max'] = 200
        self.assertNotEqual(self.service.path, ARLayoutService(different, self.storage.name).path)
        different['deviceId'] = 'another-light'
        self.assertNotEqual(self.service.path, ARLayoutService(different, self.storage.name).path)

    def test_offline_fallback_is_explicit_and_does_not_replace_saved_ai(self):
        fallback = {'layout': template(self.capabilities), 'source': 'template', 'notice': 'Offline'}
        with patch('ghostui_backend.ar_layout.generate', return_value=fallback):
            self.assertEqual(self.service.resolve()['source'], 'template')
            self.assertFalse(self.service.path.exists())
        with patch('ghostui_backend.ar_layout.generate', return_value=self.result):
            self.service.resolve()
        with patch('ghostui_backend.ar_layout.generate', return_value=fallback):
            self.assertEqual(self.service.resolve(refresh=True)['layout'], self.layout)
            self.assertEqual(self.service.current()['source'], 'ai')

    def test_invalid_binding_is_not_saved_and_corrupt_cache_falls_back(self):
        invalid = copy.deepcopy(self.result)
        invalid['layout']['controls'][0]['bind'] = 'invented'
        with patch('ghostui_backend.ar_layout.generate', return_value=invalid):
            with self.assertRaises(ValueError): self.service.resolve()
        self.assertFalse(self.service.path.exists())
        self.service.path.write_text('[]')
        self.assertEqual(self.service.current()['source'], 'template')
