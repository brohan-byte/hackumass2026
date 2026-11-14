"""Browser and paired iPhone HTTP routes. Existing paths are stable."""
import json
import secrets
import threading
from pathlib import Path
from .http_base import make_handler
from .generation import generate
from .recognition import RecognitionService, VisionBusy
from .onboarding.service import OnboardingService
EXTRA = (Path(__file__).parent / 'web/generation.js').read_text()

def handler_for(worker, port, mobile_token=None):
    generation_token = secrets.token_urlsafe(32)
    base = make_handler(worker, port)
    generation_lock = threading.Lock()
    recognition = RecognitionService(worker.capabilities["deviceId"])

    onboarding = OnboardingService(worker, recognition)

    class Handler(base):
        def mobile(self):
            if not mobile_token or not secrets.compare_digest(
                    self.headers.get('Authorization', ''), 'Bearer ' + mobile_token):
                self.reply({'error': 'Invalid phone pairing token'}, 401)
                return False
            if self.headers.get('Origin'):
                self.reply({'error': 'Use the native phone app'}, 403)
                return False
            return True

        def do_GET(self):
            if self.path.startswith('/mobile/'):
                if not self.mobile(): return
                if self.path == '/mobile/capabilities':
                    return self.reply({**worker.capabilities, 'simulated': worker.simulated})
                if self.path == '/mobile/onboarding': return self.reply(onboarding.describe())
                if self.path == '/mobile/vision': return self.reply(recognition.status())
                if self.path == '/mobile/state': return self.run_device()
                return self.reply({'error': 'Not found'}, 404)
            if self.path == '/':
                if not self.trusted(): return
                # Obtain the command token/page from the existing handler, replacing
                # its page body without altering its authentication behavior.
                original_reply = self.reply
                def reply(body, code=200, html=False):
                    if html:
                        body = body.replace('</script>', EXTRA.replace('__GENERATION_TOKEN__', generation_token) + '</script>')
                    original_reply(body, code, html)
                self.reply = reply
                return super().do_GET()
            return super().do_GET()

        def run_device(self, change=None):
            if change:
                print(f'GhostUI command: {change[0]} -> {change[1]}', flush=True)
            try:
                state = worker.request(change)
                if change:
                    print(f'GhostUI readback: {change[0]} = {state.get(change[0])}', flush=True)
                self.reply(state)
            except Exception as exc:
                print(f'GhostUI device request failed: {type(exc).__name__}: {exc}', flush=True)
                self.reply({'error': str(exc) or type(exc).__name__}, 503)

        def do_POST(self):
            if self.path == '/mobile/onboarding/verify':
                if not self.mobile(): return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 1024: raise ValueError('Invalid body size')
                    body = json.loads(self.rfile.read(length))
                    if body != {}: raise ValueError('Expected empty JSON object')
                except (ValueError, TypeError) as exc:
                    return self.reply({'error': str(exc)}, 400)
                try: return self.reply(onboarding.verify_connection())
                except Exception as exc: return self.reply({'error': str(exc)}, 503)

            if self.path.startswith('/mobile/vision/'):
                if not self.mobile(): return
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=1_600_000: raise ValueError('Invalid image request size')
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict): raise ValueError('Expected JSON object')
                    if self.path=='/mobile/vision/enroll':
                        if set(body)!={'image','box'}: raise ValueError('Expected image and box')
                        return self.reply(recognition.enroll(body['image'],body['box']))
                    if self.path=='/mobile/vision/detect':
                        if set(body)!={'image'}: raise ValueError('Expected image')
                        return self.reply(recognition.detect(body['image']))
                    if self.path=='/mobile/vision/clear': return self.reply(recognition.clear())
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
                    if not isinstance(field, str) or field not in worker.limits:
                        raise ValueError('Unknown capability')
                    lo, hi = worker.limits[field]
                    if type(value) is not int or not lo <= value <= hi:
                        raise ValueError('Value outside allowed range')
                except (ValueError, TypeError) as exc:
                    return self.reply({'error': str(exc)}, 400)
                return self.run_device((field, value))
            if self.path != '/generate': return super().do_POST()
            if not self.trusted(): return
            if self.headers.get('X-Generation-Token') != generation_token:
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
            if not generation_lock.acquire(blocking=False):
                return self.reply({'error': 'Generation already in progress'}, 429)
            try: self.reply(generate(worker.capabilities, preference))
            finally: generation_lock.release()
    return Handler
