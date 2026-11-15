"""Transport for generated adapters for a single percentage control on a JSON API."""
import http.client
import json
from urllib.parse import urlsplit

from ..contracts import validate_command


class JsonLevelAdapter:
    simulated = False
    binding: dict

    def __init__(self, address=None, simulated=False):
        if simulated or not address:
            raise ValueError('Supply the controller IP or hostname; use demo-light for simulation')
        self.origin = urlsplit(address if '://' in address else 'http://' + address)
        if (self.origin.scheme not in ('http', 'https') or not self.origin.hostname or
                self.origin.username is not None or self.origin.password is not None or
                self.origin.query or self.origin.fragment or self.origin.path not in ('', '/')):
            raise ValueError('Expected a controller hostname or HTTP(S) origin')
        info = self._call(self.binding['info_path'])
        if info.get(self.binding['match_field']) != self.binding['match_value']:
            raise ValueError('Controller identity does not match the adapter')
        instance = info.get(self.binding['identity_field'])
        name = info.get(self.binding['name_field'])
        if not isinstance(instance, str) or not instance.strip() or not isinstance(name, str) or not name.strip():
            raise ValueError('Missing controller identifier or name')
        self.control = self.binding['control_id']
        self.capabilities = {'deviceId': self.binding['family'] + ':' + instance, 'name': name,
                             'controls': [{'id': self.control, 'label': self.binding['label'],
                                           'type': 'number', 'min': 0, 'max': 100, 'step': 1}]}

    def _call(self, path, payload=None):
        transport = http.client.HTTPSConnection if self.origin.scheme == 'https' else http.client.HTTPConnection
        connection = transport(self.origin.hostname, self.origin.port, timeout=4)
        try:
            if payload is None:
                connection.request('GET', path)
            else:
                connection.request('POST', path, json.dumps(payload), {'Content-Type': 'application/json'})
            response = connection.getresponse()
            if not 200 <= response.status < 300:
                raise ValueError(f'Device returned HTTP {response.status} for {path}')
            if payload is not None:
                return  # The following state read provides confirmation.
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('Device response exceeded 64 KiB')
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object from the controller')
            return data
        finally:
            connection.close()

    def discover(self):
        # The supplied address was probed while constructing the capabilities.
        pass

    def request(self, change=None):
        spec = self.binding
        field, power, maximum = spec['value_field'], spec['power_field'], spec['wire_max']
        if change is not None:
            validate_command({self.control: (0, 100)}, change)
            percent = change[1]
            payload = {field: (percent * maximum + 50) // 100}
            if power:
                payload = {power: False} if percent == 0 else {**payload, power: True}
            self._call(spec['command_path'], payload)
        state = self._call(spec['state_path'])
        value = state.get(field)
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f'Invalid {field} in controller state')
        if power:
            if type(state.get(power)) is not bool:
                raise ValueError(f'Invalid {power} in controller state')
            if not state[power]:
                value = 0
        return {self.control: (value * 100 + maximum // 2) // maximum}

    def close(self):
        pass  # Requests close their own connections.
