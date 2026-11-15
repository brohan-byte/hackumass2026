import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
import fake_homeassistant  # noqa: E402

from ghostui_backend.contracts import numeric_limits  # noqa: E402
from ghostui_backend.integrations.homeassistant import (  # noqa: E402
    HomeAssistantAdapter, HomeAssistantClient, HomeAssistantError, supported_entities)
from ghostui_backend.service import DeviceWorker  # noqa: E402


class HomeAssistantTests(unittest.TestCase):
    def setUp(self):
        self.server, self.url = fake_homeassistant.start(token='test-token')
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.client = HomeAssistantClient(self.url, 'test-token')
        env = patch.dict(os.environ, {'HOMEASSISTANT_URL': self.url, 'HOMEASSISTANT_TOKEN': 'test-token'})
        env.start()
        self.addCleanup(env.stop)

    def adapter(self, entity):
        return HomeAssistantAdapter(entity, client=self.client)

    def test_light_through_device_worker_confirms_readback(self):
        worker = DeviceWorker('light.ceiling_lights', False, 'homeassistant')
        self.addCleanup(worker.close)
        caps = worker.capabilities
        self.assertEqual((caps['deviceId'], caps['name']), ('ha.light.ceiling_lights', 'Ceiling Lights'))
        self.assertEqual(worker.limits, {'brightness': (0, 100)})
        self.assertEqual(worker.request(), {'brightness': 71})  # 180/255
        self.assertEqual(worker.request(('brightness', 25)), {'brightness': 25})
        self.assertEqual(worker.request(('brightness', 0)), {'brightness': 0})  # turns off
        self.assertEqual(worker.request(('brightness', 100)), {'brightness': 100})

    def test_every_light_percentage_round_trips_exactly(self):
        light = self.adapter('light.ceiling_lights')
        for value in range(101):
            self.assertEqual(light.request(('brightness', value)), {'brightness': value}, value)

    def test_media_player_volume(self):
        speaker = self.adapter('media_player.living_room')
        self.assertEqual(speaker.capabilities['controls'][0]['id'], 'volume')
        self.assertEqual(speaker.request(), {'volume': 40})
        for value in (0, 29, 57, 100):
            self.assertEqual(speaker.request(('volume', value)), {'volume': value})

    def test_fan_with_one_percent_steps(self):
        fan = self.adapter('fan.desk_fan')
        self.assertEqual(fan.request(('speed', 55)), {'speed': 55})
        self.assertEqual(fan.request(('speed', 0)), {'speed': 0})

    def test_manifests_satisfy_shared_contract(self):
        for entity in ('light.ceiling_lights', 'media_player.living_room', 'fan.desk_fan'):
            numeric_limits(self.adapter(entity).capabilities)

    def test_unsupported_entities_are_refused_not_guessed(self):
        for entity in ('light.porch_switch', 'fan.box_fan'):
            with self.assertRaisesRegex(HomeAssistantError, 'no control GhostUI supports'):
                self.adapter(entity)
        ids = [e for e, _, _ in supported_entities(self.client)]
        self.assertEqual(ids, ['fan.desk_fan', 'light.ceiling_lights', 'media_player.living_room'])

    def test_missing_entity_lists_choices_instead_of_picking_one(self):
        with self.assertRaises(HomeAssistantError) as ctx:
            self.adapter(None)
        self.assertIn('light.ceiling_lights', str(ctx.exception))
        self.assertNotIn('light.porch_switch', str(ctx.exception))

    def test_bad_inputs_and_connection_errors(self):
        with self.assertRaisesRegex(HomeAssistantError, 'Not a Home Assistant entity'):
            self.adapter('../config/core.entries')
        with self.assertRaisesRegex(HomeAssistantError, 'has no'):
            self.adapter('light.does_not_exist')
        with self.assertRaisesRegex(HomeAssistantError, 'rejected the access token'):
            HomeAssistantAdapter('light.ceiling_lights', client=HomeAssistantClient(self.url, 'wrong'))
        with self.assertRaisesRegex(HomeAssistantError, 'Cannot reach'):
            HomeAssistantAdapter('light.ceiling_lights',
                                 client=HomeAssistantClient('http://127.0.0.1:9', 'x', timeout=2))
        with patch.dict(os.environ, {'HOMEASSISTANT_TOKEN': ''}):
            with self.assertRaisesRegex(HomeAssistantError, 'HOMEASSISTANT_TOKEN'):
                HomeAssistantAdapter('light.ceiling_lights')
        with self.assertRaisesRegex(HomeAssistantError, 'no --simulate'):
            HomeAssistantAdapter('light.ceiling_lights', simulated=True, client=self.client)

    def test_unknown_capability_rejected_by_adapter(self):
        with self.assertRaises(HomeAssistantError):
            self.adapter('light.ceiling_lights').request(('volume', 5))


if __name__ == '__main__':
    unittest.main()
