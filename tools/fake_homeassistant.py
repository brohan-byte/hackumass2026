"""A tiny stand-in for Home Assistant's REST API, for tests and offline demos.

It is not Home Assistant. It implements only what the GhostUI adapter uses:
GET /api/, GET /api/states, GET /api/states/<entity>, and
POST /api/services/<domain>/<service> for the services below. Its entities
include some the adapter must refuse (an on/off-only light, a 3-speed fan).

Run it:   python tools/fake_homeassistant.py            (port 8123, token dev-token)
Then:     HOMEASSISTANT_URL=http://127.0.0.1:8123  HOMEASSISTANT_TOKEN=dev-token
          python app.py --device homeassistant light.ceiling_lights
"""
import argparse
import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ENTITIES = {
    'light.ceiling_lights': {'state': 'on', 'attributes': {
        'friendly_name': 'Ceiling Lights', 'brightness': 180,
        'supported_color_modes': ['color_temp', 'hs'], 'supported_features': 0}},
    'light.porch_switch': {'state': 'off', 'attributes': {
        'friendly_name': 'Porch Switch', 'supported_color_modes': ['onoff'], 'supported_features': 0}},
    'media_player.living_room': {'state': 'playing', 'attributes': {
        'friendly_name': 'Living Room Speaker', 'volume_level': 0.4, 'supported_features': 4 | 8}},
    'fan.desk_fan': {'state': 'on', 'attributes': {
        'friendly_name': 'Desk Fan', 'percentage': 30, 'percentage_step': 1, 'supported_features': 1}},
    'fan.box_fan': {'state': 'on', 'attributes': {
        'friendly_name': 'Box Fan (3 speeds)', 'percentage': 67, 'percentage_step': 100 / 3,
        'supported_features': 1}},
}


def make_handler(token, entities, lock):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            if self.headers.get('Authorization') != 'Bearer ' + token:
                self.send(401, {'message': 'Invalid access token'})
                return False
            return True

        def state(self, entity_id):
            return {'entity_id': entity_id, **copy.deepcopy(entities[entity_id])}

        def do_GET(self):
            if not self.authorized():
                return
            if self.path == '/api/':
                return self.send(200, {'message': 'API running.'})
            with lock:
                if self.path == '/api/states':
                    return self.send(200, [self.state(e) for e in entities])
                if self.path.startswith('/api/states/'):
                    entity_id = self.path[len('/api/states/'):]
                    if entity_id in entities:
                        return self.send(200, self.state(entity_id))
            self.send(404, {'message': 'Entity not found.'})

        def do_POST(self):
            if not self.authorized():
                return
            parts = self.path.strip('/').split('/')
            if len(parts) != 4 or parts[:2] != ['api', 'services']:
                return self.send(404, {'message': 'Not found'})
            domain, service = parts[2], parts[3]
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
            entity_id = body.get('entity_id')
            with lock:
                if entity_id not in entities or not entity_id.startswith(domain + '.'):
                    return self.send(400, {'message': 'Unknown entity for this domain'})
                e = entities[entity_id]
                a = e['attributes']
                if (domain, service) == ('light', 'turn_on'):
                    e['state'] = 'on'
                    if 'onoff' not in a.get('supported_color_modes', []):
                        a['brightness'] = max(1, min(255, int(body.get('brightness', a.get('brightness') or 255))))
                elif (domain, service) == ('light', 'turn_off'):
                    e['state'] = 'off'
                    a['brightness'] = None
                elif (domain, service) == ('media_player', 'volume_set'):
                    a['volume_level'] = max(0.0, min(1.0, float(body['volume_level'])))
                elif (domain, service) == ('fan', 'set_percentage'):
                    step = a.get('percentage_step') or 1
                    # Real fans snap to their supported speeds.
                    a['percentage'] = min(100, round(round(body['percentage'] / step) * step))
                    e['state'] = 'on' if a['percentage'] else 'off'
                elif (domain, service) == ('fan', 'turn_off'):
                    e['state'] = 'off'
                    a['percentage'] = 0
                else:
                    return self.send(400, {'message': f'Service {domain}.{service} not supported'})
                return self.send(200, [self.state(entity_id)])

    return Handler


def start(port=0, token='dev-token'):
    """Start in a background thread; returns (server, url). Fresh state per call."""
    server = ThreadingHTTPServer(('127.0.0.1', port),
                                 make_handler(token, copy.deepcopy(ENTITIES), threading.Lock()))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_address[1]}'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--port', type=int, default=8123)
    parser.add_argument('--token', default='dev-token')
    args = parser.parse_args()
    server, url = start(args.port, args.token)
    print(f'Fake Home Assistant at {url} (token: {args.token}). Ctrl+C to stop.', flush=True)
    print('Entities: ' + ', '.join(ENTITIES), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()
