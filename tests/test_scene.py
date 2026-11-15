import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from ghostui_backend.devices import DeviceManager
from ghostui_backend.onboarding.registration import RegistrationService
from ghostui_backend.recognition import RecognitionService
from ghostui_backend.scene import SceneRecognitionService, unambiguous_matches
from ghostui_backend.server import handler_for
from test_devices import FakeWorker


class SceneTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hardware={}
        factory=lambda address,simulated,integration: FakeWorker(address,simulated,integration,self.hardware)
        self.manager=DeviceManager(self.temp.name,factory)
        self.addCleanup(self.manager.close)
        self.scene=SceneRecognitionService(self.manager)
        buffer=io.BytesIO()
        Image.new('RGB',(640,480),'blue').save(buffer,format='JPEG')
        self.image=base64.b64encode(buffer.getvalue()).decode()
        self.one=self.manager.register('wled','one',name='Ring light')['activeDeviceId']
        self.two=self.manager.register('marshall','two',name='Speaker')['activeDeviceId']

    def enroll(self,id_,count=1):
        record=self.manager.records[id_]
        service=RecognitionService(record['enrollmentId'],storage=self.manager.root/'vision')
        for _ in range(count): service.enroll(self.image,[0.1,0.1,0.5,0.6])
        return service

    def call(self,path,body=None,auth=True):
        handler=object.__new__(handler_for(None,8780,'phone',manager=self.manager))
        handler.path=path
        payload=json.dumps(body).encode()
        handler.headers={'Content-Length':str(len(payload))}
        if auth:handler.headers['Authorization']='Bearer phone'
        handler.rfile=io.BytesIO(payload)
        handler.reply=reply=Mock()
        (handler.do_GET if body is None else handler.do_POST)()
        args,kwargs=reply.call_args
        return args[0],args[1] if len(args)>1 else kwargs.get('code',200)

    def test_scene_bank_searches_both_devices_without_selecting_them(self):
        self.enroll(self.one,4);self.enroll(self.two,4)
        self.assertEqual(self.scene.status()['objects'],2)
        self.assertEqual(self.scene.status()['views'],8)
        self.assertEqual(self.manager.active.record['id'],self.two)
        mosaic,prompt=self.scene.reference()
        self.assertEqual(len(prompt['cls']),8)
        self.assertTrue((prompt['bboxes'][:,2]<=mosaic.width).all())
        self.assertTrue((prompt['bboxes'][:,3]<=mosaic.height).all())
        self.assertEqual(self.scene.identity_for_class(0)['deviceId'],self.one)
        self.assertEqual(self.scene.identity_for_class(4)['deviceId'],self.two)

    def test_enrollment_changes_invalidate_cached_prompts(self):
        first=self.enroll(self.one)
        self.scene.status();self.scene.prompted=True
        self.scene.status()
        self.assertTrue(self.scene.prompted)
        first.enroll(self.image,[0.2,0.2,0.4,0.5])
        self.scene.status()
        self.assertFalse(self.scene.prompted)
        first.clear()
        self.assertEqual(self.scene.status()['views'],0)

    def test_scene_does_not_include_simulations(self):
        simulated=self.manager.register('marshall','sim',simulated=True)['activeDeviceId']
        self.enroll(simulated)
        self.assertEqual(self.scene.status()['views'],0)

    def test_all_camera_and_registration_routes_require_pairing(self):
        for path,body in [('/mobile/scene/vision',None),('/mobile/scene/vision/detect',{'image':self.image}),
                          ('/mobile/registration',None),('/mobile/registration',{'deviceId':self.one})]:
            self.assertEqual(self.call(path,body,auth=False)[1],401)

    def test_scene_returns_device_identity_without_changing_active_connection(self):
        detection={'deviceId':self.one,'name':'Ring light','score':0.9,'box':[0.1,0.1,0.2,0.2]}
        with patch('ghostui_backend.scene.SceneRecognitionService.detect',return_value={
                'detections':[detection],'views':2,'latencyMs':10}):
            result,code=self.call('/mobile/scene/vision/detect',{'image':self.image})
        self.assertEqual((code,result['detections'][0]['deviceId']),(200,self.one))
        self.assertEqual(self.manager.active.record['id'],self.two)
        self.assertEqual(self.call('/mobile/scene/vision/detect',{'image':self.image,'deviceId':self.two})[1],400)

    def test_frontend_registration_exposes_only_real_device_names(self):
        self.manager.register('demo-light','simulated')
        with patch.dict('os.environ',{'HOMEASSISTANT_TOKEN':''}):
            result,code=self.call('/mobile/registration')
        self.assertEqual(code,200)
        self.assertEqual(result['devices'],[{'id':self.one,'name':'Ring light'},{'id':self.two,'name':'Speaker'}])
        chosen,code=self.call('/mobile/registration',{'deviceId':self.one})
        self.assertEqual((code,chosen['deviceId']),(200,self.one))
        self.assertEqual(self.call('/mobile/registration',{'deviceId':'invented'})[1],404)

    def test_homeassistant_entities_are_named_choices_not_protocol_options(self):
        fake=Mock()
        fake.call.return_value=[{'entity_id':'light.desk','state':'on',
            'attributes':{'friendly_name':'Desk lamp','brightness':128,'supported_color_modes':['brightness']}}]
        service=RegistrationService(self.manager)
        with patch.dict('os.environ',{'HOMEASSISTANT_TOKEN':'secret','HOMEASSISTANT_URL':'http://my-home:8123'}), \
             patch('ghostui_backend.onboarding.registration.HomeAssistantClient.from_env',return_value=fake):
            described=service.describe()
            lamp=described['devices'][-1]
            self.assertEqual(lamp['name'],'Desk lamp')
            self.assertEqual(set(lamp),{'id','name'})
            result=service.choose(lamp['id'])
            self.assertEqual(self.manager.records[result['deviceId']]['integrationId'],'homeassistant')
            self.assertNotIn('secret',json.dumps(described))

    def test_homeassistant_failure_keeps_direct_devices_available(self):
        with patch.dict('os.environ',{'HOMEASSISTANT_TOKEN':'secret'}), \
             patch('ghostui_backend.onboarding.registration.HomeAssistantClient.from_env',side_effect=OSError('Offline')):
            result=RegistrationService(self.manager).describe()
        self.assertEqual(len(result['devices']),2)
        self.assertIsNotNone(result['notice'])

    def test_fresh_profile_offers_saved_speaker_and_preserves_reference_views(self):
        shared=Path(self.temp.name)/'shared';shared.mkdir()
        record=dict(self.manager.records[self.two])
        (shared/'devices.json').write_text(json.dumps({'version':1,'devices':[record]}))
        source=RecognitionService(record['enrollmentId'],storage=shared/'vision')
        source.enroll(self.image,[0.1,0.1,0.5,0.6])
        profile=DeviceManager(shared/'phone-demo',self.manager.worker_factory)
        self.addCleanup(profile.close)
        with patch('ghostui_backend.onboarding.registration.ROOT',shared), \
             patch.dict('os.environ',{'HOMEASSISTANT_TOKEN':''}):
            service=RegistrationService(profile)
            choices=service.describe()['devices']
            self.assertEqual([row['name'] for row in choices],['Speaker'])
            id_=service.choose(choices[0]['id'])['deviceId']
            self.assertEqual(profile.records[id_]['integrationId'],'marshall')
            target=RecognitionService(profile.records[id_]['enrollmentId'],storage=profile.root/'vision')
            self.assertEqual(len(target.files()),1)
            self.assertEqual(len(source.files()),1)
            self.assertEqual(len(service.describe()['devices']),1)

    def test_duplicate_view_detections_merge_and_both_objects_remain_selectable(self):
        one={'deviceId':'one','score':0.9,'box':[0.1,0.1,0.2,0.3]}
        another_view={**one,'score':0.8,'box':[0.11,0.11,0.2,0.3]}
        two={'deviceId':'two','score':0.85,'box':[0.6,0.1,0.2,0.3]}
        self.assertEqual(unambiguous_matches([one,another_view,two]),[one,two])

    def test_ambiguous_identity_or_duplicate_physical_copies_hide_controls(self):
        one={'deviceId':'one','score':0.9,'box':[0.1,0.1,0.2,0.3]}
        wrong_id={**one,'deviceId':'two','score':0.8}
        self.assertEqual(unambiguous_matches([one,wrong_id]),[])
        copy={**one,'box':[0.6,0.1,0.2,0.3]}
        self.assertEqual(unambiguous_matches([one,copy]),[])

    def test_ambiguous_class_cannot_hide_its_competition_by_matching_two_objects(self):
        light={'deviceId':'light','score':0.8,'box':[0.1,0.1,0.2,0.3]}
        headphones={**light,'deviceId':'headphones','score':0.9}
        other_headphones={**headphones,'box':[0.6,0.1,0.2,0.3]}
        self.assertEqual(unambiguous_matches([light,headphones,other_headphones]),[])
