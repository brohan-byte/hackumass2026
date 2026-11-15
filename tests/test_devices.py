import copy
import io
import json
import re
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ghostui_backend.ar_layout import ARLayoutService
from ghostui_backend.contracts import numeric_limits, validate_command
from ghostui_backend.devices import DeviceManager, DeviceSelectionError
from ghostui_backend.generation import template
from ghostui_backend.recognition import RecognitionService
from ghostui_backend.server import handler_for


class FakeWorker:
    """Persistent fake hardware, independently keyed by transport address."""
    def __init__(self, address, simulated, integration, hardware):
        self.integration_id = integration
        self.simulated = simulated or integration == 'demo-light'
        self.adapter = SimpleNamespace(address=address)
        self.hardware = hardware
        self.address = address
        self.closed = False
        if address == 'unreachable': raise OSError('Cannot reach device')
        reported = hardware.get(address, {}).get('identity', integration + ':' + str(address))
        if integration == 'marshall': reported = 'speaker-1'
        self.capabilities = {'deviceId': reported, 'name': integration, 'controls': [
            {'id': 'brightness', 'type': 'number', 'label': 'Brightness', 'min': 0, 'max': 100, 'step': 1}]}
        self.limits = numeric_limits(self.capabilities)
        hardware.setdefault(address, {'value': 30})

    def discover(self):
        self.adapter.address = self.address = 'discovered'
        self.hardware.setdefault(self.address, {'value': 30})

    def request(self, change=None):
        if self.closed: raise AssertionError('Used closed worker')
        if change:
            validate_command(self.limits, change)
            self.hardware[self.address]['value'] = change[1]
        return {'brightness': self.hardware[self.address]['value']}

    def close(self): self.closed = True


class DeviceRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hardware = {}
        self.factory = lambda address, simulated, integration: FakeWorker(address, simulated, integration, self.hardware)
        self.manager = DeviceManager(self.root, self.factory)
        self.addCleanup(self.manager.close)
        self.Handler = handler_for(None, 8780, 'test-phone', manager=self.manager)

    def call(self, path, body=None, authenticated=True, headers=None):
        obj = object.__new__(self.Handler)
        obj.path = path
        data = json.dumps(body).encode()
        obj.headers = {'Host': '127.0.0.1:8780', 'Content-Length': str(len(data)), **(headers or {})}
        if authenticated: obj.headers['Authorization'] = 'Bearer test-phone'
        obj.rfile = io.BytesIO(data)
        obj.reply = reply = Mock()
        (obj.do_GET if body is None else obj.do_POST)()
        args, kwargs = reply.call_args
        return args[0], args[1] if len(args) > 1 else kwargs.get('code', 200)

    def add(self, address='one', integration='wled', **kwargs):
        result = self.manager.register(integration, address, **kwargs)
        return result['activeDeviceId']

    def test_empty_server_pairs_without_a_device(self):
        self.assertEqual(self.call('/mobile/devices', authenticated=False)[1], 401)
        listing, code = self.call('/mobile/devices')
        self.assertEqual((code, listing['devices'], listing['activeDeviceId']), (200, [], None))
        self.assertIn('homeassistant', [x['id'] for x in listing['integrations']])
        self.assertEqual(self.call('/mobile/state')[1], 409)
        self.assertIn('GhostUI is ready', self.call('/')[0])

    def test_registry_survives_restart_and_restores_the_same_id(self):
        instance = self.add(name='Desk light')
        self.manager.close()
        restored = DeviceManager(self.root, self.factory)
        self.addCleanup(restored.close)
        self.assertEqual(restored.last_selected, instance)
        self.assertEqual(restored.listing()['devices'][0]['status'], 'saved')
        restored.select(instance)
        self.assertEqual(restored.active.worker.capabilities['deviceId'], instance)
        self.assertEqual(restored.active.worker.capabilities['name'], 'Desk light')
        self.assertEqual(self.manager.path.stat().st_mode & 0o777, 0o600)

    def test_two_devices_keep_enrollment_and_layout_separate(self):
        one = self.add('one')
        first = self.manager.active
        first.recognition.folder.mkdir(parents=True)
        (first.recognition.folder / 'view-0.json').write_text('{}')
        layout = {'source': 'ai', 'layout': template(first.worker.capabilities), 'notice': 'Gemini'}
        with patch('ghostui_backend.ar_layout.generate', return_value=layout):
            first.layout.resolve()
        two = self.add('two')
        self.assertNotEqual(one, two)
        self.assertEqual(self.manager.active.recognition.status()['views'], 0)
        self.assertEqual(self.manager.active.layout.current()['source'], 'template')
        self.manager.select(one)
        self.assertEqual(self.manager.active.recognition.status()['views'], 1)
        self.assertEqual(self.manager.active.layout.current()['source'], 'ai')

    def test_stale_ar_commands_and_enrollment_cannot_target_new_selection(self):
        one = self.add('one')
        two = self.add('two')
        before = self.hardware['two']['value']
        for suffix, body in [('command', {'capability': 'brightness', 'value': 87}),
                             ('vision/clear', {}), ('layout', {'refresh': True})]:
            with patch('ghostui_backend.ar_layout.generate') as generate:
                self.assertEqual(self.call(f'/mobile/devices/{one}/{suffix}', body)[1], 409)
                generate.assert_not_called()
        self.assertEqual(self.call('/mobile/command', {'capability': 'brightness', 'value': 87})[1], 409)
        self.assertEqual(self.hardware['two']['value'], before)
        state, code = self.call(f'/mobile/devices/{two}/command', {'capability': 'brightness', 'value': 61})
        self.assertEqual((code, state['brightness']), (200, 61))
        self.assertEqual(self.hardware['one']['value'], 30)

    def test_register_select_and_scoped_layout_routes(self):
        result, code = self.call('/mobile/devices', {'integrationId': 'wled', 'address': 'one', 'name': 'Desk'})
        self.assertEqual(code, 200)
        one = result['activeDeviceId']
        two = self.add('two')
        selected, code = self.call(f'/mobile/devices/{one}/select', {})
        self.assertEqual((code, selected['activeDeviceId']), (200, one))
        caps, code = self.call(f'/mobile/devices/{one}/capabilities')
        self.assertEqual((code, caps['deviceId'], caps['name']), (200, one, 'Desk'))
        layout = self.call(f'/mobile/devices/{one}/layout')[0]
        self.assertEqual(layout['deviceId'], one)
        self.assertEqual(self.call(f'/mobile/devices/{two}/state')[1], 409)
        self.assertEqual(self.call('/mobile/devices/missing/state')[1], 404)
        self.assertEqual(self.call(f'/mobile/devices/{one}/onboarding')[0]['scope'], 'saved-devices-one-active')

    def test_old_browser_token_rejected_after_selection(self):
        one = self.add('one')
        page = self.call('/')[0]
        token = re.search("const token='([^']+)'", page)[1]
        gen_token = re.search("generationToken='([^']+)'", page)[1]
        self.add('two')
        self.assertEqual(self.call('/command', {'capability': 'brightness', 'value': 70},
                                   headers={'X-GhostUI-Token': token})[1], 403)
        self.assertEqual(self.call('/generate', {'preference': ''},
                                   headers={'X-Generation-Token': gen_token})[1], 403)
        self.manager.select(one)
        self.assertEqual(self.call('/command', {'capability': 'brightness', 'value': 70},
                                   headers={'X-GhostUI-Token': token})[1], 403)

    def test_unreachable_selected_device_is_offline_and_can_recover(self):
        one = self.add('one')
        worker = self.manager.active.worker
        with patch.object(worker, 'request', side_effect=OSError('Disconnected')):
            self.assertEqual(self.call(f'/mobile/devices/{one}/onboarding/verify', {})[1], 503)
        listing = self.call('/mobile/devices')[0]
        self.assertEqual(listing['devices'][0]['status'], 'offline')
        self.assertEqual(self.call(f'/mobile/devices/{one}/onboarding/verify', {})[1], 200)
        self.assertEqual(self.call('/mobile/devices')[0]['devices'][0]['status'], 'connected')

    def test_failed_add_preserves_active_device_and_disk(self):
        one = self.add()
        original = self.manager.path.read_bytes()
        with self.assertRaises(OSError): self.add('unreachable')
        self.assertEqual(self.manager.listing()['activeDeviceId'], one)
        self.assertEqual(self.manager.path.read_bytes(), original)
        self.assertFalse(self.manager.active.worker.closed)

    def test_changed_address_reuses_identity_but_wrong_device_is_not_selected(self):
        self.hardware['old'] = {'identity': 'mac:one', 'value': 30}
        one = self.add('old')
        self.hardware['new'] = {'identity': 'mac:one', 'value': 30}
        self.assertEqual(self.add('new'), one)
        self.assertEqual(len(self.manager.records), 1)
        self.add('two')
        self.hardware['new']['identity'] = 'mac:stranger'
        with self.assertRaisesRegex(ValueError, 'different device'): self.manager.select(one)
        self.assertEqual(self.manager.listing()['devices'][0]['status'], 'offline')
        self.assertNotEqual(self.manager.listing()['activeDeviceId'], one)

    def test_legacy_speaker_enrollment_and_gemini_layout_are_preserved(self):
        old_vision = RecognitionService('speaker-1', self.root / 'vision')
        old_vision.folder.mkdir(parents=True)
        view = old_vision.folder / 'view-0.json'
        view.write_text('{"box":[0,0,1,1]}')
        reported = self.factory('speaker-address', False, 'marshall').capabilities
        old_layout = ARLayoutService(reported, self.root / 'ar-layouts')
        result = {'layout': template(reported), 'source': 'ai', 'notice': 'Gemini'}
        with patch('ghostui_backend.ar_layout.generate', return_value=result): old_layout.resolve()
        one = self.add('speaker-address', integration='marshall')
        self.assertEqual(self.manager.active.recognition.status()['views'], 1)
        self.assertEqual(self.manager.active.layout.current()['source'], 'ai')
        self.assertEqual(self.manager.active.layout.current()['deviceId'], one)
        self.assertTrue(view.exists())
        self.assertTrue(old_layout.path.exists())
        self.add('second-speaker', integration='marshall')
        self.assertEqual(self.manager.active.recognition.status()['views'], 0)
        self.assertEqual(self.manager.active.layout.current()['source'], 'template')

    def test_homeassistant_identity_is_namespaced_by_server(self):
        with patch.dict('os.environ', {'HOMEASSISTANT_URL': 'http://first:8123'}):
            one = self.add('light.desk', integration='homeassistant')
        with patch.dict('os.environ', {'HOMEASSISTANT_URL': 'http://second:8123'}):
            two = self.add('light.desk', integration='homeassistant')
            self.assertNotEqual(one, two)
            with self.assertRaisesRegex(ValueError, 'saved Home Assistant server'):
                self.manager.select(one)

    def test_invalid_registration_is_not_persisted(self):
        for body in ({}, {'integrationId': []}, {'integrationId': 'guessed'},
                     {'integrationId': 'wled', 'simulated': 1},
                     {'integrationId': 'wled', 'address': 'http://user:secret@device'},
                     {'integrationId': 'wled', 'name': ' '},
                     {'integrationId': 'wled', 'unexpected': 1}):
            self.assertEqual(self.call('/mobile/devices', body)[1], 400)
        self.assertFalse(self.manager.path.exists())

    def test_save_failure_does_not_close_current_connection(self):
        self.add('one')
        current = self.manager.active
        with patch.object(self.manager, '_save', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError): self.add('two')
        self.assertIs(self.manager.active, current)
        self.assertFalse(current.worker.closed)
        self.assertEqual(len(self.manager.records), 1)

    def test_requests_hold_selection_until_completion(self):
        one = self.add('one')
        two = self.add('two')
        started, completed = threading.Event(), threading.Event()
        def switch():
            started.set()
            self.manager.select(one)
            completed.set()
        with self.manager.session(two) as session:
            thread = threading.Thread(target=switch)
            thread.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(completed.wait(0.05))
            self.assertFalse(session.worker.closed)
        thread.join(2)
        self.assertTrue(completed.is_set())
        with self.assertRaises(DeviceSelectionError):
            with self.manager.session(two): pass

    def test_real_http_empty_pairing_and_registration(self):
        http = ThreadingHTTPServer(('127.0.0.1', 0), self.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        connection = HTTPConnection('127.0.0.1', http.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.request('POST', '/mobile/devices', json.dumps({'integrationId': 'wled', 'address': 'one'}),
                           {'Authorization': 'Bearer test-phone', 'Content-Type': 'application/json'})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        instance = json.loads(response.read())['activeDeviceId']
        connection.request('GET', f'/mobile/devices/{instance}/capabilities', headers={'Authorization': 'Bearer test-phone'})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())['deviceId'], instance)


class RealSimulatedWorkerTests(unittest.TestCase):
    def test_default_worker_factory_supports_selection_and_restart(self):
        with TemporaryDirectory() as root:
            manager = DeviceManager(root)
            try:
                one = manager.register('marshall', simulated=True)['activeDeviceId']
                two = manager.register('demo-light')['activeDeviceId']
                self.assertNotEqual(one, two)
                manager.select(one)
                self.assertEqual(manager.active.worker.request(('volume', 8))['volume'], 8)
            finally: manager.close()
            manager = DeviceManager(root)
            try:
                manager.select(manager.last_selected)
                self.assertEqual(manager.active.worker.capabilities['deviceId'], one)
                self.assertTrue(manager.active.worker.simulated)
            finally: manager.close()
