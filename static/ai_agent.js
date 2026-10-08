/* AI Agent Chat JavaScript */
(function () {
  'use strict';
  var el = function (id) { return document.getElementById(id); };
  var agent = el('aiAgent');
  if (!agent) return;

  var chatUrl = agent.dataset.chatUrl || '';
  var streamUrl = agent.dataset.streamUrl || '';
  var applyUrl = agent.dataset.applyUrl || '';
  var csrfToken = agent.dataset.csrf || '';
  var configured = agent.dataset.configured === '1';
  var idleLabel = agent.dataset.idleLabel || 'آنلاین — آمادهٔ پاسخگویی';
  var messagesEl = el('messages');
  var inputEl = el('chatInput');
  var sendBtn = el('sendBtn');
  var clearBtn = el('clearChat');
  var dotEl = el('agentDot');
  var statusEl = el('agentStatusText');

  var history = [];
  var conversationId = null;
  var conversationSelect = el("conversationSelect");
  var isBusy = false;

  function setBusy(busy) {
    isBusy = busy;
    dotEl.className = 'ai-agent__dot' + (busy ? ' busy' : (configured ? '' : ' error'));
    statusEl.textContent = busy ? 'در حال پردازش...' : idleLabel;
    sendBtn.disabled = busy || !configured;
    inputEl.disabled = busy || !configured;
    [clearBtn, el('newChat'), el('renameChat'), el('agentProfile'), el('resetAgentProfile'), conversationSelect].forEach(function (button) { if (button) button.disabled = busy; });
  }

  function flagError(message) {
    dotEl.className = 'ai-agent__dot error';
    statusEl.textContent = message;
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  }

  var FONT_FACES = ['Regular', 'Medium', 'SemiBold', 'Bold', 'ExtraBold', 'Black']
    .map(function (name, index) {
      var weight = [400, 500, 600, 700, 800, 900][index];
      return '@font-face{font-family:Vazirmatn;src:url(\'/static/Vazirmatn-' + name +
        '.woff2\') format(\'woff2\');font-weight:' + weight + ';font-display:block}';
    }).join('');

  // جدول ساختهشده با ابزار گزارش، مستقل از صفحه چاپ میشود تا خروجی A4 تمیز باشد.
  function printReport(card) {
    var body = card.querySelector('.agent-report__body');
    if (!body) return;
    var frame = document.createElement('iframe');
    frame.setAttribute('aria-hidden', 'true');
    frame.style.cssText = 'position:fixed;inset-inline-start:-10000px;width:0;height:0;border:0';
    document.body.appendChild(frame);
    var printed = false;
    function startPrint() {
      if (printed) return;
      var body = frame.contentDocument && frame.contentDocument.body;
      // بارگذاری اولیهٔ about:blank نباید پنجرهٔ چاپ خالی باز کند.
      if (!body || !body.childNodes.length) return;
      printed = true;
      frame.contentWindow.focus();
      frame.contentWindow.print();
      setTimeout(function () { frame.remove(); }, 1500);
    }
    frame.onload = startPrint;
    var doc = frame.contentWindow.document;
    doc.open();
    doc.write('<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>' +
      FONT_FACES +
      'body{margin:0;padding:12mm;font-family:Vazirmatn,Tahoma,Arial,sans-serif;direction:rtl;color:#111}' +
      'h4{margin:0 0 10px;font-size:16px}' +
      'table.agent-table{width:100%;border-collapse:collapse;font-size:12px}' +
      'table.agent-table th,table.agent-table td{border:1px solid #444;padding:5px 7px;text-align:right}' +
      'table.agent-table thead th{background:#eef2f6}' +
      '@media print{@page{size:A4;margin:10mm}}' +
      '</style></head><body>' + body.innerHTML + '</body></html>');
    doc.close();
    // اگر رویداد load پیش از نوشتن سند تمام شده باشد، دوباره تلاش می‌کنیم.
    setTimeout(startPrint, 120);
  }

  function addReportCard(body, report) {
    var card = document.createElement('div');
    card.className = 'agent-report';
    var head = document.createElement('div');
    head.className = 'agent-report__head';
    var title = document.createElement('strong');
    title.textContent = report.title || 'گزارش آمادهٔ چاپ';
    var printBtn = document.createElement('button');
    printBtn.type = 'button';
    printBtn.className = 'btn btn--outline btn--sm';
    printBtn.innerHTML = '<i class="cil-print" aria-hidden="true"></i> چاپ جدول';
    printBtn.addEventListener('click', function () { printReport(card); });
    head.appendChild(title);
    head.appendChild(printBtn);
    var reportBody = document.createElement('div');
    reportBody.className = 'agent-report__body';
    // محتوای گزارش را خود سرور از دادهٔ پایگاه داده ساخته و پاکسازی کرده است.
    reportBody.innerHTML = report.html || '';
    var saved = reportBody.querySelector('[data-archive-id]');
    if(saved && /^[a-f0-9]{32}$/.test(saved.dataset.archiveId)) {
      var link=document.createElement('a');link.className='btn btn--outline btn--sm';
      link.textContent='باز کردن سند ذخیره‌شده / PDF، Word، Excel';
      link.href=agent.dataset.documentsUrl+'?document_id='+encodeURIComponent(saved.dataset.archiveId)+'#documentArchive';
      head.appendChild(link);
    }

    card.appendChild(head);
    card.appendChild(reportBody);
    body.appendChild(card);
  }

  function applyChange(card, proposal) {
    var status = card.querySelector('.agent-change__status');
    var applyBtn = card.querySelector('[data-apply]');
    var cancelBtn = card.querySelector('[data-cancel]');
    applyBtn.disabled = true;
    status.classList.remove('is-error');
    status.textContent = 'در حال اجرا…';
    fetch(applyUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ change_id: proposal.change_id })
    }).then(function (response) {
      return response.json().then(function (data) { return { ok: response.ok && data.ok, data: data }; });
    }).then(function (out) {
      if (!out.ok) throw new Error((out.data && out.data.error) || 'اجرای تغییر ممکن نشد.');
      var result = out.data.result || {};
      if (!(Number(result.affected) > 0)) throw new Error('هیچ رکوردی تحت تأثیر قرار نگرفت؛ تغییر ثبت نشد. از دستیار پیشنهاد اصلاح‌شده بخواهید.');
      card.classList.add('is-done');
      status.textContent = 'اجرا شد؛ ' + (result.affected || 0) + ' ردیف تغییر کرد.';
      cancelBtn.disabled = true;
      addMessage('bot', 'تغییر تأییدشده اجرا شد (' + (result.affected || 0) + ' ردیف).' +
        (result.summary ? ' ' + result.summary : ''));
      history.push({ role: 'assistant', content: 'تغییر اجرا شد: ' + (result.summary || result.sql || '') });
    }).catch(function (error) {
      status.textContent = error.message;
      status.classList.add('is-error');
      applyBtn.disabled = false;
    });
  }

  // تغییر پیشنهادی دستیار تا وقتی کاربر «تأیید و اجرا» را نزند اجرا نمیشود.
  function addChangeCard(body, proposal) {
    var card = document.createElement('div');
    card.className = 'agent-change';
    var head = document.createElement('div');
    head.className = 'agent-change__head';
    head.innerHTML = '<i class="cil-warning" aria-hidden="true"></i>';
    var headText = document.createElement('strong');
    headText.textContent = 'تغییر پیشنهادی — هنوز اجرا نشده';
    head.appendChild(headText);
    var summary = document.createElement('p');
    summary.textContent = proposal.summary || 'تغییر در پایگاه داده';
    var sql = document.createElement('pre');
    sql.className = 'agent-change__sql';
    sql.textContent = proposal.sql || '';
    var actions = document.createElement('div');
    actions.className = 'agent-change__actions';
    var applyBtn = document.createElement('button');
    applyBtn.type = 'button';
    applyBtn.className = 'btn btn--primary btn--sm';
    applyBtn.dataset.apply = '1';
    applyBtn.textContent = 'تأیید و اجرا';
    applyBtn.addEventListener('click', function () { applyChange(card, proposal); });
    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn btn--outline btn--sm';
    cancelBtn.dataset.cancel = '1';
    cancelBtn.textContent = 'انصراف';
    cancelBtn.addEventListener('click', function () {
      card.classList.add('is-cancelled');
      card.querySelector('.agent-change__status').textContent = 'لغو شد؛ هیچ تغییری اجرا نشد.';
      applyBtn.disabled = true;
      cancelBtn.disabled = true;
    });
    var status = document.createElement('span');
    status.className = 'agent-change__status';
    status.setAttribute('role', 'status');
    actions.appendChild(applyBtn);
    actions.appendChild(cancelBtn);
    actions.appendChild(status);
    card.appendChild(head);
    card.appendChild(summary);
    card.appendChild(sql);
    card.appendChild(actions);
    body.appendChild(card);
  }

  function addMessage(role, text, toolCalls, extras) {
    var msg = document.createElement('div');
    msg.className = 'msg msg--' + role;
    var avatar = document.createElement('div');
    avatar.className = 'msg__avatar';
    avatar.innerHTML = role === 'user'
      ? '<i class="cil-user" aria-hidden="true"></i>'
      : '<i class="cil-robot" aria-hidden="true"></i>';
    var body = document.createElement('div');
    body.className = 'msg__body';
    var textDiv = document.createElement('div');
    textDiv.className = 'msg__text';
    textDiv.innerHTML = escapeHtml(text).replace(/\n/g, '<br>');
    body.appendChild(textDiv);
    ((extras && extras.reports) || []).forEach(function (report) { addReportCard(body, report); });
    ((extras && extras.sources) || []).forEach(function (source) { addSource(body, source); });
    ((extras && extras.proposals) || []).forEach(function (proposal) { addChangeCard(body, proposal); });
    if (toolCalls && toolCalls.length > 0) {
      var toolDiv = document.createElement('div');
      toolDiv.className = 'msg__tool-call';
      toolDiv.textContent = 'ابزارها: ' + toolCalls.map(function (tc) {
        return tc.function + '(' + (tc.arguments || '{}') + ')';
      }).join(', ');
      body.appendChild(toolDiv);
    }
    msg.appendChild(avatar);
    msg.appendChild(body);
    messagesEl.appendChild(msg);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addTyping() {
    var msg = document.createElement('div');
    msg.className = 'msg msg--bot';
    msg.id = 'typingMsg';
    var avatar = document.createElement('div');
    avatar.className = 'msg__avatar';
    avatar.innerHTML = '<i class="cil-robot" aria-hidden="true"></i>';
    var body = document.createElement('div');
    body.className = 'msg__body typing-indicator';
    body.innerHTML = '<span></span><span></span><span></span>';
    msg.appendChild(avatar);
    msg.appendChild(body);
    messagesEl.appendChild(msg);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function removeTyping() {
    var t = el('typingMsg');
    if (t) t.remove();
  }

  async function jsonRequest(payload) {
    var response = await fetch(chatUrl, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken}, body:JSON.stringify(payload)});
    var data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'درخواست انجام نشد.');
    return data;
  }

  if(el('resetAgentProfile'))el('resetAgentProfile').addEventListener('click',()=>{el('agentProfile').value='';el('agentProfile').dispatchEvent(new Event('change'));});
  if(el('agentProfile')) el('agentProfile').addEventListener('change',async function(){try{await jsonRequest({action:'profile',profile_id:this.value});location.reload();}catch(error){alert(error.message);}});

  function addSource(body, source) {
    var card = document.createElement('details'); card.className='agent-source';
    var meta=source.meta || {};
    var summary=document.createElement('summary');
    summary.textContent='منبع داده · ' + (meta.row_count == null ? 'خلاصه' : meta.row_count + ' ردیف') + ' · ' + (meta.coverage || '');
    card.appendChild(summary);
    var text=document.createElement('pre');
    var sourceNames={search_students:'جستجوی دانش‌آموزان',get_attendance:'حضور و غیاب',get_service_fees:'مالی سرویس',get_school_summary:'خلاصهٔ مدرسه',get_statistics:'آمار',query_database:'پرس‌وجوی داده',transform_result:'مرتب‌سازی/فیلتر نتیجه'};
    var extracted=new Intl.DateTimeFormat('fa-IR',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Tehran'}).format(new Date(meta.extracted_at));
    text.textContent='ابزار: '+(sourceNames[meta.source] || meta.source)+'\nزمان استخراج (تهران): '+extracted+
      '\nفیلترها: '+JSON.stringify(meta.effective_filters || meta.filters || {})+
      (meta.population ? '\nجمعیت: '+meta.population : '')+
      (meta.total == null ? '' : '\nکل منطبق: '+meta.total+' · صفحه: '+meta.page)+
      '\nشناسه: '+source.result_id;
    card.appendChild(text);
    function exportButton(all) {
      var button=document.createElement('button'); button.type='button'; button.className='btn btn--outline btn--sm';
      button.textContent=all ? 'Excel کامل منبع (استخراج تازه)' : 'Excel همین نتیجه';
      button.addEventListener('click',async function () {
        button.disabled=true;
        try {
          var response=await fetch(chatUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken},
            body:JSON.stringify({action:'export',conversation_id:conversationId,result_id:source.result_id,all:all})});
          if (!response.ok) { var err=await response.json(); throw new Error(err.error || 'خطای خروجی'); }
          var url=URL.createObjectURL(await response.blob()); var a=document.createElement('a');
          a.href=url; a.download='agent-result.xlsx'; a.click(); setTimeout(function(){URL.revokeObjectURL(url);},3000);
        } catch (error) { alert(error.message); }
        finally { button.disabled=false; }
      });
      card.appendChild(button);
    }
    if(meta.source==='search_students'){var link=document.createElement('a');link.className='btn btn--outline btn--sm';link.textContent='ساخت سند برای همین نتیجه';link.href='/ai-documents?conversation_id='+encodeURIComponent(conversationId||'')+'&result_id='+encodeURIComponent(source.result_id);card.appendChild(link);}
    exportButton(false);
    if (['search_students','get_attendance','get_service_fees'].indexOf(meta.source)>=0) exportButton(true);
    body.appendChild(card);
  }

  async function refreshConversations(loadId) {
    var response=await fetch(chatUrl+(loadId ? '?conversation_id='+encodeURIComponent(loadId) : ''));
    if (!response.ok) throw new Error('خواندن گفتگوها ممکن نشد.');
    var data=await response.json();
    conversationSelect.innerHTML='';
    var empty=document.createElement('option'); empty.value=''; empty.textContent='گفتگوی تازه'; conversationSelect.appendChild(empty);
    (data.conversations || []).forEach(function(c){var option=document.createElement('option'); option.value=c.id; option.textContent=c.title; conversationSelect.appendChild(option);});
    if (loadId && data.conversation) {
      conversationId=loadId; history=[]; messagesEl.innerHTML='';
      data.conversation.messages.forEach(function(m){
        history.push({role:m.role,content:m.content});
        addMessage(m.role==='user' ? 'user' : 'bot',m.content,[],{reports:m.reports || [],sources:m.sources || []});
      });
    }
    conversationSelect.value=conversationId || '';
    return data;
  }

  async function sendStream(query) {
    if (!configured || !query.trim() || isBusy) return;
    var prior=history.slice();
    addMessage('user',query); history.push({role:'user',content:query});
    setBusy(true); addTyping();
    var accumulated='', calls=[], reports=[], proposals=[], sources=[], done=false, failed=false;
    function handle(data) {
      if (data.event==='conversation') conversationId=data.data.id;
      else if (data.event==='token') {
        accumulated+=data.data;
        var typing=el('typingMsg'); if (typing) typing.querySelector('.msg__body').textContent=accumulated;
      } else if (data.event==='tool_start') {
        calls.push({function:data.data.function,arguments:'{}'});
        statusEl.textContent='در حال اجرای '+data.data.function+'…';
      } else if (data.event==='tool_end') {
        if (calls.length) calls[calls.length-1].result=data.data.result_summary;
        statusEl.textContent='دریافت نتیجه و آماده‌سازی پاسخ…';
      } else if (data.event==='source') { if(!sources.some(function(s){return s.result_id===data.data.result_id;})) sources.push(data.data); }
      else if (data.event==='report') reports.push(data.data);
      else if (data.event==='pending_change') proposals.push(data.data);
      else if (data.event==='error') { failed=true; throw new Error(data.data.message || 'خطای پردازش'); }
      else if (data.event==='done') done=true;
    }
    try {
      // Create first: the id remains valid even if the model/provider fails.
      if (!conversationId) {
        var created=await jsonRequest({action:'new'}); conversationId=created.conversation_id;
      }
      var response=await fetch(streamUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken},
        body:JSON.stringify({query:query,conversation_id:conversationId,allow_external_data:!!(el('agentExternalConsent') && el('agentExternalConsent').checked)})});
      if (!response.ok) {
        var errorData=await response.json(); throw new Error(errorData.error || 'خطای ارتباط');
      }
      var reader=response.body.getReader(), decoder=new TextDecoder(), buffer='';
      try {
        while (true) {
          var part=await reader.read();
          buffer+=decoder.decode(part.value || new Uint8Array(),{stream:!part.done});
          var boundary;
          while ((boundary=buffer.indexOf('\n\n'))>=0) {
            var frame=buffer.slice(0,boundary); buffer=buffer.slice(boundary+2);
            var lines=frame.split('\n').filter(function(line){return line.indexOf('data:')===0;});
            if (lines.length) handle(JSON.parse(lines.map(function(line){return line.slice(5).trim();}).join('\n')));
          }
          if (part.done) break;
        }
      } finally { if (!done) await reader.cancel(); }
      if (!done) throw new Error('ارتباط پیش از پایان پاسخ قطع شد؛ گفتگو را بازخوانی کنید.');
      removeTyping();
      addMessage('bot',accumulated,calls,{reports:reports.slice(-1),proposals:proposals,sources:sources});
      history.push({role:'assistant',content:accumulated});
      inputEl.value='';
      await refreshConversations();
    } catch (error) {
      removeTyping(); history=prior;
      addMessage('bot','خطا: '+error.message); flagError(error.message);
      // Partial messages are never silently saved as completed answers.
      if (!failed) console.warn('AI request did not complete');
    } finally { setBusy(false); if(el('agentExternalConsent'))el('agentExternalConsent').checked=false; }
  }

  function sendMessage() {
    var query = inputEl.value.trim();
    if (!query) return;
    sendStream(query);
  }

  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  function blankConversation() {
    conversationId=null; history=[]; messagesEl.innerHTML=''; conversationSelect.value='';
    addMessage('bot','گفتگوی تازه؛ چه کمکی می‌توانم بکنم؟');
  }
  if (clearBtn) clearBtn.addEventListener('click',async function(){
    if (isBusy || !confirm('این گفتگو و نتایج ذخیره‌شدهٔ آن برای همیشه حذف شود؟')) return;
    setBusy(true);
    try { if(conversationId) await jsonRequest({action:'delete',conversation_id:conversationId}); blankConversation(); await refreshConversations(); }
    catch(error){alert(error.message);} finally{setBusy(false);}
  });
  el('newChat').addEventListener('click',function(){if(!isBusy) blankConversation();});
  el('renameChat').addEventListener('click',async function(){
    if(isBusy || !conversationId) return;
    var title=prompt('نام گفتگو:'); if(!title) return;
    setBusy(true);
    try{await jsonRequest({action:'rename',conversation_id:conversationId,title:title}); await refreshConversations();}
    catch(error){alert(error.message);} finally{setBusy(false);}
  });
  conversationSelect.addEventListener('change',async function(){
    if(!this.value){blankConversation();return;}
    setBusy(true);
    try{await refreshConversations(this.value);}catch(error){alert(error.message);}finally{setBusy(false);}
  });
  setBusy(true);
  refreshConversations().then(function(data){
    if(data.conversations && data.conversations.length) return refreshConversations(data.conversations[0].id);
  }).catch(function(error){flagError(error.message);}).finally(function(){setBusy(false);});

  if (configured) {
    inputEl.focus();
  } else {
    inputEl.placeholder = 'ابتدا مدیر سامانه سرویس هوش مصنوعی را تنظیم کند.';
  }
})();
