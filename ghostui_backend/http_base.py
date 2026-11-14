"""Local browser routes and command validation; independent of device protocol."""
import json
import secrets
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
PAGE = (Path(__file__).parent / 'web/index.html').read_text()

def make_handler(adapter, port):
    token = secrets.token_urlsafe(32)
    allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
    allowed_origins = {'http://' + host for host in allowed_hosts}

    class Handler(BaseHTTPRequestHandler):
        def reply(self, body, code=200, html=False):
            data = body.encode() if html else json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def trusted(self):
            if self.headers.get('Host') not in allowed_hosts:
                self.reply({'error': 'Unrecognized host'}, 403)
                return False
            origin = self.headers.get('Origin')
            if origin and origin not in allowed_origins:
                self.reply({'error': 'Unrecognized origin'}, 403)
                return False
            return True

        def do_GET(self):
            if not self.trusted():
                return
            path = urlparse(self.path).path
            if path == '/':
                self.reply(PAGE.replace('__TOKEN__', token), html=True)
            elif path == '/capabilities':
                self.reply({**adapter.capabilities, 'simulated': adapter.simulated})
            elif path == '/state':
                self.run_device()
            else:
                self.reply({'error': 'Not found'}, 404)

        def run_device(self, change=None):
            try:
                self.reply(adapter.request(change))
            except Exception as exc:
                self.reply({'error': str(exc) or type(exc).__name__}, 503)

        def do_POST(self):
            if not self.trusted():
                return
            if urlparse(self.path).path != '/command':
                return self.reply({'error': 'Not found'}, 404)
            if self.headers.get('X-GhostUI-Token') != token:
                return self.reply({'error': 'Missing or invalid session token'}, 403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024:
                    raise ValueError('Invalid body size')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or set(data) != {'capability', 'value'}:
                    raise ValueError('Expected capability and value only')
                field, value = data['capability'], data['value']
                if not isinstance(field, str) or field not in adapter.limits:
                    raise ValueError('Unknown capability')
                lo, hi = adapter.limits[field]
                if type(value) is not int or not lo <= value <= hi:
                    raise ValueError(f'Expected an integer in {lo}..{hi}')
            except (ValueError, TypeError) as exc:
                return self.reply({'error': str(exc)}, 400)
            self.run_device((field, value))

    return Handler
