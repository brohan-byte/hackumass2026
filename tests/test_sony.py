import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ghostui_backend.devices import DeviceManager
from ghostui_backend.integrations.sony import SonyAdapter, SonyBridgeError
from ghostui_backend.integrations.mac_playback import MacPlaybackAdapter
from ghostui_backend.registry import ADAPTERS
from ghostui_backend.service import DeviceWorker
from ghostui_backend.onboarding.registration import RegistrationService


class SonyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.bridge=self.root/'fake-sony'
        self.commands=self.root/'commands.txt'
        self.metadata={'address':'aa:bb:cc:dd:ee:ff','model':'WH-1000XM5','firmware':'test',
            'capabilities':{'deviceId':'sony:aa:bb:cc:dd:ee:ff','name':'WH-1000XM5','controls':[
                {'id':'volume','label':'Volume','type':'number','min':0,'max':30,'step':1}]}}
        self.write_bridge()

    def write_bridge(self,error=None,ignore_write=False,request_error=None):
        self.bridge.write_text('''#!/usr/bin/env python3
import json,sys
from pathlib import Path
metadata='''+repr(self.metadata)+'''
error='''+repr(error)+'''
if error:
    print(json.dumps({'error':error}),flush=True)
    raise SystemExit(1)
print(json.dumps(metadata),flush=True)
volume=6
for line in sys.stdin:
    command=line.strip()
    if command=='quit':break
    with Path('''+repr(str(self.commands))+''').open('a') as log:log.write(command+'\\n')
    if '''+repr(request_error)+''':
        print(json.dumps({'error': '''+repr(request_error)+'''}),flush=True)
        continue
    if command.startswith('volume ') and not '''+repr(ignore_write)+''':volume=int(command.split()[1])
    print(json.dumps({'state':{'volume':volume}}),flush=True)
''')
        self.bridge.chmod(0o700)

    def adapter(self,*args,**kwargs):
        return SonyAdapter(*args,**kwargs,bridge=self.bridge)

    def test_read_only_startup_and_bounded_confirmed_volume(self):
        adapter=self.adapter()
        self.addCleanup(adapter.close)
        self.assertEqual(adapter.model,'WH-1000XM5')
        self.assertFalse(self.commands.exists())
        self.assertEqual(adapter.request(),{'volume':6})
        self.assertEqual(adapter.request(('volume',8)),{'volume':8})
        for bad in (-1,31,True,1.5):
            with self.assertRaises(ValueError):adapter.request(('volume',bad))
        self.assertEqual(self.commands.read_text().splitlines(),['state','volume 8'])
        adapter.close();self.assertIsNotNone(adapter.process.poll())

    def test_transport_error_and_wrong_model_do_not_create_fake_capabilities(self):
        self.write_bridge(error='Sony Bluetooth connection timed out.')
        with self.assertRaisesRegex(SonyBridgeError,'timed out'):self.adapter()
        self.metadata['model']='Other headphones';self.write_bridge()
        with self.assertRaisesRegex(SonyBridgeError,'identify an XM5'):self.adapter()
        self.assertFalse(self.commands.exists())

    def test_worker_uses_reported_state_not_desired_value_and_never_replays_write(self):
        self.write_bridge(ignore_write=True)
        with patch.dict(ADAPTERS,{'sony':self.adapter}):
            worker=DeviceWorker(device='sony');self.addCleanup(worker.close)
            with patch('ghostui_backend.service.time.monotonic',side_effect=[0,3]):
                with self.assertRaisesRegex(ValueError,'device reports 6'):worker.request(('volume',8))
        self.assertEqual(self.commands.read_text().splitlines(),['volume 8'])

    def test_registry_persists_resolved_address_and_reuses_same_device(self):
        with patch.dict(ADAPTERS,{'sony':self.adapter}):
            manager=DeviceManager(self.root/'registry')
            try:
                id_=manager.register('sony')['activeDeviceId']
                record=manager.records[id_]
                self.assertEqual(record['address'],'aa:bb:cc:dd:ee:ff')
                self.assertEqual(record['adapterProvenance']['source'],'existing-library')
                self.assertEqual(manager.active.worker.request(('volume',8)),{'volume':8})
            finally:manager.close()
            restored=DeviceManager(self.root/'registry')
            try:
                restored.select(restored.last_selected)
                self.assertEqual(restored.active.record['id'],id_)
                self.assertEqual(restored.active.worker.capabilities['deviceId'],id_)
            finally:restored.close()

    def test_failed_hardware_probe_does_not_persist_a_sony_device(self):
        self.write_bridge(error='Sony Bluetooth connection timed out.')
        manager=DeviceManager(self.root/'registry');self.addCleanup(manager.close)
        with patch.dict(ADAPTERS,{'sony':self.adapter}):
            with self.assertRaises(SonyBridgeError):manager.register('sony')
        self.assertEqual(manager.listing()['devices'],[])
        self.assertFalse(manager.path.exists())

    def test_mac_playback_is_explicitly_labeled_and_persists_audio_uid(self):
        self.metadata.update(controlSource='mac-playback',address='Sony-Audio-UID')
        self.metadata['capabilities']['name']='Sony XM5 · Mac playback'
        self.metadata['capabilities']['controls'][0].update(label='Mac volume',max=100)
        self.write_bridge()
        factory=lambda *args,**kwargs:MacPlaybackAdapter(*args,**kwargs,bridge=self.bridge)
        with patch.dict(ADAPTERS,{'sony-playback':factory}):
            manager=DeviceManager(self.root/'registry');self.addCleanup(manager.close)
            id_=manager.register('sony-playback')['activeDeviceId']
            record=manager.records[id_]
            self.assertEqual(record['address'],'Sony-Audio-UID')
            self.assertEqual(record['adapterProvenance']['source'],'macos-coreaudio')
            self.assertIn('Mac playback',record['name'])
            self.assertEqual(manager.active.worker.request(('volume',70)),{'volume':70})
            with self.assertRaises(ValueError):manager.active.worker.request(('volume',101))

    def test_mac_playback_rejects_private_protocol_metadata_and_output_changes(self):
        with self.assertRaisesRegex(SonyBridgeError,'Mac playback bridge'):
            MacPlaybackAdapter(bridge=self.bridge)
        self.metadata['controlSource']='mac-playback'
        self.write_bridge(request_error='Mac audio output changed. Select the saved XM5.')
        adapter=MacPlaybackAdapter(bridge=self.bridge);self.addCleanup(adapter.close)
        with self.assertRaisesRegex(SonyBridgeError,'output changed'):adapter.request(('volume',8))
        self.assertEqual(self.commands.read_text().splitlines(),['volume 8'])

    def test_profile_playback_option_verifies_connection_before_saving_once(self):
        profile=self.root/'profile';profile.mkdir()
        (profile/'registration-options.json').write_text(json.dumps({'version':1,'integrations':['sony-playback']}))
        manager=DeviceManager(profile);self.addCleanup(manager.close)
        service=RegistrationService(manager)
        factory=lambda *args,**kwargs:MacPlaybackAdapter(*args,**kwargs,bridge=self.bridge)
        with patch.dict(ADAPTERS,{'sony-playback':factory}),patch.dict('os.environ',{'HOMEASSISTANT_TOKEN':''}):
            choice=service.describe()['devices'][0]
            self.assertEqual(choice['name'],'Sony XM5 · Mac playback')
            self.assertEqual(manager.records,{})
            self.write_bridge(error='Select WH-1000XM5 in Sound Output first.')
            with self.assertRaisesRegex(SonyBridgeError,'Sound Output'):service.choose(choice['id'])
            self.assertFalse(manager.path.exists())
            self.metadata['controlSource']='mac-playback';self.write_bridge()
            saved=service.choose(choice['id'])['deviceId']
            self.assertEqual(manager.records[saved]['integrationId'],'sony-playback')
            self.assertEqual(service.describe()['devices'],[{'id':saved,'name':choice['name']}])
            self.assertEqual(self.commands.read_text().splitlines(),['state'])
