"""Fixed HTTP runtime configured by a persisted, validated Gemini JSON mapping."""
import copy
import hashlib
import json
from ..adaptergen import validate
from .http_level import JsonLevelAdapter


class DocumentedHttpAdapter(JsonLevelAdapter):
    def __init__(self, address=None, simulated=False, binding=None):
        if binding is None:
            raise ValueError('Use --onboard ADDRESS --api-docs URL to generate this adapter')
        validate(binding)
        self.binding = copy.deepcopy(binding)
        super().__init__(address, simulated)
        # A model's choice of family name must not create duplicate devices on
        # regeneration. Namespace the actual identifier by its documented vendor.
        identity = self.capabilities['deviceId'][len(binding['family']) + 1:]
        key = [binding['match_field'], binding['match_value'], binding['identity_field'], identity]
        self.capabilities['deviceId'] = 'generated-http:' + hashlib.sha256(json.dumps(key).encode()).hexdigest()
