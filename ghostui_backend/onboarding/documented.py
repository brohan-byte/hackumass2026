"""Documentation URL -> Gemini mapping -> verified persisted HTTP connection."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import os
import re
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..adaptergen import extract_binding, validate

MAX_DOWNLOAD = 1_048_576


def documentation_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Supply an HTTPS API documentation URL')
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('API documentation must use an HTTPS URL without embedded credentials')
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or '/', parsed.query, ''))


class SecureRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, documentation_url(newurl))


class DocumentationText(HTMLParser):
    """Drop executable/style/navigation text; preserve visible API examples."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'header', 'footer'):
            self.hidden.append(tag)
        if tag in ('p', 'div', 'tr', 'pre', 'li', 'h1', 'h2', 'h3') and not self.hidden:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()
        if tag in ('p', 'div', 'tr', 'pre', 'li') and not self.hidden:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def text(self):
        return re.sub(r'\n[ \t]*\n+', '\n\n', ''.join(self.parts)).strip()


@dataclass(frozen=True)
class APIDocumentation:
    url: str
    text: str

    @property
    def sha256(self):
        return hashlib.sha256(self.text.encode()).hexdigest()


def fetch_documentation(url):
    url = documentation_url(url)
    request = Request(url, headers={'User-Agent': 'GhostUI/0.1',
                                   'Accept': 'text/html,text/plain,application/json'})
    try:
        with build_opener(SecureRedirects()).open(request, timeout=12) as response:
            final_url = documentation_url(response.geturl())
            content_type = response.headers.get_content_type()
            if content_type not in ('text/html', 'text/plain', 'text/markdown', 'application/json'):
                raise ValueError('Use an HTML, plain-text or JSON API documentation page')
            raw = response.read(MAX_DOWNLOAD + 1)
            if len(raw) > MAX_DOWNLOAD:
                raise ValueError('Documentation exceeds 1 MiB; provide a focused API reference')
            text = raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
    except OSError as exc:
        raise ValueError(f'Could not download API documentation ({type(exc).__name__}); check the Mac internet connection') from None
    if content_type == 'text/html':
        parser = DocumentationText()
        parser.feed(text)
        text = parser.text()
    if not 0 < len(text.strip()) <= 64000:
        raise ValueError('Use a focused API documentation page containing 1–64000 text characters')
    return APIDocumentation(final_url, text)


class DocumentedOnboarding:
    def __init__(self, manager, log=print):
        self.manager = manager
        self.log = log

    def run(self, address, docs_url, name=None, *, expected_identity=None):
        if not isinstance(address, str) or not address.strip():
            raise ValueError('Supply the device IP or hostname')
        self.log('[onboard 1/4] Downloading API documentation…')
        document = fetch_documentation(docs_url)
        self.log(f'[onboard 2/4] Gemini: extracting a control mapping from {len(document.text)} documentation characters…')
        binding = extract_binding(document.text)
        validate(binding)
        mapping_hash = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
        self.log(f'[onboard 3/4] Runtime: generated-http · mapping {mapping_hash[:12]}')
        self.log(f"[onboard 3/4] Checking identity at {binding['info_path']} and state at {binding['state_path']} (read only)…")
        provenance = {'source': 'gemini-documentation', 'documentationUrl': document.url,
                      'documentationSha256': document.sha256, 'bindingSha256': mapping_hash,
                      'model': os.environ.get('GEMINI_MODEL', 'gemini-3.5-flash-lite'),
                      'generatedAt': datetime.now(timezone.utc).isoformat(),
                      'validation': {'identityRead': True, 'stateRead': True, 'writeTested': False}}
        if expected_identity is not None:
            provenance['discovery'] = {'family': 'wled', **expected_identity}
        listing = self.manager.register('generated-http', address.strip(), name=name,
                                        binding=binding, provenance=provenance,
                                        **({'expected_identity': expected_identity} if expected_identity is not None else {}))
        id_ = listing['activeDeviceId']
        self.log(f"[onboard 4/4] Saved {self.manager.records[id_]['name']} and generated mapping to {self.manager.path}")
        self.log('[onboard 4/4] Ready for Register object on the phone. Test its slider to verify a physical change.')
        return listing
