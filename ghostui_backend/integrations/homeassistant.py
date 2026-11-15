"""Home Assistant adapter: one integration for any entity GhostUI can map.

GhostUI never talks to the physical device here. It asks Home Assistant over
its REST API, and Home Assistant talks to the device through whichever of its
own integrations owns it (WLED, Hue, Sonos, demo devices, ...).

Configuration comes from the environment or the root .env:
  HOMEASSISTANT_URL    default http://localhost:8123
  HOMEASSISTANT_TOKEN  a long-lived access token (Profile > Security)
The entity is the device address:
  python app.py --device homeassistant light.ceiling_lights

The shared contract only supports integer sliders, so each entity exposes one
percentage control. Entities without a control we can map exactly are refused,
never guessed, and every write is confirmed by DeviceWorker's read-back.
"""
import json
import os
import re
import urllib.error
import urllib.request

ENTITY_ID = re.compile(r'^[a-z_]+\.[a-z0-9_]+$')
MEDIA_VOLUME_SET = 4   # MediaPlayerEntityFeature.VOLUME_SET
FAN_SET_SPEED = 1      # FanEntityFeature.SET_SPEED


def _percent(id_, label):
    return {'id': id_, 'label': label, 'type': 'number', 'min': 0, 'max': 100, 'step': 1}


class HomeAssistantError(ValueError):
    pass


class HomeAssistantClient:
    """Minimal REST client using only the standard library."""

    def __init__(self, url, token, timeout=10):
        self.url = url.rstrip('/')
        self.token = token
        self.timeout = timeout

    @classmethod
    def from_env(cls):
        token = os.environ.get('HOMEASSISTANT_TOKEN', '').strip()
        if not token:
            raise HomeAssistantError(
                'Set HOMEASSISTANT_TOKEN in .env (Home Assistant: your profile > '
                'Security > Long-lived access tokens).')
        url = os.environ.get('HOMEASSISTANT_URL', '').strip() or 'http://localhost:8123'
        return cls(url, token)

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return json.loads(res.read() or b'null')
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise HomeAssistantError('Home Assistant rejected the access token') from None
            if exc.code == 404:
                raise HomeAssistantError(f'Home Assistant has no {path}') from None
            raise HomeAssistantError(f'Home Assistant returned HTTP {exc.code} for {path}') from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HomeAssistantError(f'Cannot reach Home Assistant at {self.url}: {exc}') from None


def control_for(state):
    """The one integer control GhostUI can drive exactly for this entity, or None."""
    domain = state['entity_id'].split('.', 1)[0]
    attrs = state.get('attributes') or {}
    features = attrs.get('supported_features') or 0
    if domain == 'light':
        modes = set(attrs.get('supported_color_modes') or [])
        if modes and modes <= {'onoff'}:
            return None  # on/off only: needs the planned toggle type
        return _percent('brightness', 'Brightness')
    if domain == 'media_player' and features & MEDIA_VOLUME_SET:
        return _percent('volume', 'Volume')
    if domain == 'fan' and features & FAN_SET_SPEED:
        # A fan with a few fixed speeds would silently round our value, so the
        # read-back would never match. Only accept fans with 1% steps.
        if float(attrs.get('percentage_step') or 1) == 1:
            return _percent('speed', 'Speed')
    return None


def read_value(state):
    domain = state['entity_id'].split('.', 1)[0]
    attrs = state.get('attributes') or {}
    if state.get('state') in ('unavailable', 'unknown'):
        raise HomeAssistantError('Entity is ' + state['state'] + ': ' + state['entity_id'])
    if state.get('state') == 'off':
        if domain == 'media_player':
            return round((attrs.get('volume_level') or 0) * 100)
        return 0
    if domain == 'light':
        return round((attrs.get('brightness') or 0) * 100 / 255)
    if domain == 'media_player':
        return round((attrs.get('volume_level') or 0) * 100)
    if domain == 'fan':
        return round(attrs.get('percentage') or 0)
    raise HomeAssistantError('Unsupported entity ' + state['entity_id'])


def service_call(entity_id, value):
    """(domain, service, data) that sets this entity's control to value."""
    domain = entity_id.split('.', 1)[0]
    if domain == 'light':
        if value == 0:
            return 'light', 'turn_off', {'entity_id': entity_id}
        # Send HA's own 0..255 scale so the percentage reads back exactly.
        return 'light', 'turn_on', {'entity_id': entity_id, 'brightness': round(value * 255 / 100)}
    if domain == 'media_player':
        return 'media_player', 'volume_set', {'entity_id': entity_id, 'volume_level': value / 100}
    if domain == 'fan':
        if value == 0:
            return 'fan', 'turn_off', {'entity_id': entity_id}
        return 'fan', 'set_percentage', {'entity_id': entity_id, 'percentage': value}
    raise HomeAssistantError('Unsupported entity ' + entity_id)


def supported_entities(client):
    """[(entity_id, friendly name, control id)] that GhostUI can drive."""
    found = []
    for state in client.call('GET', '/api/states') or []:
        control = control_for(state)
        if control:
            name = (state.get('attributes') or {}).get('friendly_name') or state['entity_id']
            found.append((state['entity_id'], name, control['id']))
    return sorted(found)


class HomeAssistantAdapter:
    simulated = False

    def __init__(self, address=None, simulated=False, client=None):
        if simulated:
            raise HomeAssistantError('Home Assistant has no --simulate mode; '
                                     'use its demo integration for fake devices.')
        self.client = client or HomeAssistantClient.from_env()
        if not address:
            # Never bind to whichever entity happens to exist: the user picks.
            options = supported_entities(self.client)
            listing = '\n'.join(f'  {e}  ({n}, {c})' for e, n, c in options) or '  (none found)'
            raise HomeAssistantError('Choose a Home Assistant entity, e.g. '
                                     '--device homeassistant light.ceiling_lights\n'
                                     'Entities GhostUI can control:\n' + listing)
        if not ENTITY_ID.match(address):
            raise HomeAssistantError(f'Not a Home Assistant entity ID: {address!r}')
        self.entity_id = address
        state = self._state()
        self.control = control_for(state)
        if not self.control:
            raise HomeAssistantError(
                f'{address} has no control GhostUI supports yet. Supported: lights '
                'with brightness, media players with volume, fans with 1% speed steps.')
        name = (state.get('attributes') or {}).get('friendly_name') or address
        self._caps = {'deviceId': 'ha.' + address, 'name': name, 'controls': [self.control]}

    @property
    def capabilities(self):
        return self._caps

    def _state(self):
        state = self.client.call('GET', '/api/states/' + self.entity_id)
        if not isinstance(state, dict) or state.get('entity_id') != self.entity_id:
            raise HomeAssistantError('Unexpected state response for ' + self.entity_id)
        return state

    def discover(self):
        pass  # Home Assistant owns discovery; the entity is chosen explicitly.

    def request(self, change=None):
        if change:
            field, value = change
            if field != self.control['id']:
                raise HomeAssistantError('Unknown capability ' + str(field))
            domain, service, data = service_call(self.entity_id, value)
            self.client.call('POST', f'/api/services/{domain}/{service}', data)
        return {self.control['id']: read_value(self._state())}

    def close(self):
        pass
