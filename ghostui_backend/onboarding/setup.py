"""Phone-triggered discovery and setup jobs; device details remain on the Mac."""
import copy
import secrets
import threading
import time

from .discovery import discover_wled, probe_wled
from .documented import DocumentedOnboarding


class SetupBusy(ValueError):
    pass


class DeviceSetupService:
    def __init__(self, manager):
        self.manager = manager
        self.lock = threading.RLock()
        self.scan_lock = threading.Lock()
        self.candidates = {}
        self.scanned_at = None
        self.jobs = {}
        self.running = None

    def discover(self):
        with self.scan_lock:
            with self.lock:
                fresh = bool(self.candidates) and self.scanned_at is not None and time.monotonic() - self.scanned_at < 15
            if not fresh:
                found = discover_wled()
                with self.lock:
                    # Keep candidate IDs stable between refreshes, but expire old candidates.
                    previous = {c['mac'].lower(): c['id'] for c in self.candidates.values()}
                    self.candidates = {}
                    for candidate in found:
                        id_ = previous.get(candidate['mac'].lower()) or secrets.token_hex(16)
                        self.candidates[id_] = {**candidate, 'id': id_, 'seenAt': time.monotonic()}
                    self.scanned_at = time.monotonic()
            with self.lock:
                devices = [{'id': c['id'], 'name': c['name']} for c in self.candidates.values()]
            return {'devices': devices, 'notice': None if devices else
                    'No new lights found. Keep the light and Mac on the same Wi-Fi, then retry.'}

    def start(self, candidate_id):
        with self.lock:
            if self.running:
                job = self.jobs[self.running]
                if job['candidateId'] == candidate_id: return self._public(job)
                raise SetupBusy('Another device is being prepared. Please wait.')
            candidate = self.candidates.get(candidate_id)
            if candidate is None or time.monotonic() - candidate['seenAt'] > 300:
                raise KeyError('Device discovery expired; search again')
            id_ = secrets.token_hex(16)
            job = {'id': id_, 'candidateId': candidate_id, 'status': 'running',
                   'message': 'Connecting to your light…', 'deviceId': None, 'error': None}
            # Keep at most 32 completed jobs; an in-flight job is never evicted.
            if len(self.jobs) >= 32: self.jobs.pop(next(iter(self.jobs)))
            self.jobs[id_] = job
            self.running = id_
            threading.Thread(target=self._prepare, args=(id_, dict(candidate)), daemon=True).start()
            return self._public(job)

    def status(self, id_):
        with self.lock:
            if id_ not in self.jobs: raise KeyError('Setup request expired; retry')
            return self._public(self.jobs[id_])

    @staticmethod
    def _public(job):
        return {k: copy.deepcopy(job[k]) for k in ('id', 'status', 'message', 'deviceId', 'error')}

    def _message(self, id_, message):
        with self.lock: self.jobs[id_]['message'] = message

    def _prepare(self, id_, candidate):
        try:
            current = probe_wled(candidate['address'])
            if current['mac'].lower() != candidate['mac'].lower():
                raise ValueError('A different light answered; search for devices again')
            with self.manager.lock:
                existing = next((copy.deepcopy(r) for r in self.manager.records.values()
                    if not r['simulated'] and r['integrationId'] in ('wled', 'generated-http') and
                    (r['address'] == candidate['address'] or
                     r.get('adapterProvenance', {}).get('discovery', {}).get('mac', '').lower() == current['mac'].lower())), None)
            if existing:
                self._message(id_, 'Opening your saved controls…')
                if existing['integrationId'] == 'generated-http':
                    result = self.manager.register('generated-http', candidate['address'], name=existing['name'],
                        binding=existing['adapterBinding'], provenance=existing.get('adapterProvenance'),
                        expected_identity={'mac': current['mac']})
                else:
                    # Same address is not enough: select() compares the saved unit identity.
                    result = self.manager.select(existing['id'])
            else:
                def progress(message):
                    print(message, flush=True)
                    self._message(id_, 'Preparing your connection…')
                result = DocumentedOnboarding(self.manager, progress).run(candidate['address'],
                    candidate['documentation'], candidate['name'], expected_identity={'mac': current['mac']})
            device_id = result['activeDeviceId']
            self._message(id_, 'Creating your controls…')
            with self.manager.session(device_id) as session:
                layout = session.layout.resolve()
            with self.lock:
                self.jobs[id_].update(status='ready', deviceId=device_id,
                    message='Ready to test your light.' if layout['source'] == 'ai' else
                            'Ready with standard controls.')
        except Exception as exc:
            print(f'Device setup failed: {type(exc).__name__}: {exc}', flush=True)
            with self.lock:
                self.jobs[id_].update(status='failed', message='Could not prepare this light.',
                    error='Check the light connection and the Mac internet connection, then try again.')
        finally:
            with self.lock: self.running = None
