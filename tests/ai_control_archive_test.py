#!/usr/bin/env python
"""4.60 isolated regression. Synthetic records, keys and HTTP/Ollama server."""
import importlib
import io
import json
import unittest
from http.server import BaseHTTPRequestHandler,HTTPServer
from threading import Thread
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
import ai_agent_test as base
from school_app import ai_control as control
from school_app.database import get_db
D=importlib.import_module('school_app.ai_documents')
R=importlib.import_module('school_app.routes.ai_documents')

class ControlArchiveTests(unittest.TestCase):
    def setUp(self):
        self.ctx=base.app.app_context();self.ctx.push()
        with get_db() as conn:
            conn.execute("DELETE FROM app_settings WHERE key LIKE 'ai_control:%' OR key LIKE 'ai_document_archive:%' OR key LIKE 'ai_document_receipt:%'")
            self.ids=[r['id'] for r in conn.execute('SELECT id FROM students ORDER BY id')]
        base.save_provider()
        self.client=base.page_client();base.set_session(self.client,'admin',user_id=860)
        self.other=base.page_client();base.set_session(self.other,'manager',user_id=861)
    def tearDown(self):self.ctx.pop()
    def post(self,path,data,client=None):return (client or self.client).post(path,json=data,headers={'X-CSRF-Token':base.CSRF})
    def setting(self,data):
        state=self.client.get('/settings/ai-documents?api=1').get_json()['state']
        return self.post('/settings/ai-documents',{**data,'revision':state['revision']})
    def profile(self,remote=False):
        p={'name':'آزمایشی','provider':'openai-compatible' if remote else 'ollama','base_url':'https://example.invalid/v1' if remote else D.DEFAULT_OLLAMA_URL,'model':'test-model','api_key':'synthetic-secret' if remote else ''}
        rv=self.setting({'action':'profile_save','profile':p});self.assertEqual(rv.status_code,200,rv.data)
        return next(reversed(rv.json['state']['profiles']))
    def letter(self,ids=None,brief='با احترام، لطفاً برای بررسی پرونده مراجعه فرمایید.'):
        rv=self.post('/ai-documents/generate-letter',{'student_ids':ids or self.ids[:1],'brief':brief,'subject':'موضوع مستقل','recipient':'اولیای گرامی','attachments':'یک برگ','paper':'a4-portrait'})
        self.assertEqual(rv.status_code,200,rv.data);return rv.json['documents']
    def mutate(self,doc,action,**kw):return self.post('/ai-documents',{'action':action,'id':doc['id'],'revision':doc['revision'],**kw})

    def test_settings_models_reads_real_local_http_tags(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                assert self.path=='/api/tags'
                data=json.dumps({'models':[{'name':'fixture:7b','size':2*1024**3,'details':{'family':'fixture','parameter_size':'7B'}}]}).encode()
                self.send_response(200);self.end_headers();self.wfile.write(data)
        server=HTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            rv=self.client.get(f'/settings/ai-documents/models?url=http://127.0.0.1:{server.server_port}/v1')
            self.assertTrue(rv.json['online']);self.assertEqual(rv.json['models'],['fixture:7b'])
            self.assertEqual(rv.json['entries'][0]['size'],'2.0 GB')
        finally:server.shutdown();server.server_close()
        self.assertEqual(self.client.get('/settings/ai-documents/models?url=https://example.org').status_code,400)
        source=base.ROOT.joinpath('static/ai_documents_settings.js').read_text()
        self.assertNotIn('{{',source)

    def test_ollama_empty_differs_from_offline(self):
        with patch.object(D,'_ollama_tags',return_value=[]):self.assertTrue(D.ollama_status(D.DEFAULT_OLLAMA_URL)['online'])
        with patch.object(D,'_ollama_tags',return_value=None):self.assertFalse(D.ollama_status(D.DEFAULT_OLLAMA_URL)['online'])

    def test_profile_credentials_never_reused_for_new_destination(self):
        pid=self.profile(True)
        public=self.client.get('/settings/ai-documents?api=1').json
        self.assertNotIn('synthetic-secret',json.dumps(public))
        self.assertNotIn('api_key_encrypted',json.dumps(public))
        p=public['state']['profiles'][pid]
        p.update(base_url='https://different.invalid/v1',api_key='')
        rv=self.setting({'action':'profile_save','profile':p});self.assertEqual(rv.status_code,400)
        with get_db() as conn:self.assertEqual(control.private(control.read(conn)['profiles'][pid])['api_key'],'synthetic-secret')

    def test_legacy_destination_change_requires_fresh_key(self):
        with get_db() as conn:
            D.save_provider_config(conn,{'provider':'openai-compatible','base_url':'https://first.invalid/v1','model':'a','api_key':'legacy-test'})
            with self.assertRaises(ValueError):D.save_provider_config(conn,{'provider':'openai-compatible','base_url':'https://second.invalid/v1','model':'a'})

    def test_redirect_does_not_forward_credentials(self):
        hits=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                hits.append(self.path)
                if self.path=='/start':self.send_response(302);self.send_header('Location','/target');self.end_headers()
                else:self.send_response(200);self.end_headers()
        server=HTTPServer(('127.0.0.1',0),Handler);Thread(target=server.serve_forever,daemon=True).start()
        try:
            with self.assertRaises(HTTPError):D.urlopen(Request(f'http://127.0.0.1:{server.server_port}/start',headers={'Authorization':'Bearer fake'}))
            self.assertEqual(hits,['/start'])
        finally:server.shutdown();server.server_close()

    def test_profile_health_and_unsaved_probe(self):
        pid=self.profile()
        replies=[{'content':'OK'},{'content':'{"ok":true}'},{'content':None,'tool_calls':[{'function':{'name':'test_connection'}}]}]
        with patch.object(D,'request_chat_message',side_effect=replies) as request:
            rv=self.setting({'action':'test','id':pid});self.assertEqual(rv.status_code,200);self.assertTrue(rv.json['test']['tools'])
            self.assertNotIn('AGT-',str(request.call_args_list))
        with get_db() as conn:self.assertEqual(control.read(conn)['profiles'][pid]['health']['status'],'ok')
        rv=self.setting({'action':'test','draft':{'provider':'openai-compatible','base_url':'https://test.invalid/v1','model':'t'}})
        self.assertEqual(rv.status_code,400)

    def test_separate_assignments_user_override_and_deleted_profile(self):
        a=self.profile();b=self.profile(True)
        rv=self.setting({'action':'policy_save','assignments':{'documents':a,'agent':b},'policy':dict(control.POLICY)})
        self.assertEqual(rv.status_code,200)
        with get_db() as conn:
            self.assertEqual(D.effective_private_provider_config(conn,860,'documents')['profile_id'],a)
            self.assertEqual(D.effective_private_provider_config(conn,860,'agent')['profile_id'],b)
        self.post('/ai-agent/chat',{'action':'profile','profile_id':a})
        with get_db() as conn:
            self.assertEqual(D.effective_private_provider_config(conn,860,'agent')['profile_id'],a)
            self.assertEqual(D.effective_private_provider_config(conn,861,'agent')['profile_id'],b)
        self.setting({'action':'profile_delete','id':a})
        self.assertEqual(self.client.get('/ai-agent').status_code,200)
        with get_db() as conn:self.assertFalse(D.effective_private_provider_config(conn,860,'agent')['configured'])

    def test_upgrade_preserves_legacy_user_local_choice(self):
        pid=self.profile(True)
        self.setting({'action':'policy_save','assignments':{'documents':pid,'agent':pid},'policy':dict(control.POLICY)})
        with get_db() as conn:
            conn.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('ai_documents:provider_selection:860',json.dumps({'provider':'ollama','model':'old-local:7b'})))
            self.assertEqual(D.effective_public_provider_config(conn,860)['model'],'old-local:7b')
            control.select(conn,860,'documents','')
            self.assertEqual(D.effective_public_provider_config(conn,860)['id'],pid)
            self.assertEqual(D.effective_public_provider_config(conn,860,'agent')['model'],'old-local:7b')
        with get_db() as conn:conn.execute('DELETE FROM app_settings WHERE key=?',('ai_documents:provider_selection:860',))

    def test_policy_blocks_remote_agent_until_explicit_consent(self):
        pid=self.profile(True)
        self.setting({'action':'policy_save','assignments':{'agent':pid},'policy':dict(control.POLICY)})
        with patch.object(base.AGENT,'request_chat_message',return_value={'content':'پاسخ','tool_calls':[]}) as model:
            self.assertEqual(self.post('/ai-agent/chat',{'query':'سلام','allow_external_data':True}).status_code,400);model.assert_not_called()
            self.setting({'action':'policy_save','assignments':{'agent':pid},'policy':{**control.POLICY,'agent_remote':True}})
            self.assertEqual(self.post('/ai-agent/chat',{'query':'سلام'}).status_code,400)
            self.assertEqual(self.post('/ai-agent/chat',{'query':'سلام','allow_external_data':True}).status_code,200)

    def test_explicit_key_removal_disables_remote_profile(self):
        pid=self.profile(True)
        state=self.client.get('/settings/ai-documents?api=1').json['state']
        profile=state['profiles'][pid];profile.update(clear_key=True)
        response=self.setting({'action':'profile_save','profile':profile})
        self.assertEqual(response.status_code,200,response.data)
        self.assertFalse(response.json['state']['profiles'][pid]['enabled'])
        self.assertFalse(response.json['state']['profiles'][pid]['api_key_set'])

    def test_remote_generation_uses_placeholders_and_local_substitution(self):
        records=[{'student_name':'نام محرمانه آزمایشی','grade':'۳','class_name':'الف','school_name':'مدرسه محرمانه','academic_year':'1405-1406','today':'1405/07/15'}]
        captured=[]
        def fake(config,messages,tools=None):
            captured.append(json.loads(messages[-1]['content']))
            return json.dumps({'title':'نامه','html':'<p>{{student_name}}</p><p>مهر و امضا</p>'})
        with patch.object(D,'request_chat_completion',side_effect=fake):
            _,output=D.generate_document({'provider':'openai-compatible'},'letter','نامهٔ رسمی',records)
        self.assertNotIn('نام محرمانه آزمایشی',json.dumps(captured,ensure_ascii=False))
        self.assertEqual(captured[0]['students'][0]['student_name'],'{{student_name}}')
        self.assertIn('نام محرمانه آزمایشی',output)

    def test_revision_conflict_and_settings_rollback(self):
        pid=self.profile()
        self.assertEqual(self.post('/settings/ai-documents',{'action':'profile_delete','id':pid,'revision':0}).status_code,400)
        rv=self.setting({'action':'rollback','target':0});self.assertEqual(rv.status_code,200);self.assertEqual(rv.json['state']['profiles'],{})
        self.assertEqual(self.other.get('/settings/ai-documents?api=1').status_code,403)

    def test_usage_budget_and_no_prompt_storage(self):
        self.setting({'action':'policy_save','assignments':{},'policy':{**control.POLICY,'daily_requests':1}})
        config={'provider':'ollama','base_url':D.DEFAULT_OLLAMA_URL,'model':'fixture','api_key':''}
        payload={'choices':[{'message':{'content':'OK'}}],'usage':{'prompt_tokens':10,'completion_tokens':2}}
        with patch.object(D,'urlopen',return_value=io.BytesIO(json.dumps(payload).encode())):
            D.request_chat_message(config,[{'role':'user','content':'DO-NOT-LOG-THIS'}])
        with self.assertRaises(D.AIProviderError):D.request_chat_message(config,[{'role':'user','content':'x'}])
        with get_db() as conn:
            usage=control.usage(conn);self.assertEqual(usage['requests'],1);self.assertEqual(usage['recent'][0]['prompt_tokens'],10)
            self.assertNotIn('DO-NOT-LOG-THIS',json.dumps(usage))

    def test_batch_letters_and_archive_ownership(self):
        docs=self.letter(self.ids[:2]);self.assertEqual(len(docs),2)
        self.assertNotEqual(docs[0]['record']['student_name'],docs[1]['record']['student_name'])
        self.assertIn('موضوع مستقل',docs[0]['html']);self.assertIn('اولیای گرامی',docs[0]['html'])
        for d in docs:
            self.assertEqual(self.client.get('/ai-documents?api=1&id='+d['id']).status_code,200)
            self.assertEqual(self.other.get('/ai-documents?api=1&id='+d['id']).status_code,400)

    def test_edit_restore_issue_idempotency_and_void(self):
        doc=self.letter()[0]
        edited=self.mutate(doc,'edit',html=doc['html']+'<p>ویرایش</p><script>alert(1)</script>',title='ویرایش‌شده')
        self.assertEqual(edited.status_code,200);new=edited.json['document'];self.assertNotIn('<script',new['html'])
        self.assertEqual(self.mutate(doc,'edit',html='stale').status_code,400)
        restored=self.mutate(new,'restore',target=1).json['document'];self.assertEqual(restored['html'],doc['html'])
        issued=self.mutate(restored,'issue');self.assertEqual(issued.status_code,200,issued.data)
        self.assertTrue(issued.json['document']['number'])
        again=self.mutate(restored,'issue');self.assertEqual(again.json['document']['number'],issued.json['document']['number'])
        self.assertEqual(self.mutate(issued.json['document'],'edit',html='x').status_code,400)
        self.assertEqual(self.mutate(issued.json['document'],'delete').status_code,400)
        void=self.mutate(issued.json['document'],'void',reason='آزمون');self.assertEqual(void.json['document']['status'],'void')

    def test_long_letter_flows_and_direct_exports(self):
        doc=self.letter(brief=('این یک متن بلند آزمایشی برای بررسی چندصفحه‌ای شدن نامه است.\n'*35))[0]
        self.assertIn('ai-flow-letter',doc['html']);self.assertNotIn('overflow:hidden',doc['html'])
        for fmt,magic in [('docx',b'PK'),('pdf',b'%PDF')]:
            rv=self.post('/ai-documents',{'action':'export','id':doc['id'],'format':fmt})
            self.assertEqual(rv.status_code,200,rv.data[:200]);self.assertTrue(rv.data.startswith(magic));self.assertGreater(len(rv.data),1000)

    def test_receipt_requires_specific_record_and_rechecks_before_issue(self):
        with get_db() as conn:source=conn.execute('SELECT id FROM monthly_service ORDER BY id LIMIT 1').fetchone()[0]
        body={'document_type':'receipt','student_ids':self.ids[:1],'brief':'گواهی وضعیت','paper':'a4-portrait'}
        self.assertEqual(self.post('/ai-documents/generate',body).status_code,400)
        def generated(config,kind,brief,records):
            return 'رسید','<article class="ai-document-copy"><p>'+' — '.join(str(v) for k,v in records[0].items() if not k.startswith('_'))+'</p></article>'
        with patch.object(R,'generate_document',side_effect=generated):
            rv=self.post('/ai-documents/generate',{**body,'service_id':source})
        self.assertEqual(rv.status_code,200,rv.data);doc=rv.json['documents'][0]
        self.assertEqual(doc['record']['_service_id'],source)
        self.assertEqual(self.mutate(doc,'edit',html='x').status_code,400)
        with get_db() as conn:conn.execute('UPDATE monthly_service SET paid_amount=paid_amount+1 WHERE id=?',(source,))
        try:self.assertEqual(self.mutate(doc,'issue').status_code,400)
        finally:
            with get_db() as conn:conn.execute('UPDATE monthly_service SET paid_amount=paid_amount-1 WHERE id=?',(source,))
        issued=self.mutate(doc,'issue');self.assertEqual(issued.status_code,200,issued.data)
        with patch.object(R,'generate_document',side_effect=generated):duplicate=self.post('/ai-documents/generate',{**body,'service_id':source}).json['documents'][0]
        self.assertEqual(self.mutate(duplicate,'issue').status_code,400)

    def test_revision_short_fields_do_not_corrupt_tokens_or_persian_text(self):
        doc=self.letter(self.ids[-1:])[0]
        from school_app import ai_document_store as store
        def identity(config,messages,tools=None):return json.loads(messages[-1]['content'])['html']
        with patch.object(D,'request_chat_completion',side_effect=identity):
            rv=self.mutate(doc,'revise',instruction='متن را حفظ کن')
        self.assertEqual(rv.status_code,200,rv.data)
        updated=rv.json['document']
        self.assertNotIn('[[FIELD_',updated['html'])
        self.assertEqual(store.text(updated['html']),store.text(doc['html']))

    def test_form_autosave_is_per_user_and_excludes_consent(self):
        rv=self.post('/ai-documents',{'action':'form_save','form':{'aiBrief':'متن بازیابی','student_ids':self.ids,'allow_external_data':True}})
        self.assertEqual(rv.status_code,200)
        form=self.client.get('/ai-documents?api=1').json['form'];self.assertEqual(form['aiBrief'],'متن بازیابی');self.assertNotIn('allow_external_data',form)
        self.assertNotEqual(self.other.get('/ai-documents?api=1').json['form'].get('aiBrief'),'متن بازیابی')

    def test_remote_payload_anonymized_and_missing_invitation_fields(self):
        pid=self.profile(True);self.setting({'action':'policy_save','assignments':{'documents':pid},'policy':dict(control.POLICY)})
        rv=self.post('/ai-documents',{'action':'payload_preview','document_type':'letter','student_ids':self.ids[:1],'brief':'دعوت'})
        self.assertEqual(rv.status_code,200);self.assertEqual(rv.json['payload']['students'][0]['student_name'],'{{student_name}}')
        with patch.object(R,'generate_document') as model:
            rv=self.post('/ai-documents/generate',{'document_type':'invitation','student_ids':self.ids[:1],'brief':'دعوت','allow_external_data':True})
            self.assertEqual(rv.status_code,400);model.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
