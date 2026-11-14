"""Legacy Acton III BLE adapter. Wire protocol preserved from the working prototype."""
import asyncio
import time
SUFFIX = '-0000-1000-8000-00805f9b34fb'
VOLUME = '0000aa08' + SUFFIX
EQ = '0000aa16' + SUFFIX
CAPS = {'deviceId': 'speaker-1', 'name': 'Marshall Acton III', 'controls': [
    {'id': 'volume', 'label': 'Volume', 'type': 'number', 'min': 0, 'max': 31, 'step': 1},
    {'id': 'bass', 'label': 'Bass', 'type': 'number', 'min': 0, 'max': 10, 'step': 1},
    {'id': 'treble', 'label': 'Treble', 'type': 'number', 'min': 0, 'max': 10, 'step': 1}]}
LIMITS = {c['id']: (c['min'], c['max']) for c in CAPS['controls']}


async def discover_speaker():
    """Use scan.py-style discovery and probe.py-style read-only verification.

    Validate the model and legacy UUIDs observed in the actual probe output,
    rather than assuming any advertised Marshall name is compatible.
    """
    from bleak import BleakClient, BleakScanner
    print('Scanning for Marshall Acton III BLE devices (12 seconds)…', flush=True)
    discovered = await BleakScanner.discover(timeout=12.0, return_adv=True)
    candidates = []
    for device, advertisement in discovered.values():
        name = advertisement.local_name or device.name or ''
        if any(word in name.lower() for word in ('acton', 'marshall')):
            candidates.append((device, name))
    if not candidates:
        raise ValueError('No named Marshall/Acton BLE device found. Turn on the '
                         'speaker, close the Marshall app, move closer and retry. '
                         'An explicit scanned address can still be supplied.')
    verified = []
    for device, name in candidates:
        print(f'Probing {name} ({device.address})…', flush=True)
        try:
            async with BleakClient(device, timeout=12) as client:
                model = (await asyncio.wait_for(client.read_gatt_char(
                    '00002a24-0000-1000-8000-00805f9b34fb'), timeout=5)
                    ).decode(errors='replace').strip(' \x00')
                if model.upper() != 'ACTON III':
                    print(f'  Skipping model {model!r}', flush=True)
                    continue
                for uuid in (VOLUME, EQ):
                    ch = client.services.get_characteristic(uuid)
                    if ch is None or not {'read', 'write'}.issubset(ch.properties):
                        raise ValueError(f'Missing legacy read/write control {uuid}')
                volume = bytes(await asyncio.wait_for(client.read_gatt_char(VOLUME), 5))
                eq = bytes(await asyncio.wait_for(client.read_gatt_char(EQ), 5))
                if (len(volume) != 1 or len(eq) != 5 or volume[0] > 31
                        or eq[0] > 10 or eq[4] > 10):
                    raise ValueError('Unexpected control packet format or range')
                verified.append(device)
                print('  Verified ACTON III with legacy volume/EQ controls.', flush=True)
        except Exception as exc:
            print(f'  Probe failed: {exc}', flush=True)
    if not verified:
        raise ValueError('No compatible Acton III passed the read-only probe. '
                         'Check Bluetooth permissions and close other BLE clients.')
    if len(verified) > 1:
        addresses = ', '.join(device.address for device in verified)
        raise ValueError(f'Multiple compatible speakers found: {addresses}. '
                         'Supply the intended address explicitly to avoid controlling the wrong speaker.')
    return verified[0]

class Adapter:
    def __init__(self, address, simulated=False):
        self.address, self.simulated = address, simulated
        self.state = {'volume': 5, 'bass': 5, 'treble': 5}
        self.client = None
        self.validated = False
        # Keep the same event loop alive across HTTP requests for CoreBluetooth.
        self.runner = asyncio.Runner()

    async def connect(self):
        if self.client is not None and self.client.is_connected:
            return
        from bleak import BleakClient
        self.validated = False
        self.client = BleakClient(self.address, timeout=15)
        await self.client.connect()
        await self.read_state()
        self.validated = True

    async def read_state(self):
        volume = bytes(await self.client.read_gatt_char(VOLUME))
        eq = bytearray(await self.client.read_gatt_char(EQ))
        if len(volume) != 1 or len(eq) != 5:
            raise ValueError('Unexpected volume/EQ packet format')
        state = {'volume': volume[0], 'bass': eq[0], 'treble': eq[4]}
        if any(not lo <= state[key] <= hi for key, (lo, hi) in LIMITS.items()):
            raise ValueError('Device state outside configured demo ranges')
        self.state = state
        return dict(state)

    async def transact(self, change=None):
        if self.simulated:
            if change:
                self.state[change[0]] = change[1]
            return dict(self.state)
        try:
            await self.connect()
            if not self.validated:
                raise ValueError('Connection has not passed state validation')
            if change:
                field, value = change
                if field == 'volume':
                    # No reconnect or pre-read needed on an already validated link.
                    await self.client.write_gatt_char(VOLUME, bytes([value]), response=True)
                else:
                    # Preserve the other EQ fields, including physical knob changes.
                    eq = bytearray(await self.client.read_gatt_char(EQ))
                    if len(eq) != 5:
                        raise ValueError('Unexpected EQ packet format; no write attempted')
                    eq[0 if field == 'bass' else 4] = value
                    await self.client.write_gatt_char(EQ, eq, response=True)
            return await self.read_state()
        except BaseException:
            # Do not automatically replay a write after a failure or timeout.
            self.validated = False
            if self.client is not None:
                try:
                    await asyncio.wait_for(self.client.disconnect(), timeout=3)
                except Exception:
                    pass
                self.client = None
            raise

    def request(self, change=None):
        started = time.perf_counter()
        try:
            return self.runner.run(asyncio.wait_for(self.transact(change), timeout=25))
        finally:
            print(f"{'Command' if change else 'Read'} round trip: "
                  f"{(time.perf_counter() - started) * 1000:.0f} ms", flush=True)

    def close(self):
        try:
            if self.client is not None:
                self.runner.run(asyncio.wait_for(self.client.disconnect(), timeout=3))
        finally:
            self.runner.close()

class MarshallAdapter(Adapter):
    @property
    def capabilities(self):
        return CAPS

    def discover(self):
        self.address = self.runner.run(discover_speaker())

