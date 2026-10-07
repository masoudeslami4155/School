#!/usr/bin/env python
"""Real Chromium: design in both pages, archive, edit and rich downloads."""
import json
from threading import Thread
from unittest.mock import patch
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
import ai_agent_test as base
from school_app import ai_design as design
base.save_provider();client=base.page_client();cookie=client.get_cookie('session').value
server=make_server('127.0.0.1',0,base.app,threaded=True)
Thread(target=server.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{server.server_port}'
try:
 with patch('school_app.ai_documents.request_chat_completion',return_value=json.dumps({'html':design.DEFAULT_LAYOUT})):
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1360,'height':1000});errors=[]
   page.on('pageerror',lambda e:errors.append(str(e)));page.context.add_cookies([{'name':'session','value':cookie,'url':url}])
   for route in ['/ai-documents','/ai-agent']:
    page.goto(url+route);page.locator('#aiDesignStudio > details > summary').click()
    page.locator('#designKind').select_option('table');page.locator('#designTitle').fill('گزارش مدرن کلاس')
    page.locator('#designBody').fill('کد\tنام\tوضعیت\n001\tدانش‌آموز آزمایشی\tحاضر\n002\tنمونهٔ دوم\tغایب')
    page.locator('#designPayload').click();page.locator('#designPayloadView').wait_for(state='visible')
    assert 'دانش‌آموز آزمایشی' not in page.locator('#designPayloadView').inner_text()
    page.locator('#designGenerate').click();page.wait_for_function("document.querySelector('#designStatus').textContent.includes('پیش‌نویس ذخیره شد')")
    page.frame_locator('#designPreview').locator('table').wait_for()
    assert 'دانش‌آموز آزمایشی' in page.frame_locator('#designPreview').locator('table').inner_text()
    for format in ['docx','xlsx','pdf_design']:
     with page.expect_download(timeout=45000) as download:page.locator('[data-design-export="'+format+'"]').click()
     file=download.value
     assert file.suggested_filename.endswith('.pdf' if format=='pdf_design' else '.'+format)
     if format=='pdf_design':file.save_as('/home/user/ai-design-462-preview.pdf')
    page.locator('#designOutput details summary').click()
    source=page.locator('#designSource').input_value();page.locator('#designSource').fill(source+'<p>اصلاح نسخهٔ دوم</p>');page.locator('#designSave').click()
    page.wait_for_function("document.querySelector('#designStatus').textContent.includes('نسخهٔ 2')")
    page.locator('#designOutput details summary').click()
    page.screenshot(path='/home/user/ai-design-462-'+route[1:]+'.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
    page.set_viewport_size({'width':1360,'height':1000})
   page.goto(url+'/ai-documents');page.wait_for_function("document.querySelector('#archiveSelect').options.length>=3")
   ident=page.locator('#archiveSelect option').nth(1).get_attribute('value')
   page.goto(url+'/ai-documents?document_id='+ident+'#documentArchive')
   page.wait_for_function("document.querySelector('#documentEditor').textContent.includes('اصلاح نسخهٔ دوم')")
   assert not errors,errors
   browser.close();print('PASS: both studios, private payload, generation, archive, edit, real Word/Excel/graphic PDF downloads, mobile, deep-link reload, no JS errors')
finally:server.shutdown()
