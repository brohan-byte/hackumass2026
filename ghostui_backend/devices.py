"""Persistent device instances and one active, verified runtime connection."""
import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
from urllib.parse import urlsplit
from uuid import uuid4

from .ar_layout import ARLayoutService
from .contracts import validate_command
from .integrations.catalog import INTEGRATIONS
from .onboarding.service import OnboardingService
from .recognition import RecognitionService
from .service import DeviceWorker

ROOT = Path(__file__).resolve().parent.parent / 'data'


class DeviceSelectionError(ValueError):
    pass


class DeviceSession:
    def __init__(self, worker, record, root):
        self.worker = worker
        self.record = record
        self.recognition = RecognitionService(record['enrollmentId'], storage=root / 'vision')
        self.layout = ARLayoutService(worker.capabilities, storage=root / 'ar-layouts')
        self.onboarding = OnboardingService(worker, self.recognition)
        self.command_token = secrets.token_urlsafe(32)
        self.generation_token = secrets.token_urlsafe(32)
        self.generation_lock = threading.Lock()


class DeviceManager:
    def __init__(self, root=ROOT, worker_factory=DeviceWorker):
        self.root = Path(root)
        self.path = self.root / 'devices.json'
        self.worker_factory = worker_factory
        self.lock = threading.RLock()
        self.active = None
        self.errors = {}
        if self.path.exists():
            data = json.loads(self.path.read_text())
            if data.get('version') != 1 or not isinstance(data.get('devices'), list):
                raise ValueError('Unsupported device registry. Preserve devices.json before repairing it.')
            records = data['devices']
            if len({r['id'] for r in records}) != len(records):
                raise ValueError('Duplicate device IDs in registry')
            self.records = {r['id']: r for r in records}
            self.last_selected = data.get('selectedDeviceId')
        else:
            self.records = {}
            self.last_selected = None

    def _save(self, records, selected):
        self.root.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.root, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as file:
                json.dump({'version': 1, 'selectedDeviceId': selected,
                           'devices': list(records.values())}, file, indent=2)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def listing(self):
        with self.lock:
            devices = []
            for record in self.records.values():
                active = self.active is not None and self.active.record['id'] == record['id']
                devices.append({key: record[key] for key in
                                ('id', 'name', 'integrationId', 'address', 'simulated', 'capabilities')})
                devices[-1].update(status='offline' if record['id'] in self.errors else
                                  'connected' if active else 'saved', error=self.errors.get(record['id']))
            return {'devices': devices,
                    'activeDeviceId': self.active.record['id'] if self.active else None}

    def _new_worker(self, integration, address, simulated, binding=None):
        worker = self.worker_factory(address, simulated, integration, **({'binding': binding} if binding is not None else {}))
        try:
            if not address and not simulated:
                worker.discover()
            state = worker.request()
            for field, bounds in worker.limits.items():
                validate_command({field: bounds}, (field, state.get(field)))
            return worker
        except BaseException:
            worker.close()
            raise

    def _source(self, integration):
        if integration != 'homeassistant':
            return ''
        raw = os.environ.get('HOMEASSISTANT_URL', '').strip() or 'http://localhost:8123'
        url = urlsplit(raw)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            raise ValueError('HOMEASSISTANT_URL must be an HTTP(S) server address without embedded credentials')
        return raw.rstrip('/')

    def _adopt_layout(self, reported, session):
        # Preserve old files and copy a verified layout to the new instance key.
        old = ARLayoutService(reported, storage=self.root / 'ar-layouts')
        if old.current()['source'] == 'ai' and not session.layout.path.exists():
            session.layout.path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=session.layout.path.parent, suffix='.tmp')
            try:
                with os.fdopen(fd, 'wb') as file:
                    file.write(old.path.read_bytes())
                os.replace(name, session.layout.path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)

    def _install(self, worker, record, records):
        worker.capabilities = copy.deepcopy(record['capabilities'])
        session = DeviceSession(worker, record, self.root)
        try:
            self._save(records, record['id'])
        except BaseException:
            worker.close()
            raise
        previous = self.active
        self.active = session
        self.records = records
        self.last_selected = record['id']
        self.errors.pop(record['id'], None)
        if previous:
            try:
                previous.worker.close()
            except Exception as exc:
                print(f'Previous device cleanup failed: {type(exc).__name__}', flush=True)
        return self.listing()

    def register(self, integration, address=None, simulated=False, name=None, *, binding=None, provenance=None, expected_identity=None):
        if not isinstance(integration, str) or integration not in INTEGRATIONS:
            raise ValueError('Unknown integration')
        if integration == 'generated-http':
            from .adaptergen import validate
            validate(binding)
        elif binding is not None or provenance is not None:
            raise ValueError('Only generated-http accepts adapter binding metadata')
        if address is not None and (not isinstance(address, str) or len(address) > 256):
            raise ValueError('Invalid connection address')
        if type(simulated) is not bool:
            raise ValueError('simulated must be boolean')
        if name is not None and (not isinstance(name, str) or not 1 <= len(name.strip()) <= 80):
            raise ValueError('Name must contain 1–80 characters')
        if address and '://' in address:
            url = urlsplit(address)
            if url.username or url.password or url.query or url.fragment:
                raise ValueError('Keep credentials out of device addresses')
        with self.lock:
            source = self._source(integration)
            # Reuse the current connection rather than opening a second BLE client.
            if self.active:
                current = self.active.record
                if (current['integrationId'] == integration and current['address'] == address and current['source'] == source and
                        current['simulated'] == (simulated or integration == 'demo-light') and binding is None and expected_identity is None):
                    if name and name.strip() != current['name']:
                        raise ValueError('This device is already selected under its saved name')
                    return self.listing()
            worker = self._new_worker(integration, address, simulated, binding)
            try:
                reported = copy.deepcopy(worker.capabilities)
                if expected_identity is not None:
                    actual = getattr(worker.adapter, 'identity_info', {})
                    if not isinstance(expected_identity, dict) or not expected_identity or any(
                            actual.get(key) != value for key, value in expected_identity.items()):
                        raise ValueError('A different device answered during setup; search again')
                if integration in ('marshall', 'sony', 'sony-playback') and not worker.simulated:
                    discovered = worker.adapter.address
                    address = getattr(discovered, 'address', discovered)
                    identity = str(address)
                elif worker.simulated:
                    identity = address or 'default'
                else:
                    identity = reported['deviceId']
                fingerprint = hashlib.sha256(json.dumps([integration, source, identity, worker.simulated]).encode()).hexdigest()
                existing = next((r for r in self.records.values() if r['fingerprint'] == fingerprint), None)
                instance_id = existing['id'] if existing else uuid4().hex
                if existing:
                    enrollment_id = existing['enrollmentId']
                else:
                    # Only the first real instance may claim legacy references.
                    claimed = any(r['enrollmentId'] == reported['deviceId'] for r in self.records.values())
                    legacy = not worker.simulated and integration in ('marshall', 'wled') and not claimed
                    enrollment_id = reported['deviceId'] if legacy else instance_id
                capabilities = {**reported, 'deviceId': instance_id,
                                'name': name.strip() if name else existing['name'] if existing else reported['name']}
                record = {'id': instance_id, 'name': capabilities['name'], 'integrationId': integration,
                          'address': address, 'source': source, 'fingerprint': fingerprint,
                          'reportedDeviceId': reported['deviceId'], 'enrollmentId': enrollment_id,
                          'simulated': worker.simulated, 'capabilities': capabilities}
                if integration == 'sony':
                    record['adapterProvenance'] = {
                        'source': 'existing-library',
                        'repository': 'https://github.com/mos9527/SonyHeadphonesClient',
                        'commit': '3c8f3330c85d45c29e7b76f718082a8d4fe402f1',
                        'model': worker.adapter.model, 'firmware': worker.adapter.firmware}
                if integration == 'sony-playback':
                    record['adapterProvenance'] = {'source': 'macos-coreaudio',
                        'controlScope': 'Mac playback volume only', 'model': worker.adapter.model}
                if binding is not None:
                    record['adapterBinding'] = copy.deepcopy(binding)
                    record['adapterProvenance'] = copy.deepcopy(provenance or {'source': 'supplied-binding'})
                records = {**self.records, instance_id: record}
                worker.capabilities = capabilities
                preview = DeviceSession(worker, record, self.root)
                if enrollment_id != instance_id:
                    self._adopt_layout(reported, preview)
            except BaseException:
                worker.close()
                raise
            return self._install(worker, record, records)

    def select(self, instance_id):
        with self.lock:
            if instance_id not in self.records:
                raise KeyError('Unknown saved device')
            if self.active and self.active.record['id'] == instance_id:
                return self.listing()
            record = self.records[instance_id]
            try:
                if self._source(record['integrationId']) != record['source']:
                    raise ValueError('Configure the saved Home Assistant server before selecting this device')
                worker = self._new_worker(record['integrationId'], record['address'], record['simulated'], record.get('adapterBinding'))
                if not worker.simulated and worker.capabilities['deviceId'] != record['reportedDeviceId']:
                    worker.close()
                    raise ValueError('A different device answered at the saved address. Register it explicitly.')
                capabilities = {**copy.deepcopy(worker.capabilities), 'deviceId': instance_id, 'name': record['name']}
                updated = {**record, 'capabilities': capabilities}
                return self._install(worker, updated, {**self.records, instance_id: updated})
            except Exception as exc:
                self.errors[instance_id] = str(exc)
                raise

    @contextmanager
    def session(self, instance_id=None):
        # Keep the selected worker alive through the whole HTTP operation.
        with self.lock:
            if not self.active:
                raise DeviceSelectionError('Select a saved device or add a connection first')
            if instance_id is not None and self.active.record['id'] != instance_id:
                raise DeviceSelectionError('Device selection changed. Select this device again before using it.')
            yield self.active

    def mark_online(self, instance_id):
        with self.lock:
            self.errors.pop(instance_id, None)

    def mark_offline(self, instance_id, error):
        with self.lock:
            self.errors[instance_id] = str(error)

    def close(self):
        with self.lock:
            if self.active:
                self.active.worker.close()
                self.active = None
