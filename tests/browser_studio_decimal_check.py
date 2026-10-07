#!/usr/bin/env python
"""Optional real-browser regression: pip install playwright; playwright install chromium.
Uses the isolated fixture database and an ephemeral loopback server; no real data.
"""
from playwright.sync_api import sync_playwright
from threading import Thread
from werkzeug.serving import make_server
import shutil
import print_studio_routes_test as fixture
app=fixture.app
client=app.test_client()
fixture.login(client,'admin')
cookie=client.get_cookie('session').value
server=make_server('127.0.0.1',0,app,threaded=True)
Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
docs=['service_request','service_receipt','service_drivers','attendance_students','attendance_teachers','folder_labels','student_info','wall_cards','student_filters','school_statistics','student_certificate','ai_letter']
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.context.add_cookies([{'name': 'session', 'value': cookie, 'url': base}])
  for doc in docs:
   page.goto(base+'/report-print-layouts?document='+doc);page.wait_for_load_state('networkidle')
   studio=page.locator('[data-studio-document]');actual=studio.get_attribute('data-studio-document');assert actual==doc,(doc,actual)
   el=page.locator('.pla-element[data-element-key], .pla-driver-table, .rpl-movable, [data-cert-element], [data-letter-element]').filter(visible=True).first
   el.scroll_into_view_if_needed();box=el.bounding_box();x=box['x']+box['width']*.4;y=box['y']+box['height']*.5
   styles=lambda: page.locator('.pla-element[data-element-key], .pla-driver-table, .rpl-movable, [data-cert-element], [data-letter-element]').evaluate_all('xs=>xs.map(x=>x.getAttribute("style"))')
   before_style=styles()
   page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+13.37,y+9.23,steps=5);page.mouse.up()
   assert styles() != before_style, (doc,'drag did not change position')
   invalid=page.locator('input[type=number]').evaluate_all('(xs)=>xs.filter(x=>!x.checkValidity()).map(x=>[x.outerHTML,x.value,x.validationMessage])')
   assert not invalid,(doc,invalid)
   vals=page.locator('input[type=number][step="0.01"]').evaluate_all('xs=>xs.map(x=>x.value)')
   # Explicit hundredths entry, then save through the actual browser validation path.
   num=page.locator('input[type=number][step="0.01"]').first
   value=num.evaluate('x=>Math.min(Number(x.max||100),Math.max(Number(x.min||0),Number(x.value||0)+.37)).toFixed(2)')
   num.fill(value);num.dispatch_event('input');num.dispatch_event('change')
   form=num.locator('xpath=ancestor::form');assert form.evaluate('f=>f.checkValidity()'),doc
   with page.expect_navigation(): form.locator('button[type=submit]').first.click()
   assert page.url.startswith(base+'/report-print-layouts'),(doc,page.url)
   assert abs(float(page.locator('input[type=number][step="0.01"]').first.input_value())-float(value))<.001,(doc,value)
   print(doc,'drag + hundredths + browser save/reload OK')
  assert not errors,errors
  page.goto(base+'/my-settings');page.locator('[name=apply_color_palette][value=electropop]').click();page.goto(base+'/');page.wait_for_load_state("networkidle")
  bg=page.evaluate('getComputedStyle(document.body).backgroundImage');assert 'gradient' in bg
  page.emulate_media(media='print');assert 'gradient' not in page.evaluate('getComputedStyle(document.body).backgroundImage')
  print('Screen gradient / physical print separation OK')
  page.emulate_media(media='screen')
  from school_app.user_preferences import COLOR_PALETTES
  for key in COLOR_PALETTES:
   page.goto(base+'/my-settings');page.locator('[name=apply_color_palette][value="'+key+'"]').click()
   for path in ('/', '/report-print-layouts?document=service_drivers', '/contact-book/print'):
    page.goto(base+path)
    assert page.locator('html').get_attribute('data-ui-palette')==key
    for mode in ('light','dark'):
     page.evaluate('(t)=>document.documentElement.dataset.theme=t',mode)
     assert 'gradient' in page.evaluate('getComputedStyle(document.body).backgroundImage')
   print(key, 'global gradient day/night OK')
  browser.close()
finally:
 server.shutdown()
 shutil.rmtree(fixture._tmp,ignore_errors=True)
 if not fixture._credentials_existed:
  fixture._credentials.unlink(missing_ok=True)
