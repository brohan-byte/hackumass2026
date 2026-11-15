"""Names-only registration choices; protocol and credential details stay on Mac."""
import hashlib
import json
import os
import shutil
from ..devices import ROOT
from ..recognition import RecognitionService
from ..integrations.catalog import INTEGRATIONS
from ..integrations.homeassistant import HomeAssistantClient, supported_entities


class RegistrationService:
    def __init__(self, manager):
        self.manager = manager

    def _choices(self):
        with self.manager.lock:
            records = [dict(r) for r in self.manager.records.values() if not r['simulated']]
        choices = {r['id']: {'id': r['id'], 'name': r['name'], 'savedId': r['id']} for r in records}
        # Explicitly configured setup choices are not verified device records.
        # Registration opens and verifies the real connection before saving it.
        try:
            options = json.loads((self.manager.root/'registration-options.json').read_text())
            enabled = options.get('integrations', []) if options.get('version') == 1 else []
            if isinstance(enabled, list) and 'sony-playback' in enabled and not any(
                    r['integrationId'] == 'sony-playback' for r in records):
                id_ = 'setup-sony-playback'
                choices[id_] = {'id': id_, 'name': INTEGRATIONS['sony-playback'].name,
                                'integrationId': 'sony-playback'}
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        # Fresh generation-demo profiles can still use the verified speaker
        # connection from the main project, without showing addresses/protocols.
        if ROOT.resolve() in self.manager.root.resolve().parents:
            try:
                saved = json.loads((ROOT/'devices.json').read_text()).get('devices', [])
                for record in saved:
                    if record.get('integrationId') != 'marshall' or record.get('simulated'): continue
                    if any(r['integrationId']=='marshall' and r['address']==record['address'] for r in records): continue
                    id_ = 'saved-'+hashlib.sha256(record['id'].encode()).hexdigest()
                    choices[id_] = {'id': id_, 'name': record['name'], 'externalRecord': record}
            except (OSError, ValueError, KeyError, TypeError):
                pass
        notice = None
        if os.environ.get('HOMEASSISTANT_TOKEN', '').strip():
            try:
                client = HomeAssistantClient.from_env()
                source = self.manager._source('homeassistant')
                known = {r['address'] for r in records if r['integrationId'] == 'homeassistant' and r['source'] == source}
                for entity, name, _ in supported_entities(client):
                    if entity in known: continue
                    id_ = hashlib.sha256((source + '\n' + entity).encode()).hexdigest()
                    choices[id_] = {'id': id_, 'name': name, 'entity': entity}
            except Exception:
                notice = 'Some devices could not be reached. Check the connection on your Mac and retry.'
        return choices, notice

    def describe(self):
        choices, notice = self._choices()
        return {'devices': [{'id': row['id'], 'name': row['name']} for row in choices.values()], 'notice': notice}

    def choose(self, id_):
        if not isinstance(id_, str): raise ValueError('Choose a device')
        choices, _ = self._choices()
        if id_ not in choices: raise KeyError('Device is no longer available; refresh and try again')
        choice = choices[id_]
        if 'savedId' in choice:
            self.manager.select(choice['savedId'])
            device_id = choice['savedId']
        elif 'integrationId' in choice:
            result = self.manager.register(choice['integrationId'], name=choice['name'])
            device_id = result['activeDeviceId']
        elif 'externalRecord' in choice:
            record = choice['externalRecord']
            result = self.manager.register('marshall', record['address'], name=record['name'])
            device_id = result['activeDeviceId']
            current = self.manager.records[device_id]
            source = RecognitionService(record['enrollmentId'], storage=ROOT/'vision')
            target = RecognitionService(current['enrollmentId'], storage=self.manager.root/'vision')
            if not target.files():
                for path in source.files():
                    if path.with_suffix('.jpg').is_file():
                        target.folder.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path.with_suffix('.jpg'), target.folder/path.with_suffix('.jpg').name)
                        shutil.copy2(path, target.folder/path.name)
        else:
            result = self.manager.register('homeassistant', choice['entity'])
            device_id = result['activeDeviceId']
        return {'deviceId': device_id}
