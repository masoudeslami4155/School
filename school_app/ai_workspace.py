"""Bounded, user-owned conversation memory and immutable query snapshots.

Stored in protected app_settings rather than client cookies or browser storage.
No school records are modified here. A role/permission fingerprint prevents a
saved snapshot surviving a reduction of the owner's privileges.
"""
from __future__ import annotations
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import g, session
from .database import get_db
from .dates import (normalize_digits, gregorian_to_jalali, jalali_to_gregorian,
                    jalali_month_days, normalize_jalali_date)

PREFIX = 'ai_workspace:'
MAX_CONVERSATIONS = 12
MAX_TURNS = 40
MAX_RESULTS = 12


def normalize_fa(value):
    text = normalize_digits(str(value or '')).translate(str.maketrans({'ي':'ی', 'ك':'ک', 'ى':'ی', '\u200c':' ', '\u200f':'', '\u200e':''}))
    text = re.sub('[\u064b-\u065f\u0670ـ]', '', text)
    return ' '.join(text.split())


def temporal_context(now=None):
    now = now or datetime.now(ZoneInfo('Asia/Tehran'))
    today = now.date()
    y, m, d = gregorian_to_jalali(today.year, today.month, today.day)
    def jalali(value):
        a,b,c = gregorian_to_jalali(value.year,value.month,value.day)
        return f'{a:04d}/{b:02d}/{c:02d}'
    saturday = today - timedelta(days=(today.weekday() + 2) % 7)
    py, pm = (y-1,12) if m == 1 else (y,m-1)
    start_year = y if m >= 7 else y-1
    return {'today': f'{y:04d}/{m:02d}/{d:02d}', 'timezone':'Asia/Tehran',
            'academic_year':f'{start_year}-{start_year+1}',
            'ranges': {'امروز':[jalali(today)]*2,
                       'دیروز':[jalali(today-timedelta(days=1))]*2,
                       'این ماه':[f'{y:04d}/{m:02d}/01', f'{y:04d}/{m:02d}/{jalali_month_days(y,m):02d}'],
                       'ماه قبل':[f'{py:04d}/{pm:02d}/01', f'{py:04d}/{pm:02d}/{jalali_month_days(py,pm):02d}'],
                       'این هفته':[jalali(saturday),jalali(saturday+timedelta(days=6))],
                       'هفته قبل':[jalali(saturday-timedelta(days=7)),jalali(saturday-timedelta(days=1))]}}


def date_range(value):
    text = normalize_fa(value).replace('هفته گذشته','هفته قبل').replace('ماه گذشته','ماه قبل')
    ctx = temporal_context()
    if text in ctx['ranges']:
        return ctx['ranges'][text]
    date = normalize_jalali_date(text, required=True)
    return [date,date]


def fingerprint():
    raw = json.dumps([session.get('role'),session.get('permissions',''),session.get('personnel_number','')], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _prefix():
    if not session.get('user_id'):
        raise ValueError('ورود به حساب لازم است.')
    return PREFIX + str(session['user_id']) + ':'


def _key(cid):
    if not re.fullmatch('[a-f0-9]{32}', str(cid or '')):
        raise ValueError('شناسهٔ گفتگو معتبر نیست.')
    return _prefix() + cid


def new_workspace():
    return {'id':uuid.uuid4().hex,'title':'گفتگوی تازه','messages':[], 'results':{}, 'working':{},
            'fingerprint':fingerprint(),'updated_at':datetime.now(ZoneInfo('Asia/Tehran')).isoformat(timespec='microseconds')}


def load(cid):
    with get_db() as conn:
        row = conn.execute('SELECT value FROM app_settings WHERE key=?',(_key(cid),)).fetchone()
    if not row:
        raise ValueError('گفتگو یافت نشد یا به حساب شما تعلق ندارد.')
    data = json.loads(row['value'])
    if data.get('fingerprint') != fingerprint():
        raise ValueError('مجوز حساب تغییر کرده؛ برای جلوگیری از نمایش دادهٔ قبلی گفتگوی تازه بسازید.')
    return data


def save(data):
    data['updated_at'] = datetime.now(ZoneInfo('Asia/Tehran')).isoformat(timespec='microseconds')
    data['messages'] = data['messages'][-MAX_TURNS:]
    data['results'] = dict(list(data['results'].items())[-MAX_RESULTS:])
    with get_db() as conn:
        conn.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     (_key(data['id']),json.dumps(data,ensure_ascii=False,default=str)))
        rows = conn.execute('SELECT key,value FROM app_settings WHERE key LIKE ?',(_prefix()+'%',)).fetchall()
        # Busy lease keys are deliberately outside this prefix.
        ordered = sorted(rows,key=lambda r:json.loads(r['value']).get('updated_at',''),reverse=True)
        for row in ordered[MAX_CONVERSATIONS:]:
            conn.execute('DELETE FROM app_settings WHERE key=?',(row['key'],))
        conn.commit()


def listing():
    with get_db() as conn:
        rows = conn.execute('SELECT value FROM app_settings WHERE key LIKE ?',(_prefix()+'%',)).fetchall()
    data = [json.loads(r['value']) for r in rows]
    return sorted([{'id':d['id'],'title':d['title'],'updated_at':d['updated_at']} for d in data
                   if d.get('fingerprint') == fingerprint()],key=lambda d:d['updated_at'],reverse=True)


def delete(cid):
    with get_db() as conn:
        conn.execute('DELETE FROM app_settings WHERE key=?',(_key(cid),))
        conn.commit()


def workspace():
    if not hasattr(g,'ai_workspace'):
        g.ai_workspace = new_workspace()
    return g.ai_workspace


def acquire(cid):
    """Cross-worker lease: one request per conversation, with crash recovery."""
    import time
    key = 'ai_workspace_busy:' + _key(cid)
    token = uuid.uuid4().hex
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT value FROM app_settings WHERE key=?',(key,)).fetchone()
        if row and json.loads(row['value'])['until'] > time.time():
            raise ValueError('این گفتگو در حال پردازش است؛ کمی صبر کنید.')
        conn.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     (key,json.dumps({'token':token,'until':time.time()+900})))
        conn.commit()
    return key,token


def release(lease):
    key,token = lease
    with get_db() as conn:
        row = conn.execute('SELECT value FROM app_settings WHERE key=?',(key,)).fetchone()
        if row and json.loads(row['value']).get('token') == token:
            conn.execute('DELETE FROM app_settings WHERE key=?',(key,))
            conn.commit()


def snapshot(name,args,payload,meta=None):
    state = workspace()
    rows = payload if isinstance(payload,list) else payload.get('rows') if isinstance(payload,dict) else None
    rid = uuid.uuid4().hex
    meta = dict(meta or {})
    if isinstance(payload,dict):
        for k in ('truncated','row_count','total','page','page_size','has_more'):
            if k in payload: meta[k] = payload[k]
    meta.setdefault('row_count',len(rows) if rows is not None else None)
    meta.setdefault('truncated',False)
    meta.update(source=name,filters=dict(args),extracted_at=datetime.now(ZoneInfo('Asia/Tehran')).isoformat(timespec='microseconds'))
    meta['coverage'] = 'صفحهٔ محدود؛ نه کل جمعیت' if meta.get('has_more') or meta.get('page',1)>1 or meta.get('truncated') else 'نتیجهٔ پرس‌وجو با فیلترهای درج‌شده'
    result = {'result_id':rid,'data':payload,'rows':rows,'meta':meta}
    state['results'][rid] = result
    state['results'] = dict(list(state['results'].items())[-MAX_RESULTS:])
    state['working'].update({'last_result_id':rid,'source':name,'filters':args,'period':{k:v for k,v in args.items() if k in {'date','date_from','date_to','year','month','period'}}})
    for key in ('class_name','grade','student_code'):
        if args.get(key): state['working'][key]=args[key]
    if rows and len(rows)==1 and isinstance(rows[0],dict):
        code=rows[0].get('student_code') or rows[0].get('code')
        if code: state['working']['student_code']=code
    return result


def get_result(rid):
    result = workspace()['results'].get(str(rid))
    if not result:
        raise ValueError('نتیجه یافت نشد یا منقضی شده؛ پرس‌وجو را دوباره اجرا کنید.')
    return result


def context_message():
    state = workspace()
    return json.dumps({'calendar':temporal_context(),'role':session.get('role'),
                       'working_memory':state['working'],
                       'saved_results':[{'result_id':r['result_id'],'meta':r['meta']} for r in list(state['results'].values())[-4:]]},ensure_ascii=False)
