#!/usr/bin/env python
"""Optional browser E2E with synthetic DB/model; pip install playwright."""
import json
import time
from threading import Thread
from unittest.mock import patch
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
import ai_agent_test as fixture

app=fixture.app
fixture.save_provider()
client=fixture.page_client()
cookie=client.get_cookie('session').value
calls=[]
def provider(config,messages,tools=None):
    calls.append(messages[-1]['role'])
    def tool(name,args,id):
        return {'content':None,'tool_calls':[{'id':id,'type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]}
    if messages[-1]['role']=='user':
        if messages[-1]['content']=='ادامه':
            assert any(m.get('content')=='فهرست دانش‌آموزان' for m in messages)
            return {'content':'زمینهٔ گفتگو حفظ شده است.','tool_calls':[]}
        return tool('search_students',{'page_size':2},'search')
    if messages[-1]['tool_call_id']=='search':
        data=json.loads(messages[-1]['content'])
        assert 'AGT-1' in messages[-1]['content']
        time.sleep(1.2) # browser must see progress before final text
        return tool('generate_report_html',{'result_id':data['result_id'],'title':'گزارش مستند','columns':['first_name','last_name'],'headers':['نام','نام خانوادگی']},'report')
    return {'content':'دو ردیف از سه دانش‌آموز؛ نتیجه صفحه‌بندی شده است.','tool_calls':[]}

server=make_server('127.0.0.1',0,app,threaded=True)
Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
try:
 with patch.object(fixture.AGENT,'request_chat_message',side_effect=provider):
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':1360,'height':1000}); errors=[]; requests=[]
   page.on('pageerror',lambda error:errors.append(str(error)))
   page.on('request',lambda req: requests.append((req.method,req.url)))
   page.context.add_cookies([{'name':'session','value':cookie,'url':base}])
   page.goto(base+'/ai-agent')
   page.locator('#chatInput').fill('فهرست دانش‌آموزان'); page.locator('#sendBtn').click()
   page.locator('#agentStatusText').filter(has_text='دریافت نتیجه').wait_for()
   page.locator('.agent-report').wait_for(); page.locator('#sendBtn:not([disabled])').wait_for()
   assert page.locator('.agent-report tbody tr').count()==2
   assert page.locator('.agent-source').count()==1
   cid=page.locator('#conversationSelect').input_value(); assert cid
   page.reload(); page.locator('.agent-report').wait_for()
   assert page.locator('#conversationSelect').input_value()==cid
   page.locator('#chatInput').fill('ادامه');page.locator('#sendBtn').click()
   page.get_by_text('زمینهٔ گفتگو حفظ شده است.',exact=True).wait_for()
   page.locator('#sendBtn:not([disabled])').wait_for()
   page.locator('.agent-source summary').click()
   with page.expect_download() as download:
    page.get_by_text('Excel همین نتیجه',exact=True).click()
   assert download.value.suggested_filename.endswith('.xlsx')
   page.screenshot(path='/home/user/agent-459-check.png',full_page=True)
   page.locator('#newChat').click(); assert not page.locator('.agent-report').count()
   page.locator('#conversationSelect').select_option(cid); page.locator('.agent-report').wait_for()
   page.locator('#renameChat:not([disabled])').wait_for()
   page.once('dialog',lambda dialog:dialog.accept('آزمون مرورگر'))
   page.locator('#renameChat').click()
   page.wait_for_function("document.querySelector('#conversationSelect').selectedOptions[0].textContent==='آزمون مرورگر'")
   page.once('dialog',lambda dialog:dialog.accept());page.locator('#clearChat').click()
   page.wait_for_function("document.querySelector('#conversationSelect').value===''")
   page.reload();page.locator('#chatInput:not([disabled])').wait_for()
   assert not page.locator('.agent-report').count()
   streams=[r for r in requests if '/ai-agent/stream' in r[1]]
   assert len(streams)==2 and all(method=='POST' and '?' not in url for method,url in streams),streams
   assert not errors,errors
   page.set_viewport_size({'width':390,'height':844});page.reload();page.locator('#chatInput:not([disabled])').wait_for()
   assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2')
   browser.close()
   print('PASS: actual progress, POST transport, immutable report, refresh/history, Excel, switch/rename/delete, mobile, no JS errors')
finally:
 server.shutdown()
