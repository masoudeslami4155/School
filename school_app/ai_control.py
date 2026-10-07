"""AI connection profiles, policy, test status and metadata-only telemetry.
Secrets stay encrypted server-side. No automatic cross-provider failover.
"""
from __future__ import annotations
import copy
import json
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import session, has_request_context, g
from .database import get_db

KEY='ai_control:v1'
POLICY={'documents_remote':True,'agent_remote':False,'anonymous_documents':True,'daily_requests':1000}

def now(): return datetime.now(ZoneInfo('Asia/Tehran')).isoformat(timespec='seconds')
def read(conn):
    row=conn.execute('SELECT value FROM app_settings WHERE key=?',(KEY,)).fetchone()
    return json.loads(row['value']) if row else {'revision':0,'profiles':{},'assignments':{'documents':'','agent':''},'policy':dict(POLICY),'history':[]}
def write(conn,state):
    conn.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(KEY,json.dumps(state,ensure_ascii=False)))
def public(state):
    out=copy.deepcopy(state)
    out['history']=[{'revision':x['revision'],'at':x['at'],'actor':x.get('actor')} for x in state['history']]
    for p in out['profiles'].values():
        p['api_key_set']=bool(p.pop('api_key_encrypted',''))
        p['configured']=bool(p.get('model') and (p['provider']=='ollama' or p['api_key_set']))
    return out

def update(data):
    from .ai_documents import _normalize_base_url,_fernet,PROVIDER_LABELS,REMOTE_PROVIDERS,MODEL_PATTERN
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        state=read(conn)
        if int(data.get('revision',-1))!=state['revision']: raise ValueError('تنظیمات در پنجرهٔ دیگری تغییر کرده؛ صفحه را تازه کنید.')
        prior={k:copy.deepcopy(v) for k,v in state.items() if k!='history'}
        action=data.get('action')
        if action=='import_legacy':
            from .ai_documents import _stored_config
            old=_stored_config(conn)
            if not old.get('model'): raise ValueError('اتصال قدیمی تنظیم نشده است.')
            if len(state['profiles'])>=12:raise ValueError('حداکثر ۱۲ اتصال قابل ذخیره است.')
            pid=uuid.uuid4().hex
            state['profiles'][pid]={**old,'id':pid,'name':'اتصال قبلی','enabled':True,'temperature':0.4,'max_tokens':2400,'timeout':75,
                'input_price':0,'output_price':0,'currency':'USD','health':{'status':'untested'}}
            state['assignments']['documents']=pid
        elif action=='profile_save':
            raw=data.get('profile',{})
            if not isinstance(raw,dict):raise ValueError('مشخصات اتصال معتبر نیست.')
            pid=str(raw.get('id') or uuid.uuid4().hex)
            if len(pid)!=32 or any(c not in '0123456789abcdef' for c in pid): raise ValueError('شناسهٔ اتصال معتبر نیست.')
            old=state['profiles'].get(pid,{})
            provider=raw.get('provider')
            if provider not in PROVIDER_LABELS: raise ValueError('نوع سرویس معتبر نیست.')
            url=_normalize_base_url(raw.get('base_url',''),provider)
            model=str(raw.get('model','')).strip()
            if not MODEL_PATTERN.fullmatch(model): raise ValueError('نام مدل معتبر نیست.')
            secret=old.get('api_key_encrypted','')
            if old.get('base_url')!=url or old.get('provider')!=provider or raw.get('clear_key'): secret=''
            if raw.get('api_key'):
                if not isinstance(raw['api_key'],str):raise ValueError('کلید API باید متن باشد.')
                if len(raw['api_key'])>500: raise ValueError('کلید بیش از حد طولانی است.')
                secret=_fernet().encrypt(raw['api_key'].strip().encode()).decode()
            if provider in REMOTE_PROVIDERS and not secret and not raw.get('clear_key'): raise ValueError('برای مقصد جدید کلید همان سرویس را وارد کنید؛ کلید قبلی منتقل نمی‌شود.')
            def number(key,default,low,high,typ=float):
                try:value=typ(raw.get(key,default))
                except (TypeError,ValueError):raise ValueError('مقدار '+key+' باید عدد باشد.')
                if not low<=value<=high: raise ValueError('مقدار '+key+' خارج از محدوده است.')
                return value
            profile={'id':pid,'name':str(raw.get('name') or model)[:80],'provider':provider,'base_url':url,'model':model,
                     'api_key_encrypted':secret,'enabled':raw.get('enabled',True) is True and (provider=='ollama' or bool(secret)),
                     'temperature':number('temperature',0.4,0,1),'max_tokens':number('max_tokens',2400,256,16000,int),
                     'timeout':number('timeout',75,5,180,int),'input_price':number('input_price',0,0,1000),
                     'output_price':number('output_price',0,0,1000),'currency':str(raw.get('currency','USD'))[:12]}
            # Any edit requires a fresh test. No saved flag masquerades as health.
            profile['health']={'status':'untested'}
            if len(state['profiles'])>=12 and pid not in state['profiles']: raise ValueError('حداکثر ۱۲ اتصال قابل ذخیره است.')
            state['profiles'][pid]=profile
        elif action=='profile_delete':
            pid=data.get('id'); state['profiles'].pop(pid,None)
            for task in state['assignments']:
                if state['assignments'][task]==pid: state['assignments'][task]=''
        elif action=='policy_save':
            raw=data.get('policy',{})
            if not isinstance(raw,dict):raise ValueError('سیاست معتبر نیست.')
            state['policy']={k:raw.get(k,POLICY[k]) is True for k in ('documents_remote','agent_remote','anonymous_documents')}
            limit=int(raw.get('daily_requests',1000))
            if not 1<=limit<=10000: raise ValueError('سقف روزانه باید بین ۱ تا ۱۰٬۰۰۰ باشد.')
            state['policy']['daily_requests']=limit
            assignments=data.get('assignments',{})
            if not isinstance(assignments,dict):raise ValueError('انتخاب کاربردها معتبر نیست.')
            for task in ('documents','agent'):
                pid=str(assignments.get(task,''))
                if pid and (pid not in state['profiles'] or not state['profiles'][pid]['enabled']): raise ValueError('اتصال منتخب موجود یا فعال نیست.')
                state['assignments'][task]=pid
        elif action=='rollback':
            entry=next((x for x in state['history'] if x['revision']==int(data.get('target',-1))),None)
            if not entry: raise ValueError('نسخهٔ تنظیمات یافت نشد.')
            for k in ('profiles','assignments','policy'): state[k]=copy.deepcopy(entry['state'][k])
        else: raise ValueError('عملیات معتبر نیست.')
        state['history'].append({'revision':prior['revision'],'at':now(),'actor':session.get('user_id'),'state':prior})
        state['history']=state['history'][-20:];state['revision']+=1
        write(conn,state)
    return public(state)

def private(profile):
    from .ai_documents import _fernet,AIProviderError,PROVIDER_LABELS
    from cryptography.fernet import InvalidToken
    out=dict(profile); encrypted=out.pop('api_key_encrypted','')
    try: out['api_key']=_fernet().decrypt(encrypted.encode()).decode() if encrypted and out['provider']!='ollama' else ''
    except (InvalidToken,ValueError): raise AIProviderError('کلید این اتصال با کلید رمزگذاری فعلی باز نمی‌شود؛ مدیر باید کلید API را دوباره وارد کند.') from None
    out.update(configured=bool(out.get('model') and (out['provider']=='ollama' or out['api_key'])),profile_id=out['id'],provider_label=PROVIDER_LABELS[out['provider']],api_key_set=bool(encrypted))
    return out

def resolve(conn,user_id,task,include_key=True):
    state=read(conn)
    row=conn.execute('SELECT value FROM app_settings WHERE key=?',(f'ai_control:user:{user_id}',)).fetchone()
    selection=json.loads(row['value']) if row else {}
    if selection.get(task)=='__legacy__':return None
    if task not in selection:
        # Preserve an existing user's explicitly pinned local model during upgrade.
        from .ai_documents import load_provider_selection,MODEL_PATTERN
        previous=load_provider_selection(conn,user_id)
        if previous.get('provider')=='ollama' and MODEL_PATTERN.fullmatch(previous.get('model','')):return None
    pid=selection.get(task) or state['assignments'].get(task)
    if not pid: return None
    profile=state['profiles'].get(pid)
    if not profile or not profile['enabled']:
        return {'id':pid,'provider':'ollama','provider_label':'اتصال منتخب حذف یا غیرفعال شده؛ دوباره انتخاب کنید','base_url':'','model':'','configured':False,'api_key':'','api_key_set':False}
    if include_key: out=private(profile)
    else:
        out=public({'profiles':{pid:profile},'history':[]})['profiles'][pid]
        from .ai_documents import PROVIDER_LABELS
        out['provider_label']=PROVIDER_LABELS[out['provider']]
    out['use_case']=task
    out['selection_source']='user' if selection.get(task) else 'default'
    return out

def select(conn,user_id,task,pid):
    if task not in ('agent','documents'): raise ValueError('کاربرد معتبر نیست.')
    state=read(conn)
    if pid and pid!='__legacy__' and (pid not in state['profiles'] or not state['profiles'][pid]['enabled']): raise ValueError('اتصال در دسترس نیست.')
    key=f'ai_control:user:{user_id}'
    row=conn.execute('SELECT value FROM app_settings WHERE key=?',(key,)).fetchone()
    choices=json.loads(row['value']) if row else {};choices[task]=pid
    conn.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(choices)))

def allowed(config,task,consent=False):
    if config.get('provider')=='ollama': return
    with get_db() as conn: policy=read(conn)['policy']
    if not policy.get(task+'_remote',False): raise ValueError('ارسال اینترنتی برای این کاربرد توسط مدیر غیرفعال است.')
    if consent is not True: raise ValueError('قبل از ارسال اینترنتی، اجازهٔ ارسال همین درخواست را تأیید کنید.')

def telemetry_start(config):
    day=now()[:10];key='ai_control:usage:'+day
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT value FROM app_settings WHERE key=?',(key,)).fetchone()
        entries=json.loads(row['value']) if row else []
        if len(entries)>=read(conn)['policy']['daily_requests']:
            from .ai_documents import AIProviderError
            raise AIProviderError('سقف درخواست روزانهٔ هوش مصنوعی پر شده است.')
        ident=uuid.uuid4().hex
        entries.append({'id':ident,'at':now(),'profile':config.get('profile_id','legacy'),'model':config.get('model'),
                        'user':session.get('user_id') if has_request_context() else None,'task':config.get('use_case','documents'),'status':'started'})
        conn.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(entries)))
        old=conn.execute("SELECT key FROM app_settings WHERE key LIKE 'ai_control:usage:%' ORDER BY key DESC").fetchall()
        for r in old[30:]: conn.execute('DELETE FROM app_settings WHERE key=?',(r['key'],))
    return key,ident,time.monotonic()

def telemetry_end(handle,config,status,usage=None):
    if not handle:return
    key,ident,start=handle;usage=usage if isinstance(usage,dict) else {}
    usage={k:v for k,v in usage.items() if k in ('prompt_tokens','completion_tokens') and isinstance(v,int) and 0<=v<=100000000}
    with get_db() as conn:
        row=conn.execute('SELECT value FROM app_settings WHERE key=?',(key,)).fetchone()
        if not row:return
        entries=json.loads(row['value'])
        for entry in entries:
            if entry['id']==ident:
                entry.update(status=status,seconds=round(time.monotonic()-start,3),prompt_tokens=usage.get('prompt_tokens'),completion_tokens=usage.get('completion_tokens'))
                if isinstance(usage.get('prompt_tokens'),int) and isinstance(usage.get('completion_tokens'),int) and (config.get('input_price') or config.get('output_price')):
                    entry['estimated_cost']=(usage['prompt_tokens']*config.get('input_price',0)+usage['completion_tokens']*config.get('output_price',0))/1000000
                    entry['currency']=config.get('currency','USD')
        conn.execute('UPDATE app_settings SET value=? WHERE key=?',(json.dumps(entries),key))

def usage(conn):
    rows=conn.execute("SELECT value FROM app_settings WHERE key LIKE 'ai_control:usage:%' ORDER BY key DESC LIMIT 30").fetchall()
    entries=[e for r in rows for e in json.loads(r['value'])]
    return {'requests':len(entries),'errors':sum(e['status'] not in ('ok','started') for e in entries),
            'recent':sorted(entries,key=lambda e:e['at'],reverse=True)[:100]}

def test_profile(data):
    from .ai_documents import request_chat_message,AIProviderError
    with get_db() as conn:
        state=read(conn); profile=state['profiles'].get(data.get('id'))
    # Probe an unsaved draft without persisting its key.
    if data.get('draft'):
        draft=data['draft']
        if not isinstance(draft,dict):raise ValueError('مشخصات آزمایش معتبر نیست.')
        from .ai_documents import _normalize_base_url,REMOTE_PROVIDERS,MODEL_PATTERN
        provider=draft.get('provider')
        if provider not in ('ollama','gemini','openai-compatible'): raise ValueError('نوع اتصال معتبر نیست.')
        url=_normalize_base_url(draft.get('base_url',''),provider)
        if not MODEL_PATTERN.fullmatch(str(draft.get('model',''))): raise ValueError('نام مدل معتبر نیست.')
        key=str(draft.get('api_key','')).strip()
        if not key and profile and profile['base_url']==url and profile['provider']==provider: key=private(profile)['api_key']
        if provider in REMOTE_PROVIDERS and not key: raise ValueError('کلید مقصد را وارد کنید.')
        config={'provider':provider,'base_url':url,'model':draft['model'],'api_key':key,'configured':True,'timeout':30}
    elif profile: config=private(profile)
    else: raise ValueError('اتصال یافت نشد.')
    if not config.get('configured'):raise ValueError('کلید یا مدل اتصال کامل نیست.')
    config.update(_test=True,use_case='connection_test',max_tokens=256,temperature=0)
    started=time.monotonic();result={'at':now(),'status':'failed','text':False,'json':False,'tools':False}
    try:
        msg=request_chat_message(config,[{'role':'user','content':'Reply with the word OK. Synthetic connection test; no school data.'}])
        result['text']=bool(msg.get('content'))
        msg=request_chat_message(config,[{'role':'user','content':'Return ONLY JSON: {"ok":true}'}])
        try: result['json']=json.loads(msg.get('content') or '{}').get('ok') is True
        except (ValueError,AttributeError): pass
        tool={'type':'function','function':{'name':'test_connection','description':'Call this function now to complete the synthetic test.','parameters':{'type':'object','properties':{},'required':[]}}}
        msg=request_chat_message(config,[{'role':'user','content':'Call test_connection now. Do not answer with text.'}],tools=[tool])
        result['tools']=any(c.get('function',{}).get('name')=='test_connection' for c in msg.get('tool_calls',[]) if isinstance(c,dict) and isinstance(c.get('function'),dict))
        result['status']='ok' if result['text'] else 'failed'
    except AIProviderError as exc: result['error']=str(exc)
    result['seconds']=round(time.monotonic()-started,2)
    if profile and not data.get('draft'):
        with get_db() as conn:
            conn.execute('BEGIN IMMEDIATE');fresh=read(conn)
            if fresh['profiles'].get(profile['id'])==profile:
                fresh['profiles'][profile['id']]['health']=result;write(conn,fresh)
    return result
