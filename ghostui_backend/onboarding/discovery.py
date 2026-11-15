"""Read-only WLED discovery. Advertisements identify candidates, not commands."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import ipaddress
import json
import re
from threading import Event, Lock

WLED_DOCUMENTATION = 'https://kno.wled.ge/interfaces/json-api/'
SERVICE = '_wled._tcp.local.'


def controller_address(host, port=80):
    address = ipaddress.IPv4Address(host)
    if (not address.is_private or address.is_loopback or address.is_multicast or
            address.is_unspecified or type(port) is not int or not 1 <= port <= 65535):
        raise ValueError('Expected a local controller address')
    return str(address) if port == 80 else f'{address}:{port}'


def probe_wled(address):
    """No redirects, credentials, writes or executable discovery metadata."""
    connection = http.client.HTTPConnection(address, timeout=2)
    try:
        connection.request('GET', '/json/info')
        response = connection.getresponse()
        if response.status != 200: raise ValueError('Controller did not answer')
        raw = response.read(65537)
        if len(raw) > 65536: raise ValueError('Controller response too large')
        info = json.loads(raw)
        if not isinstance(info, dict) or info.get('brand') != 'WLED':
            raise ValueError('Controller did not identify as WLED')
        mac = info.get('mac')
        if not isinstance(mac, str) or not re.fullmatch(r'[a-fA-F0-9]{12}', mac):
            raise ValueError('Missing WLED unit identity')
        name = info.get('name')
        if not isinstance(name, str) or not name.strip(): raise ValueError('Missing device name')
        name = ''.join(c for c in name if c.isprintable()).strip()[:80]
        return {'address': address, 'name': name or 'WLED light', 'mac': mac,
                'family': 'wled', 'documentation': WLED_DOCUMENTATION}
    finally:
        connection.close()


def advertised_controllers(wait=4):
    try:
        from zeroconf import IPVersion, ServiceBrowser, ServiceStateChange, Zeroconf
    except ImportError:
        raise ValueError('Install requirements-vision.txt on the Mac to enable discovery') from None
    names = set()
    lock = Lock()
    def changed(zeroconf, service_type, name, state_change):
        with lock:
            if state_change == ServiceStateChange.Removed: names.discard(name)
            elif len(names) < 24: names.add(name)
    with Zeroconf(ip_version=IPVersion.V4Only) as zc:
        browser = ServiceBrowser(zc, SERVICE, handlers=[changed])
        try: Event().wait(wait)
        finally: browser.cancel()
        with lock: selected = sorted(names)
        def resolve(name):
            info = zc.get_service_info(SERVICE, name, timeout=1000)
            if info:
                for host in info.parsed_addresses(IPVersion.V4Only):
                    try: return controller_address(host, info.port)
                    except ValueError: pass
        with ThreadPoolExecutor(max_workers=6) as pool:
            return sorted({address for address in pool.map(resolve, selected) if address})


def discover_wled():
    def probe(address):
        try: return probe_wled(address)
        except (OSError, ValueError, http.client.HTTPException): return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        devices = [item for item in pool.map(probe, advertised_controllers()) if item]
    return list({item['mac'].lower(): item for item in devices}.values())
