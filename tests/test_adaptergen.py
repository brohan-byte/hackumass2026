import io
import json
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from ghostui_backend.adaptergen import main, render
from ghostui_backend.integrations.wled import GeneratedAdapter
from ghostui_backend.service import DeviceWorker

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/adaptergen'


class AdapterGenerationTests(unittest.TestCase):
    def test_doc_extraction_to_loadable_module(self):
        binding = json.loads((EXAMPLE / 'wled.json').read_text())
        with TemporaryDirectory() as temp, patch.dict('os.environ', {'GEMINI_API_KEY': 'test'}):
            output = Path(temp, 'candidate.py')
            with patch('ghostui_backend.adaptergen.gemini_json', return_value=binding) as extract:
                with redirect_stdout(io.StringIO()):
                    main(['--docs', str(EXAMPLE / 'wled-api.md'), '--output', str(output)])
                self.assertIn('GET /json/info', extract.call_args.args[0])
            self.assertEqual(output.read_text(), (ROOT / 'ghostui_backend/integrations/wled.py').read_text())
        with self.assertRaises(ValueError):
            render({**binding, 'state_path': '//another-host/secret'})

    def test_catalog_adapter_over_http(self):
        state = {'on': False, 'bri': 127}
        writes = []
        class Ring(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, obj):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(obj).encode())

            def do_GET(self):
                if self.path == '/json/info':
                    self.reply({'brand': 'WLED', 'name': 'Desk ring', 'mac': '000102030405'})
                elif self.path == '/json/state':
                    self.reply(state)
                else:
                    self.send_error(404)

            def do_POST(self):
                if self.path != '/json/state':
                    return self.send_error(404)
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                writes.append(payload)
                state.update(payload)
                self.reply({'success': True})

        server = HTTPServer(('127.0.0.1', 0), Ring)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        worker = DeviceWorker(f'127.0.0.1:{server.server_port}', device='wled')
        self.addCleanup(worker.close)
        self.assertEqual(worker.capabilities['deviceId'], 'wled:000102030405')
        self.assertEqual(worker.request(), {'brightness': 0})
        for percent in (1, 40, 100, 0):
            self.assertEqual(worker.request(('brightness', percent)), {'brightness': percent})
        self.assertEqual(writes, [{'bri': 3, 'on': True}, {'bri': 102, 'on': True},
                                  {'bri': 255, 'on': True}, {'on': False}])

    def test_refuse_other_endpoints(self):
        with patch.object(GeneratedAdapter, '_call', return_value={'brand': 'unrelated'}) as call:
            with self.assertRaisesRegex(ValueError, 'identity'):
                GeneratedAdapter('desk-ring.local')
            call.assert_called_once_with('/json/info')
