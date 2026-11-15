"""Validated, persistent layouts for the native AR renderer."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading

from .generation import generate, template, validate_layout

AR_PREFERENCE = ('Native AR hand-gesture HUD with vertical sliders. Choose concise '
                 'labels, a short title, and meaningful groups. Order related controls '
                 'together. The native renderer manages safe geometry and hit targets.')


class ARLayoutService:
    def __init__(self, capabilities, storage=None):
        self.capabilities = capabilities
        root = Path(storage) if storage else Path(__file__).resolve().parent.parent / 'data/ar-layouts'
        identity = json.dumps({'capabilities': capabilities, 'preference': AR_PREFERENCE}, sort_keys=True)
        self.path = root / (hashlib.sha256(identity.encode()).hexdigest() + '.json')
        self.lock = threading.Lock()

    def current(self):
        try:
            result = json.loads(self.path.read_text())
            if result.get('source') != 'ai':
                raise ValueError('Expected saved AI layout')
            layout = validate_layout(result['layout'], self.capabilities)
            return {'deviceId': self.capabilities['deviceId'], 'layout': layout, 'source': 'ai', 'notice': 'Saved Gemini AR layout.', 'cached': True}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return {'deviceId': self.capabilities['deviceId'], 'layout': template(self.capabilities), 'source': 'template',
                    'notice': 'Default AR controls. Generate a layout when the Mac has internet access.',
                    'cached': False}

    def resolve(self, refresh=False):
        with self.lock:
            saved = self.current()
            if saved['source'] == 'ai' and not refresh:
                return saved
            result = generate(self.capabilities, AR_PREFERENCE)
            validate_layout(result['layout'], self.capabilities)
            if result['source'] != 'ai':
                if saved['source'] == 'ai':
                    return {**saved, 'notice': 'Generation unavailable. Keeping the saved Gemini AR layout.'}
                return {**result, 'deviceId': self.capabilities['deviceId'], 'cached': False}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=self.path.parent, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as file:
                    json.dump(result, file)
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {**result, 'deviceId': self.capabilities['deviceId'], 'cached': False}
