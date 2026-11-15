"""Browser and paired iPhone HTTP routes. Existing paths are stable."""
import json
import secrets
import threading
from pathlib import Path
from .http_base import make_handler
from .generation import generate
from .recognition import RecognitionService, VisionBusy
from .onboarding.service import OnboardingService
from .ar_layout import ARLayoutService
from .devices import DeviceSelectionError
from .integrations.catalog import integration_catalog
from .scene import SceneRecognitionService
from .onboarding.registration import RegistrationService
from .onboarding.setup import DeviceSetupService, SetupBusy
EXTRA = (Path(__file__).parent / 'web/generation.js').read_text()

def handler_for(worker, port, mobile_token=None, manager=None):
    generation_token = secrets.token_urlsafe(32)
    base = make_handler(worker, port)
    generation_lock = threading.Lock()
    recognition = RecognitionService(worker.capabilities["deviceId"]) if worker else None

    onboarding = OnboardingService(worker, recognition) if worker else None
    ar_layout = ARLayoutService(worker.capabilities) if worker else None
    scene = SceneRecognitionService(manager) if manager else None
    registration = RegistrationService(manager) if manager else None
    setup = DeviceSetupService(manager) if manager else None

    class Handler(base):
        def bind_session(self, session=None):
            self.worker = session.worker if session else worker
            self.recognition = session.recognition if session else recognition
            self.onboarding = session.onboarding if session else onboarding
            self.ar_layout = session.layout if session else ar_layout
            self.generation_token = session.generation_token if session else generation_token
            self.generation_lock = session.generation_lock if session else generation_lock
            if session:
                self.command_token = session.command_token

        def registry_reply(self, listing):
            return self.reply({**listing, 'integrations': integration_catalog()})

        def registry_body(self):
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError('Invalid body size')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected JSON object')
            return body

        def scene_route(self, post):
            if not self.mobile(): return
            try:
                if self.path == '/mobile/registration':
                    if not post: return self.reply(registration.describe())
                    body = self.registry_body()
                    if set(body) != {'deviceId'}: raise ValueError('Choose a device')
                    return self.reply(registration.choose(body['deviceId']))
                if not post and self.path == '/mobile/scene/vision':
                    return self.reply(scene.status())
                if post and self.path == '/mobile/scene/vision/detect':
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 1_600_000: raise ValueError('Invalid image request size')
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict) or set(body) != {'image'}: raise ValueError('Expected image')
                    return self.reply(scene.detect(body['image']))
                return self.reply({'error': 'Not found'}, 404)
            except KeyError:
                return self.reply({'error': 'Device is no longer available; refresh and try again'}, 404)
            except VisionBusy as exc:
                return self.reply({'error': str(exc)}, 429)
            except (ValueError, TypeError) as exc:
                return self.reply({'error': str(exc)}, 400)
            except Exception as exc:
                print(f'Scene/registration failed: {type(exc).__name__}: {exc}', flush=True)
                return self.reply({'error': 'Could not complete this request. Check your Mac and retry.'}, 503)

        def setup_route(self, post):
            if not self.mobile(): return
            try:
                if self.path == '/mobile/setup/discover' and post:
                    if self.registry_body() != {}: raise ValueError('Expected empty JSON object')
                    return self.reply(setup.discover())
                if self.path == '/mobile/setup/start' and post:
                    body = self.registry_body()
                    if set(body) != {'candidateId'} or not isinstance(body['candidateId'], str):
                        raise ValueError('Choose a discovered device')
                    return self.reply(setup.start(body['candidateId']))
                if self.path.startswith('/mobile/setup/jobs/') and not post:
                    return self.reply(setup.status(self.path.removeprefix('/mobile/setup/jobs/')))
                return self.reply({'error': 'Not found'}, 404)
            except SetupBusy as exc:
                return self.reply({'error': str(exc)}, 409)
            except KeyError:
                return self.reply({'error': 'Device setup expired; search for devices again'}, 404)
            except (ValueError, TypeError) as exc:
                return self.reply({'error': str(exc)}, 400)
            except Exception as exc:
                print(f'Discovery failed: {type(exc).__name__}: {exc}', flush=True)
                return self.reply({'error': 'Could not search for lights. Check the Mac Wi-Fi connection and retry.'}, 503)

        def dispatch(self, post=False):
            path = self.path
            if manager and path.startswith('/mobile/setup/'):
                return self.setup_route(post)
            if manager and (path == '/mobile/registration' or path.startswith('/mobile/scene/')):
                return self.scene_route(post)
            instance_id = None
            if manager and path.startswith('/mobile/devices'):
                if not self.mobile(): return
                try:
                    if path == '/mobile/devices':
                        if not post: return self.registry_reply(manager.listing())
                        body = self.registry_body()
                        if set(body) - {'integrationId', 'address', 'name', 'simulated'}:
                            raise ValueError('Unexpected registration field')
                        if not isinstance(body.get('integrationId'), str):
                            raise ValueError('Expected integrationId')
                        return self.registry_reply(manager.register(body['integrationId'],
                            body.get('address'), body.get('simulated', False), body.get('name')))
                    parts = path.split('/')
                    if len(parts) < 5 or not parts[3]:
                        return self.reply({'error': 'Not found'}, 404)
                    instance_id = parts[3]
                    if parts[4:] == ['select']:
                        if not post: return self.reply({'error': 'Use POST to select a device'}, 405)
                        if self.registry_body() != {}: raise ValueError('Expected empty JSON object')
                        return self.registry_reply(manager.select(instance_id))
                    if instance_id not in manager.records:
                        return self.reply({'error': 'Unknown saved device'}, 404)
                    self.path = '/mobile/' + '/'.join(parts[4:])
                except KeyError:
                    return self.reply({'error': 'Unknown saved device'}, 404)
                except (ValueError, TypeError) as exc:
                    return self.reply({'error': str(exc)}, 400)
                except Exception as exc:
                    return self.reply({'error': str(exc) or type(exc).__name__}, 503)
            try:
                if manager:
                    # Authenticate before reporting device state, even with no active device.
                    if self.path.startswith('/mobile/'):
                        if not self.mobile(): return
                        if instance_id is None:
                            return self.reply({'error': 'Select a device and use its device-scoped route'}, 409)
                    elif not self.trusted(): return
                    if not manager.active and path == '/' and not post:
                        return self.reply('<h1>GhostUI is ready</h1><p>Connect your phone and tap Register object to find and set up a WLED light.</p>', html=True)
                    with manager.session(instance_id) as session:
                        self.bind_session(session)
                        return self.device_POST() if post else self.device_GET()
                self.bind_session()
                return self.device_POST() if post else self.device_GET()
            except DeviceSelectionError as exc:
                return self.reply({'error': str(exc)}, 409)
            finally:
                self.path = path

        def do_GET(self):
            return self.dispatch()

        def do_POST(self):
            return self.dispatch(post=True)

        def mobile(self):
            if not mobile_token or not secrets.compare_digest(
                    self.headers.get('Authorization', ''), 'Bearer ' + mobile_token):
                self.reply({'error': 'Invalid phone pairing token'}, 401)
                return False
            if self.headers.get('Origin'):
                self.reply({'error': 'Use the native phone app'}, 403)
                return False
            return True

        def device_GET(self):
            if self.path.startswith('/mobile/'):
                if not self.mobile(): return
                if self.path == '/mobile/capabilities':
                    return self.reply({**self.worker.capabilities, 'simulated': self.worker.simulated})
                if self.path == '/mobile/layout': return self.reply(self.ar_layout.current())
                if self.path == '/mobile/onboarding': return self.reply({**self.onboarding.describe(), **({'scope': 'saved-devices-one-active'} if manager else {})})
                if self.path == '/mobile/vision': return self.reply(self.recognition.status())
                if self.path == '/mobile/state': return self.run_device()
                return self.reply({'error': 'Not found'}, 404)
            if self.path == '/':
                if not self.trusted(): return
                # Obtain the command token/page from the existing handler, replacing
                # its page body without altering its authentication behavior.
                original_reply = self.reply
                def reply(body, code=200, html=False):
                    if html:
                        body = body.replace('</script>', EXTRA.replace('__GENERATION_TOKEN__', self.generation_token) + '</script>')
                    original_reply(body, code, html)
                self.reply = reply
                return super().do_GET()
            return super().do_GET()

        def run_device(self, change=None):
            if change:
                print(f'GhostUI command: {change[0]} -> {change[1]}', flush=True)
            try:
                state = self.worker.request(change)
                if manager: manager.mark_online(self.worker.capabilities['deviceId'])
                if change:
                    print(f'GhostUI readback: {change[0]} = {state.get(change[0])}', flush=True)
                self.reply(state)
            except Exception as exc:
                if manager: manager.mark_offline(self.worker.capabilities['deviceId'], exc)
                print(f'GhostUI device request failed: {type(exc).__name__}: {exc}', flush=True)
                self.reply({'error': str(exc) or type(exc).__name__}, 503)

        def device_POST(self):
            if self.path == '/mobile/layout':
                if not self.mobile(): return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 1024: raise ValueError('Invalid body size')
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict) or set(body) - {'refresh'}:
                        raise ValueError('Expected optional refresh only')
                    if type(body.get('refresh', False)) is not bool:
                        raise ValueError('refresh must be boolean')
                except (ValueError, TypeError) as exc:
                    return self.reply({'error': str(exc)}, 400)
                if not self.generation_lock.acquire(blocking=False):
                    return self.reply({'error': 'Generation already in progress'}, 429)
                try:
                    self.reply(self.ar_layout.resolve(body.get('refresh', False)))
                except Exception:
                    self.reply({'error': 'AR layout could not be saved. Retry generation.'}, 503)
                finally:
                    self.generation_lock.release()
                return

            if self.path == '/mobile/onboarding/verify':
                if not self.mobile(): return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 1024: raise ValueError('Invalid body size')
                    body = json.loads(self.rfile.read(length))
                    if body != {}: raise ValueError('Expected empty JSON object')
                except (ValueError, TypeError) as exc:
                    return self.reply({'error': str(exc)}, 400)
                try:
                    result = self.onboarding.verify_connection()
                    if manager: manager.mark_online(self.worker.capabilities['deviceId'])
                    return self.reply(result)
                except Exception as exc:
                    if manager: manager.mark_offline(self.worker.capabilities['deviceId'], exc)
                    return self.reply({'error': str(exc)}, 503)

            if self.path.startswith('/mobile/vision/'):
                if not self.mobile(): return
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=1_600_000: raise ValueError('Invalid image request size')
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict): raise ValueError('Expected JSON object')
                    if self.path=='/mobile/vision/enroll':
                        if set(body)!={'image','box'}: raise ValueError('Expected image and box')
                        return self.reply(self.recognition.enroll(body['image'],body['box']))
                    if self.path=='/mobile/vision/detect':
                        if set(body)!={'image'}: raise ValueError('Expected image')
                        return self.reply(self.recognition.detect(body['image']))
                    if self.path=='/mobile/vision/clear': return self.reply(self.recognition.clear())
                    return self.reply({'error':'Not found'},404)
                except VisionBusy as exc:return self.reply({'error':str(exc)},429)
                except (ValueError,TypeError) as exc:return self.reply({'error':str(exc)},400)
                except ImportError:return self.reply({'error':'Vision dependencies missing. Run app.py using .venv-vision/bin/python.'},503)
                except Exception as exc:
                    print(f'Vision failed: {type(exc).__name__}: {exc}',flush=True)
                    return self.reply({'error':'YOLOE inference failed. See the Mac terminal for details.'},503)

            if self.path == '/mobile/command':
                if not self.mobile(): return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 1024: raise ValueError('Invalid body size')
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict) or set(data) != {'capability', 'value'}:
                        raise ValueError('Expected capability and value')
                    field, value = data['capability'], data['value']
                    if not isinstance(field, str) or field not in self.worker.limits:
                        raise ValueError('Unknown capability')
                    lo, hi = self.worker.limits[field]
                    if type(value) is not int or not lo <= value <= hi:
                        raise ValueError('Value outside allowed range')
                except (ValueError, TypeError) as exc:
                    return self.reply({'error': str(exc)}, 400)
                return self.run_device((field, value))
            if self.path != '/generate': return super().do_POST()
            if not self.trusted(): return
            if self.headers.get('X-Generation-Token') != self.generation_token:
                return self.reply({'error': 'Invalid generation token'}, 403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096: raise ValueError('Invalid body size')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or set(body) != {'preference'}:
                    raise ValueError('Expected preference only')
                preference = body['preference']
                if not isinstance(preference, str) or len(preference) > 500:
                    raise ValueError('Preference must be at most 500 characters')
            except (ValueError, TypeError) as exc:
                return self.reply({'error': str(exc)}, 400)
            if not self.generation_lock.acquire(blocking=False):
                return self.reply({'error': 'Generation already in progress'}, 429)
            try: self.reply(generate(self.worker.capabilities, preference))
            finally: self.generation_lock.release()
    return Handler
