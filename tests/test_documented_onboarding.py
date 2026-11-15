import copy
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import Mock, patch

from ghostui_backend.adaptergen import extract_binding
from ghostui_backend.devices import DeviceManager
from ghostui_backend.onboarding.documented import (APIDocumentation, DocumentedOnboarding,
    DocumentationText, SecureRedirects, documentation_url, fetch_documentation)
from ghostui_backend.onboarding.registration import RegistrationService
from ghostui_backend.registry import ADAPTERS
from ghostui_backend.server import handler_for

DOCS_URL='https://example.org/level-api'
BINDING={'family':'bench-light','label':'Brightness','match_field':'brand','match_value':'Bench',
         'identity_field':'serial','name_field':'name','info_path':'/identity','state_path':'/status',
         'command_path':'/set','value_field':'level','power_field':'enabled','wire_max':1000,'control_id':'brightness'}
DOCS='GET /identity: brand Bench, persistent unique serial, name. GET /status: level 0..1000 and boolean enabled. POST /set accepts level and enabled.'


class DocumentedOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.state={'level':420,'enabled':True}
        self.brand='Bench'
        self.writes=[]
        owner=self
        class Controller(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,body):
                raw=json.dumps(body).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(raw)))
                self.end_headers();self.wfile.write(raw)
            def do_GET(self):
                if self.path=='/identity':self.reply({'brand':owner.brand,'serial':'unit-123','name':'Bench light'})
                elif self.path=='/status':self.reply(owner.state)
                else:self.send_error(404)
            def do_POST(self):
                if self.path!='/set':return self.send_error(404)
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.writes.append(body);owner.state.update(body);self.reply({'ok':True})
        self.http=ThreadingHTTPServer(('127.0.0.1',0),Controller)
        thread=Thread(target=self.http.serve_forever,daemon=True);thread.start()
        self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)
        self.address=f'127.0.0.1:{self.http.server_port}'
        self.manager=DeviceManager(self.temp.name);self.addCleanup(self.manager.close)
        self.logs=[]
        self.onboarding=DocumentedOnboarding(self.manager,self.logs.append)
        patcher=patch('ghostui_backend.onboarding.documented.fetch_documentation',
                      return_value=APIDocumentation(DOCS_URL,DOCS))
        self.fetch=patcher.start();self.addCleanup(patcher.stop)
        patcher=patch('ghostui_backend.adaptergen.gemini_json',return_value=copy.deepcopy(BINDING))
        self.gemini=patcher.start();self.addCleanup(patcher.stop)
        patcher=patch.dict(os.environ,{'GEMINI_API_KEY':'test-key'})
        patcher.start();self.addCleanup(patcher.stop)

    def run_onboarding(self):
        return self.onboarding.run(self.address,DOCS_URL,'New desk light')['activeDeviceId']

    def test_generated_mapping_controls_different_protocol_without_catalog_edit(self):
        # The fixture deliberately differs from WLED in routes, identity, fields
        # and numeric scale. No built-in WLED code may be used.
        with patch.dict(ADAPTERS,{'wled':Mock(side_effect=AssertionError('Built-in adapter used'))}):
            id_=self.run_onboarding()
            self.assertEqual(self.writes,[])  # Onboarding must not actuate hardware.
            self.assertIn(DOCS,self.gemini.call_args.args[0])
            self.fetch.assert_called_once_with(DOCS_URL)
            session=self.manager.active
            self.assertEqual(session.worker.integration_id,'generated-http')
            self.assertEqual(session.worker.request(),{'brightness':42})
            self.assertEqual(session.worker.request(('brightness',27)),{'brightness':27})
            self.assertEqual(self.writes,[{'level':270,'enabled':True}])
            self.assertEqual(session.worker.request(('brightness',0)),{'brightness':0})
            self.assertEqual(self.writes[-1],{'enabled':False})
        record=json.loads(self.manager.path.read_text())['devices'][0]
        self.assertEqual(record['id'],id_)
        self.assertEqual(record['adapterBinding'],BINDING)
        provenance=record['adapterProvenance']
        self.assertEqual(provenance['source'],'gemini-documentation')
        self.assertEqual(provenance['documentationUrl'],DOCS_URL)
        self.assertFalse(provenance['validation']['writeTested'])
        self.assertNotIn('test-key',json.dumps(record))

    def test_restart_reuses_saved_mapping_without_fetch_or_generation(self):
        id_=self.run_onboarding()
        self.manager.close()
        restored=DeviceManager(self.temp.name);self.addCleanup(restored.close)
        self.fetch.reset_mock();self.gemini.reset_mock()
        restored.select(restored.last_selected)
        self.assertEqual(restored.active.record['id'],id_)
        self.assertEqual(restored.active.worker.request(('brightness',61)),{'brightness':61})
        self.fetch.assert_not_called();self.gemini.assert_not_called()

    def test_regeneration_preserves_instance_when_model_changes_family_name(self):
        id_=self.run_onboarding()
        self.gemini.return_value={**BINDING,'family':'another-family-name'}
        again=self.run_onboarding()
        self.assertEqual(id_,again)
        self.assertEqual(len(self.manager.records),1)

    def test_generated_device_enters_names_only_phone_registration(self):
        id_=self.run_onboarding()
        with patch.dict(os.environ,{'HOMEASSISTANT_TOKEN':''}):
            result=RegistrationService(self.manager).describe()
        self.assertEqual(result['devices'],[{'id':id_,'name':'New desk light'}])
        Handler=handler_for(None,8780,'phone',manager=self.manager)
        handler=object.__new__(Handler)
        handler.path=f'/mobile/devices/{id_}/command'
        body=json.dumps({'capability':'brightness','value':39}).encode()
        handler.headers={'Authorization':'Bearer phone','Content-Length':str(len(body))}
        handler.rfile=io.BytesIO(body);handler.reply=Mock()
        handler.do_POST()
        self.assertEqual(handler.reply.call_args.args[0],{'brightness':39})
        self.assertEqual(self.writes,[{'level':390,'enabled':True}])
        self.assertEqual(self.manager.active.layout.current()['deviceId'],id_)

    def test_invalid_generation_does_not_change_saved_devices_or_write(self):
        original=self.manager.register('demo-light')['activeDeviceId']
        disk=self.manager.path.read_bytes()
        self.gemini.return_value={**BINDING,'command_path':'https://attacker.example/control'}
        with self.assertRaises(ValueError):self.run_onboarding()
        self.assertEqual(self.manager.path.read_bytes(),disk)
        self.assertEqual(self.manager.active.record['id'],original)
        self.assertEqual(self.writes,[])

    def test_identity_or_state_failure_is_not_saved_or_actuated(self):
        self.brand='unrelated'
        with self.assertRaisesRegex(ValueError,'identity'):self.run_onboarding()
        self.assertFalse(self.manager.path.exists())
        self.brand='Bench';self.state['level']=True
        with self.assertRaisesRegex(ValueError,'Invalid level'):self.run_onboarding()
        self.assertFalse(self.manager.path.exists())
        self.assertEqual(self.writes,[])

    def test_no_key_or_upstream_failure_never_selects_a_fallback(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':''}),patch('ghostui_backend.adaptergen.load_environment'):
            with self.assertRaisesRegex(ValueError,'GEMINI_API_KEY'):self.run_onboarding()
        self.gemini.assert_not_called()
        self.gemini.side_effect=TimeoutError('upstream failed')
        with self.assertRaisesRegex(ValueError,'no adapter was installed'):self.run_onboarding()
        self.assertFalse(self.manager.path.exists());self.assertEqual(self.writes,[])


class DocumentationTests(unittest.TestCase):
    def test_cleaning_preserves_api_examples_and_removes_hidden_content(self):
        parser=DocumentationText()
        parser.feed('<html><nav>Ignore menu</nav><script>evil()</script><style>.bad{}</style>'
                    '<main><h1>API</h1><pre>{&quot;level&quot;:42}</pre><p>POST /set</p></main></html>')
        text=parser.text()
        self.assertIn('{"level":42}',text);self.assertIn('POST /set',text)
        self.assertNotIn('evil()',text);self.assertNotIn('Ignore menu',text)

    def test_documentation_url_keeps_https_and_drops_fragment(self):
        self.assertEqual(documentation_url(DOCS_URL+'#control'),DOCS_URL)
        for bad in ('http://example.org/docs','file:///tmp/docs','https://user:secret@example.org/docs'):
            with self.assertRaises(ValueError):documentation_url(bad)
        with self.assertRaises(ValueError):SecureRedirects().redirect_request(None,None,302,'',{},'http://example.org/docs')

    def test_fetch_checks_size_type_and_extracts_text(self):
        from email.message import Message
        from ghostui_backend.onboarding import documented
        response=Mock()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.geturl.return_value=DOCS_URL
        headers=Message();headers['Content-Type']='text/html; charset=utf-8'
        response.headers=headers;response.read.return_value=b'<h1>API</h1><pre>GET /identity</pre>'
        with patch.object(documented,'build_opener') as opener:
            opener.return_value.open.return_value=response
            result=fetch_documentation(DOCS_URL)
            self.assertIn('GET /identity',result.text)
            self.assertEqual(len(result.sha256),64)
            response.read.return_value=b'x'*(documented.MAX_DOWNLOAD+1)
            with self.assertRaisesRegex(ValueError,'1 MiB'):fetch_documentation(DOCS_URL)
            headers.replace_header('Content-Type','application/pdf')
            with self.assertRaisesRegex(ValueError,'HTML'):fetch_documentation(DOCS_URL)
