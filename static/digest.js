/* End-of-day digest scheduler — runs on every page */
(function(){
  function get(k){try{return localStorage.getItem(k)}catch(e){return null}}
  function set(k,v){try{localStorage.setItem(k,v)}catch(e){}}
  function fa(n){return String(n).replace(/\d/g,function(d){return '۰۱۲۳۴۵۶۷۸۹'[+d]})}
  function todayKey(){var d=new Date();return d.getFullYear()+'-'+(d.getMonth()+1)+'-'+d.getDate()}
  function nowHM(){var n=new Date();return String(n.getHours()).padStart(2,'0')+':'+String(n.getMinutes()).padStart(2,'0')}
  function esc(s){var d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML}
  function esc2(s){return esc(s)}
  function sec(title,rows,fmt,empty){
    var h='<h3 style="margin:14px 0 8px;font-size:13.5px;border-bottom:2px solid var(--line);padding-bottom:6px;color:var(--ink)">'+title+'</h3><ul style="list-style:none;margin:0;padding:0;display:grid;gap:5px">';
    if(!(rows||[]).length){h+='<li style="color:var(--muted);font-size:12px">'+empty+'</li>'}
    else rows.forEach(function(x){
      h+='<li style="font-size:12.5px;background:var(--soft);border-right:3px solid '+(x._danger?'#b42318':'var(--primary)')+';border-radius:0 6px 6px 0;padding:6px 10px;color:var(--ink);list-style:none;display:flex;justify-content:space-between;gap:8px"><span>'+esc(x._main)+'</span><small style="color:var(--muted)">'+esc(x._meta||'')+'</small></li>';
    });
    return h+'</ul>';
  }
  function show(d){
    var ov=document.createElement('div');ov.id='digestLayer';
    ov.style.cssText='position:fixed;inset:0;z-index:120;background:rgba(10,16,26,.55);display:flex;align-items:center;justify-content:center;padding:16px';
    var box=document.createElement('div');
    box.style.cssText='background:var(--surface);color:var(--ink);border:1px solid var(--line);border-radius:16px;max-width:640px;width:100%;max-height:84vh;overflow:auto;padding:20px;font-size:13px';
    var total=(d.events_today||[]).length+(d.tasks_today||[]).length;
    var over=(d.events_overdue||[]).length+(d.tasks_overdue||[]).length;
    var h='<h2 style="margin:0 0 4px;font-size:17px;color:var(--ink)">🌇 گزارش پایان روز · '+esc(d.date)+'</h2>';
    h+='<p style="margin:0 0 12px;color:var(--muted);font-size:12px">'+fa(total)+' مورد امروز · '+fa(over)+' عقب‌افتاده</p>';
    (d.events_today||[]).forEach(function(x){x._meta=(x.type||'سایر')+' · '+(x.priority||'عادی');x._danger=false});
    (d.tasks_today||[]).forEach(function(x){x._meta=(x.category||'کار')+' · '+(x.priority||'عادی')});
    (d.events_overdue||[]).forEach(function(x){x._meta='رویداد · '+x.date;x._danger=true});
    (d.tasks_overdue||[]).forEach(function(x){x._meta='کار · '+x.due_date;x._danger=true});
    h+=sec('📌 رویدادهای امروز',d.events_today,null,'رویدادی برای امروز نیست.')
      +sec('✅ کارهای امروز (باز)',d.tasks_today,function(x){return '<b>'+(x.due_time||'بدون ساعت')+'</b> · '+x.title},'کار بازی نیست.')
      +sec('✔️ امروز انجام شد',d.tasks_done_today,function(x){return x.title},'امروز کاری تکمیل نشده.')
      +sec('⚠️ عقب‌افتاده',d.events_overdue.concat(d.tasks_overdue||[]).length?d.events_overdue.concat(d.tasks_overdue):[],function(x){return (x.date||x.due_date)+' · '+x.title},'مورد عقب‌افتاده‌ای نیست. 🎉')
      +sec('⏭️ فردا: رویداد + کار',(d.events_tomorrow||[]).concat((d.tasks_tomorrow||[]).map(function(x){x._meta=(x.category||'کار')+' · '+(x.priority||'عادی');return x})),function(x){return '<b>'+(x.time||x.due_time||'بدون ساعت')+'</b> · '+x.title},'برای فردا موردی نیست.');
    h+='<div style="display:flex;gap:8px;margin-top:16px"><button id="digestPrint" style="flex:1;padding:10px;border:none;border-radius:8px;background:var(--primary);color:#fff;font-family:inherit;font-weight:700;cursor:pointer">🖨️ چاپ گزارش کامل</button><button id="digestClose" style="padding:10px 16px;border:1px solid var(--line);border-radius:8px;background:var(--soft);color:var(--ink);cursor:pointer;font-family:inherit">بستن</button></div>';
    box.innerHTML=h;ov.appendChild(box);document.body.appendChild(ov);
    box.querySelector('#digestPrint').addEventListener('click',function(){window.open('/daily_digest','_blank')});
    box.querySelector('#digestClose').addEventListener('click',function(){ov.remove()});
    ov.addEventListener('click',function(e){if(e.target===ov)ov.remove()});
  }
  function tick(){
    if(get('digest-enabled')!=='1')return;
    if(sessionStorage.getItem('digest-unavailable'))return;
    if(get('digest-shown')===todayKey())return;
    if(nowHM()<(get('digest-time')||'17:30'))return;
    fetch('/daily_digest?format=json',{credentials:'same-origin'})
      .then(function(r){if(!r.ok)throw 0;return r.json()})
      .then(function(d){
        set('digest-shown',todayKey());
        show(d);
        if(window.Notification&&Notification.permission==='granted'){
          try{new Notification('گزارش پایان روز آماده است',{body:fa((d.events_today||[]).length)+' رویداد و '+fa((d.tasks_today||[]).length)+' کار برای امروز'})}catch(e){}
        }
      })
      .catch(function(){try{sessionStorage.setItem('digest-unavailable','1')}catch(e){}});
  }
  setInterval(tick,30000);
  tick();
})();
