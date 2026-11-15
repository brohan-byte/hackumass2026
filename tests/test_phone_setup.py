import copy
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
import unittest
from unittest.mock import Mock, patch

from ghostui_backend.devices import DeviceManager
from ghostui_backend.onboarding.discovery import controller_address, probe_wled
from ghostui_backend.onboarding.documented import APIDocumentation
from ghostui_backend.onboarding.setup import DeviceSetupService, SetupBusy
from ghostui_backend.server import handler_for

ROOT = Path(__file__).resolve().parents[1]
BINDING = json.loads((ROOT/'examples/adaptergen/wled.json').read_text())


class PhoneSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.mac = '001122334455'
        self.brand = 'WLED'
        self.state = {'on': True, 'bri': 128}
        self.writes = []
        owner = self
        class Light(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def reply(self, value):
                raw = json.dumps(value).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
            def do_GET(self):
                if self.path == '/json/info': self.reply({'name': 'Desk ring', 'brand': owner.brand, 'mac': owner.mac})
                elif self.path == '/json/state': self.reply(owner.state)
                else: self.send_error(404)
            def do_POST(self):
                if self.path != '/json/state': return self.send_error(404)
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.writes.append(body); owner.state.update(body); self.reply({'success': True})
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Light)
        Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close); self.addCleanup(self.http.shutdown)
        self.address = f'127.0.0.1:{self.http.server_port}'
        self.manager = DeviceManager(self.temp.name); self.addCleanup(self.manager.close)
        self.service = DeviceSetupService(self.manager)
        self.candidate = {'address': self.address, 'name': 'Desk ring', 'mac': self.mac,
                          'family': 'wled', 'documentation': 'https://kno.wled.ge/interfaces/json-api/'}
        patches = [
            patch('ghostui_backend.onboarding.setup.discover_wled', return_value=[self.candidate]),
            patch('ghostui_backend.onboarding.documented.fetch_documentation',
                  return_value=APIDocumentation(self.candidate['documentation'], 'Public WLED API specification')),
            patch('ghostui_backend.adaptergen.gemini_json', return_value=copy.deepcopy(BINDING)),
            patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}),
            patch('ghostui_backend.ar_layout.generate', return_value={'source': 'ai', 'notice': 'Generated',
                  'layout': {'title': 'Desk ring', 'controls': [{'bind': 'brightness', 'label': 'Brightness',
                              'widget': 'slider', 'group': 'Light'}]}}),
        ]
        self.discovery, self.fetch, self.gemini, _, self.layout = [p.start() for p in patches]
        for p in patches: self.addCleanup(p.stop)
        self.Handler = handler_for(None, 8780, 'phone', manager=self.manager)

    def wait(self, id_):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.service.status(id_)
            if result['status'] != 'running': return result
            Event().wait(.01)
        self.fail('Setup job did not finish')

    def candidate_id(self): return self.service.discover()['devices'][0]['id']

    def call(self, path, body=None, auth=True):
        handler = object.__new__(self.Handler); handler.path = path
        raw = json.dumps(body).encode(); handler.rfile = io.BytesIO(raw)
        handler.headers = {'Content-Length': str(len(raw))}
        if auth: handler.headers['Authorization'] = 'Bearer phone'
        handler.reply = Mock()
        (handler.do_GET if body is None else handler.do_POST)()
        args = handler.reply.call_args.args
        return args[0], args[1] if len(args)>1 else 200

    def test_phone_discovery_generation_registration_and_real_http_write(self):
        result, code = self.call('/mobile/setup/discover', {})
        self.assertEqual(code, 200)
        self.assertEqual(set(result['devices'][0]), {'id', 'name'})
        self.assertNotIn(self.address, json.dumps(result))
        self.assertNotIn('documentation', json.dumps(result))
        job, code = self.call('/mobile/setup/start', {'candidateId': result['devices'][0]['id']})
        self.assertEqual(code, 200)
        deadline = time.monotonic() + 5
        while job['status'] == 'running' and time.monotonic()<deadline:
            Event().wait(.01)
            job, code = self.call('/mobile/setup/jobs/'+job['id'])
        self.assertEqual(job['status'], 'ready', job)
        id_ = job['deviceId']; record = self.manager.records[id_]
        self.assertEqual(record['integrationId'], 'generated-http')
        self.assertEqual(record['adapterProvenance']['discovery']['mac'], self.mac)
        self.assertEqual(self.writes, [])
        self.gemini.assert_called_once(); self.layout.assert_called_once()
        self.assertEqual(self.manager.active.layout.current()['source'], 'ai')
        registration, _ = self.call('/mobile/registration')
        self.assertEqual(registration['devices'], [{'id': id_, 'name': 'Desk ring'}])
        state, code = self.call('/mobile/devices/'+id_+'/command', {'capability': 'brightness', 'value': 40})
        self.assertEqual((code, state), (200, {'brightness': 40}))
        self.assertEqual(self.writes, [{'bri': 102, 'on': True}])

    def test_saved_generated_connection_reuses_mapping_and_layout(self):
        candidate = self.candidate_id()
        first = self.wait(self.service.start(candidate)['id'])
        self.assertEqual(first['status'], 'ready', first)
        again = self.wait(self.service.start(candidate)['id'])
        self.assertEqual(again['deviceId'], first['deviceId'])
        self.assertEqual(len(self.manager.records), 1)
        self.gemini.assert_called_once(); self.fetch.assert_called_once(); self.layout.assert_called_once()
        self.assertEqual(self.writes, [])

    def test_changed_identity_before_or_during_generation_is_never_saved(self):
        candidate = self.candidate_id()
        self.mac = 'aabbccddeeff'
        result = self.wait(self.service.start(candidate)['id'])
        self.assertEqual(result['status'], 'failed'); self.gemini.assert_not_called()
        self.mac = self.candidate['mac']
        def swap(*args):
            self.mac = 'aabbccddeeff'
            return copy.deepcopy(BINDING)
        self.gemini.side_effect = swap
        result = self.wait(self.service.start(candidate)['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(self.manager.path.exists()); self.assertEqual(self.writes, [])

    def test_failed_generation_is_retryable_without_builtin_adapter_fallback(self):
        candidate = self.candidate_id()
        self.gemini.side_effect = TimeoutError()
        result = self.wait(self.service.start(candidate)['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertIsNone(self.manager.active); self.assertFalse(self.manager.path.exists())
        self.gemini.side_effect = None
        result = self.wait(self.service.start(candidate)['id'])
        self.assertEqual(result['status'], 'ready', result)

    def test_duplicate_start_does_not_generate_twice_and_other_start_is_busy(self):
        gate = Event(); entered = Event()
        def delayed(*args):
            entered.set(); gate.wait(3)
            return copy.deepcopy(BINDING)
        self.gemini.side_effect = delayed
        candidate = self.candidate_id()
        first = self.service.start(candidate)
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.service.start(candidate)['id'], first['id'])
            with self.assertRaises(SetupBusy): self.service.start('another-device')
        finally: gate.set()
        self.assertEqual(self.wait(first['id'])['status'], 'ready')
        self.gemini.assert_called_once()

    def test_authentication_opaque_candidates_expiry_and_read_only_probing(self):
        for path, body in [('/mobile/setup/discover', {}), ('/mobile/setup/start', {'candidateId': 'x'}),
                           ('/mobile/setup/jobs/x', None)]:
            self.assertEqual(self.call(path, body, auth=False)[1], 401)
        self.assertEqual(self.call('/mobile/setup/start', {'address': self.address})[1], 400)
        self.assertEqual(self.call('/mobile/setup/start', {'candidateId': 'invented'})[1], 404)
        candidate = self.candidate_id()
        self.service.candidates[candidate]['seenAt'] -= 301
        with self.assertRaises(KeyError): self.service.start(candidate)
        self.assertEqual(probe_wled(self.address)['mac'], self.mac)
        self.assertEqual(self.writes, [])
        self.brand = 'Other'
        with self.assertRaises(ValueError): probe_wled(self.address)
        self.assertEqual(controller_address('192.168.1.3', 8080), '192.168.1.3:8080')
        for host in ('127.0.0.1', '8.8.8.8', '0.0.0.0', '224.0.0.1'):
            with self.assertRaises(ValueError): controller_address(host)
