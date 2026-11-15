import copy
import io
import json
import os
import re
import unittest
from unittest.mock import Mock, patch
from ghostui_backend.service import DeviceWorker
from ghostui_backend.server import handler_for
from ghostui_backend.generation import generate, template, validate_layout
from ghostui_backend.contracts import numeric_limits

class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.worker = DeviceWorker(simulated=True)
        self.addCleanup(self.worker.close)
        self.Handler = handler_for(self.worker, 8780, 'phone-test-token')

    def call(self, path, body=None, headers=None):
        handler = object.__new__(self.Handler)
        handler.path = path
        payload = json.dumps(body).encode()
        handler.headers = {'Host': '127.0.0.1:8780', 'Content-Length': str(len(payload)), **(headers or {})}
        handler.rfile = io.BytesIO(payload)
        handler.reply = reply = Mock()
        (handler.do_GET if body is None else handler.do_POST)()
        call = reply.call_args
        return call.args[0], call.args[1] if len(call.args)>1 else call.kwargs.get('code',200)

    def test_browser_page_and_commands(self):
        page, code = self.call('/')
        self.assertEqual(code,200)
        self.assertIn('Generate interface',page)
        token = re.search("const token='([^']+)'", page)[1]
        state, code = self.call('/command', {'capability':'volume','value':8}, {'X-GhostUI-Token':token})
        self.assertEqual((code,state['volume']),(200,8))
        self.assertEqual(self.call('/state')[0]['volume'],8)

    def test_phone_existing_contract(self):
        h = {'Authorization':'Bearer phone-test-token'}
        caps, code = self.call('/mobile/capabilities',headers=h)
        self.assertEqual((code,caps['deviceId']),(200,'speaker-1'))
        self.assertTrue(caps['simulated'])
        state, code = self.call('/mobile/command',{'capability':'volume','value':9},h)
        self.assertEqual((code,state['volume']),(200,9))

    def test_phone_auth_required(self):
        self.assertEqual(self.call('/mobile/state')[1],401)

    def test_phone_rejects_web_origin(self):
        self.assertEqual(self.call('/mobile/state',headers={
            'Authorization':'Bearer phone-test-token','Origin':'http://evil.test'})[1],403)

    def test_invalid_commands_never_execute(self):
        for value in (32,-1,True,1.5):
            with self.assertRaises(ValueError):self.worker.request(('volume',value))
        with self.assertRaises(ValueError):self.worker.request(('power',1))
        self.assertEqual(self.worker.request()['volume'],5)

    def test_generation_fallback_and_token(self):
        page,_=self.call('/')
        token=re.search("generationToken='([^']+)'",page)[1]
        with patch.dict(os.environ,{},clear=True), patch('ghostui_backend.generation.load_environment'):
            result,code=self.call('/generate',{'preference':'minimal'}, {'X-Generation-Token':token})
        self.assertEqual((code,result['source']),(200,'template'))
        self.assertEqual(self.call('/generate',{'preference':'minimal'})[1],403)

    def test_second_device_without_route_changes(self):
        light=DeviceWorker(device='demo-light')
        self.addCleanup(light.close)
        self.assertTrue(light.simulated)
        self.assertEqual(light.request(('brightness',70))['brightness'],70)
        self.assertNotIn('volume',light.capabilities['controls'][0]['id'])
        self.assertEqual(validate_layout(template(light.capabilities),light.capabilities)['title'],'Demo Light')
        with self.assertRaises(ValueError):light.request(('volume',8))
        with self.assertRaises(ValueError):light.request(('brightness',101))

    def test_manifest_rejects_duplicate_controls(self):
        caps=copy.deepcopy(self.worker.capabilities)
        caps['controls'].append(caps['controls'][0])
        with self.assertRaises(ValueError):numeric_limits(caps)

    def test_generated_unknown_binding_rejected(self):
        layout=template(self.worker.capabilities)
        layout['controls'][0]['bind']='invented'
        with self.assertRaises(ValueError):validate_layout(layout,self.worker.capabilities)

    def test_delayed_confirmation_does_not_repeat_write(self):
        with patch.object(self.worker.adapter,'request',side_effect=[{'volume':9},{'volume':13}]) as call:
            self.assertEqual(self.worker.request(('volume',13))['volume'],13)
            self.assertEqual(call.call_args_list[1].args,())

    def test_mismatch_is_not_success(self):
        with patch.object(self.worker.adapter,'request',return_value={'volume':9}), patch('ghostui_backend.service.time.monotonic',side_effect=[0,3]):
            with self.assertRaisesRegex(ValueError,'requested 13'):
                self.worker.request(('volume',13))

    def test_recognition_auth_and_routing(self):
        self.assertEqual(self.call('/mobile/vision/detect', {'image':'test'})[1],401)
        h={'Authorization':'Bearer phone-test-token'}
        status,code=self.call('/mobile/vision',headers=h)
        self.assertEqual(code,200)
        self.assertIn('views',status)
        with patch('ghostui_backend.recognition.RecognitionService.detect',return_value={'detections':[],'views':1,'latencyMs':10}) as detector:
            body,code=self.call('/mobile/vision/detect',{'image':'test'},h)
            self.assertEqual((code,body['latencyMs']),(200,10))
            detector.assert_called_once_with('test')

    def test_recognition_rejects_unexpected_body(self):
        h={'Authorization':'Bearer phone-test-token'}
        self.assertEqual(self.call('/mobile/vision/enroll',{'image':'test'},h)[1],400)

    def test_onboarding_routes_require_pairing_and_verify_without_writes(self):
        self.assertEqual(self.call('/mobile/onboarding')[1], 401)
        self.assertEqual(self.call('/mobile/onboarding/verify', {})[1], 401)
        h = {'Authorization': 'Bearer phone-test-token'}
        summary, code = self.call('/mobile/onboarding', headers=h)
        self.assertEqual((code, summary['selectedIntegration']), (200, 'marshall'))
        with unittest.mock.patch.object(self.worker, 'request', wraps=self.worker.request) as request:
            verified, code = self.call('/mobile/onboarding/verify', {}, h)
            request.assert_called_once_with()
        self.assertEqual(code, 200)
        self.assertFalse(verified['physicalIdentityConfirmed'])
        with unittest.mock.patch.object(self.worker, 'request') as request:
            self.assertEqual(self.call('/mobile/onboarding/verify', {'value': 5}, h)[1], 400)
            request.assert_not_called()

    def test_mobile_ar_layout_auth_input_and_generation(self):
        h = {'Authorization': 'Bearer phone-test-token'}
        self.assertEqual(self.call('/mobile/layout')[1], 401)
        self.assertEqual(self.call('/mobile/layout', {})[1], 401)
        with patch('ghostui_backend.ar_layout.ARLayoutService.resolve') as resolve:
            for body in ({'refresh': 1}, {'capabilities': {}}, []):
                self.assertEqual(self.call('/mobile/layout', body, h)[1], 400)
            resolve.assert_not_called()
            resolve.return_value = {'layout': template(self.worker.capabilities),
                                    'source': 'ai', 'notice': 'Gemini', 'cached': False}
            result, code = self.call('/mobile/layout', {'refresh': True}, h)
            self.assertEqual((code, result['source']), (200, 'ai'))
            resolve.assert_called_once_with(True)
        with patch('ghostui_backend.ar_layout.ARLayoutService.current', return_value={'source': 'ai'}):
            self.assertEqual(self.call('/mobile/layout', headers=h), ({'source': 'ai'}, 200))

if __name__=='__main__':unittest.main()
