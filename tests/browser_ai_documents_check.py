#!/usr/bin/env python
"""Optional real Chromium regression. Synthetic Ollama tags/provider, isolated DB."""
import json
from threading import Thread
from unittest.mock import patch
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
import ai_agent_test as base
import importlib
D=importlib.import_module('school_app.ai_documents')
base.save_provider();client=base.page_client();cookie=client.get_cookie('session').value

def provider(config,messages,tools=None):
    if tools:return {'content':None,'tool_calls':[{'id':'test','type':'function','function':{'name':'test_connection','arguments':'{}'}}]}
    text=messages[-1]['content']
    if 'Return ONLY JSON' in text:return {'content':'{"ok":true}','tool_calls':[]}
    try:
        request=json.loads(text)
        if 'instruction' in request:return {'content':request['html']+'<p>اصلاح آزمایشی انجام شد.</p>','tool_calls':[]}
    except ValueError:pass
    return {'content':'OK','tool_calls':[]}

server=make_server('127.0.0.1',0,base.app,threaded=True);Thread(target=server.serve_forever,daemon=True).start()
url=f'http://127.0.0.1:{server.server_port}'
try:
 with patch.object(D,'_ollama_tags',return_value=[{'name':'fixture:7b','size':3*1024**3,'details':{'family':'fixture'}}]),patch.object(D,'request_chat_message',side_effect=provider):
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
   page.on('pageerror',lambda e:errors.append(str(e)));page.context.add_cookies([{'name':'session','value':cookie,'url':url}])
   page.goto(url+'/settings/ai-documents');page.get_by_role('button',name='fixture:7b — 3.0 GB',exact=True).wait_for()
   page.get_by_role('button',name='fixture:7b — 3.0 GB',exact=True).click()
   assert page.locator('#aiModel').input_value()=='fixture:7b'
   page.locator('#profileName').fill('اتصال آزمایشی مرورگر');page.locator('#profileForm button[type=submit]').click()
   page.wait_for_function("document.querySelector('#profileSelect').options.length===2")
   pid=page.locator('#profileSelect option').nth(1).get_attribute('value');page.locator('#profileSelect').select_option(pid)
   page.locator('#testSaved').click();page.wait_for_function("document.querySelector('#controlMessage').textContent.includes('\"tools\": true')")
   page.locator('#documentsAssignment').select_option(pid);page.locator('#savePolicy').click();page.get_by_text('سیاست‌ها و مدل پیش‌فرض هر کاربرد ذخیره شدند.',exact=True).wait_for()
   page.screenshot(path='/home/user/ai-settings-460.png',full_page=True)
   page.goto(url+'/ai-documents');page.locator('#aiGenerateLetter:not([disabled])').wait_for()
   page.locator('#aiStudentList input').nth(0).check();page.locator('#aiStudentList input').nth(1).check()
   page.locator('#documentSubject').fill('دعوت برای بررسی پرونده');page.locator('#documentRecipient').fill('اولیای گرامی');page.locator('#documentAttachments').fill('ندارد')
   page.locator('#aiBrief').fill('با سلام و احترام، لطفاً برای بررسی پروندهٔ دانش‌آموز به مدرسه مراجعه فرمایید.')
   page.locator('#aiGenerateLetter').click();page.wait_for_function("document.querySelector('#archiveSelect').options.length===3")
   page.locator('#documentEditor .letter-page').wait_for();page.wait_for_function("document.querySelector('#archiveStatus').textContent.includes('۲') || document.querySelector('#archiveStatus').textContent.includes('2')")
   cid=page.locator('#archiveSelect').input_value();assert cid
   page.locator('#flowDocument').click();page.wait_for_function("document.querySelector('#archiveStatus').textContent.includes('نسخه 2')")
   page.wait_for_function('window.aiPrintBlocked===false')
   page.locator('#revisionInstruction').fill('یک عبارت محترمانه به انتها اضافه کن.');page.locator('#reviseDocument').click()
   page.locator('#documentEditor').get_by_text('اصلاح آزمایشی انجام شد.',exact=True).wait_for()
   assert '[[FIELD_' not in page.locator('#documentEditor').inner_text()
   page.locator('#compareDocument').click();assert page.locator('#versionComparison').inner_text()
   page.locator('#documentEditor').evaluate("e=>{e.innerHTML+='<p>ویرایش دستی مرورگر</p>';e.dispatchEvent(new Event('input',{bubbles:true}));}")
   page.locator('#saveDocumentEdit').click();page.wait_for_function("document.querySelector('#archiveStatus').textContent.includes('نسخه 4')")
   page.once('dialog',lambda dialog:dialog.accept());page.locator('#issueDocument').click();page.wait_for_function("document.querySelector('#archiveStatus').textContent.includes('issued')")
   assert page.locator('#documentEditor').get_attribute('contenteditable')=='false'
   for button,suffix in [('exportWord','.docx'),('exportPdf','.pdf')]:
    with page.expect_download() as download:page.locator('#'+button).click()
    assert download.value.suggested_filename.endswith(suffix)
    if suffix=='.pdf':download.value.save_as('/home/user/ai-document-460-check.pdf')
   page.reload();page.wait_for_function("document.querySelector('#archiveSelect').options.length===3")
   page.locator('#archiveSelect').select_option(cid);page.locator('#archiveOpen').click();page.wait_for_function("document.querySelector('#archiveStatus').textContent.includes('issued')")
   assert 'ویرایش دستی مرورگر' in page.locator('#documentEditor').inner_text()
   page.locator('#documentArchive').scroll_into_view_if_needed();page.screenshot(path='/home/user/ai-documents-460.png',full_page=True)
   page.set_viewport_size({'width':390,'height':844});page.goto(url+'/settings/ai-documents');page.locator('#ollamaModels button').wait_for()
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
   page.goto(url+'/ai-documents');page.locator('#archiveRefresh').wait_for();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
   assert not errors,errors
   browser.close();print('PASS: Ollama discovery display, saved profile + health + assignment, batch drafts, revisions, manual edit, issuance, DOCX/PDF, reload, mobile, no JS errors')
finally:server.shutdown()
