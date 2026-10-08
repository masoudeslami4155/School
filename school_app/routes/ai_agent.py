from __future__ import annotations

from flask import (
    abort, current_app, jsonify, render_template,
    request, Response, session, stream_with_context, g, send_file,
)

from ..ai_agent import (
    AIProviderError,
    apply_pending_change,
    chat_text,
    collect_artifacts,
    run_agent,
    stream_agent_event, iter_agent_events, execute_tool,
)
from ..ai_documents import effective_public_provider_config
from ..database import get_db
from ..security import audit
from .. import ai_workspace as memory
from ..ai_results import result_rows
import json
import io
import sqlite3


def ai_agent_page():
    if session.get('role') not in {'admin', 'manager'}:
        abort(403)
    # Show the saved provider the assistant will actually use, rather than a
    # hardcoded "online" label that hid an unconfigured installation.
    with get_db() as conn:
        provider = effective_public_provider_config(conn, session.get('user_id'), 'agent')
    from .. import ai_control as control
    with get_db() as conn: connections=control.public(control.read(conn))['profiles']
    return render_template('ai_agent.html', provider=provider,connections=connections)


def _access():
    # Teacher enablement is intentionally deferred with the permission redesign.
    if session.get('role') not in {'admin', 'manager'}:
        abort(403)


def _prepare(data):
    g.ai_external_consent=data.get('allow_external_data') is True
    query=str(data.get('query') or '').strip()
    if not query: raise ValueError('پیام خالی است.')
    if len(query)>2000: raise ValueError('پیام بیش از ۲۰۰۰ نویسه است.')
    cid=data.get('conversation_id')
    state=memory.load(cid) if cid else memory.new_workspace()
    lease=memory.acquire(state['id'])
    try:
        # Re-read after acquiring the lease to avoid using a stale history.
        if cid: state=memory.load(cid)
        g.ai_workspace=state
        history=state['messages'] if cid else data.get('history',[])
        if not state['messages']: state['title']=query[:70]
        return query,history,state,lease
    except Exception:
        memory.release(lease)
        raise


def _finish(state,query,answer,reports,sources):
    sources=list({s['result_id']:s for s in sources}.values())
    state['messages'].extend([{'role':'user','content':query},
        {'role':'assistant','content':answer,'reports':reports[-1:],'sources':sources}])
    memory.save(state)


def _export(data):
    state=memory.load(data.get('conversation_id'))
    g.ai_workspace=state
    result=memory.get_result(data.get('result_id'))
    rows=result_rows(result)
    meta=dict(result['meta'])
    if data.get('all'):
        source=meta['source']
        if source not in {'search_students','get_attendance','get_service_fees'}:
            raise ValueError('خروجی کامل منبع فقط برای جستجو، حضور و مالی آماده است؛ این نتیجه را جدا صادر کنید.')
        rows=[]
        # execute_tool opens independent connections: detect concurrent changes
        # rather than silently presenting a mixed export as a stable snapshot.
        from ..database import get_db
        with get_db() as watcher:
            before=watcher.execute('PRAGMA data_version').fetchone()[0]
            for page in range(1,51):
                args=dict(meta['filters'],page=page,page_size=200)
                response=execute_tool(source,args,session.get('role'))
                rows.extend(json.loads(response['content']))
                if not response['meta']['has_more']: break
            else:
                raise ValueError('خروجی بیش از ۱۰٬۰۰۰ ردیف است؛ فیلتر محدودتری انتخاب کنید.')
            if watcher.execute('PRAGMA data_version').fetchone()[0] != before:
                raise ValueError('داده هنگام استخراج تغییر کرد؛ خروجی را دوباره بگیرید.')
        from datetime import datetime
        from zoneinfo import ZoneInfo
        meta['original_extracted_at']=meta.get('extracted_at')
        meta['extracted_at']=datetime.now(ZoneInfo('Asia/Tehran')).isoformat(timespec='seconds')
        meta.update(page=1,has_more=False,truncated=False,coverage='استخراج مجدد همهٔ رکوردهای منطبق با فیلتر؛ نه تصویر ذخیره‌شدهٔ قدیمی',row_count=len(rows))
    from openpyxl import Workbook
    from datetime import datetime
    wb=Workbook(); sheet=wb.active; sheet.title='داده‌ها'; sheet.sheet_view.rightToLeft=True
    columns=list(rows[0]) if rows else []
    sheet.append(columns)
    for row in rows:
        sheet.append([row.get(c) if isinstance(row.get(c),(int,float,bool)) else str(row.get(c) if row.get(c) is not None else '') for c in columns])
    # Untrusted names and cells must never become spreadsheet formulas.
    for row in sheet:
        for cell in row:
            if isinstance(cell.value,str): cell.data_type='s'
    info=wb.create_sheet('مشخصات'); info.sheet_view.rightToLeft=True
    info.append(['شناسه نتیجه',result['result_id']])
    info.append(['زمان ساخت فایل',datetime.now().isoformat(timespec='seconds')])
    for key,value in meta.items(): info.append([key,json.dumps(value,ensure_ascii=False)])
    output=io.BytesIO(); wb.save(output); output.seek(0)
    return send_file(output,as_attachment=True,download_name='agent-result.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def ai_agent_chat():
    _access()
    try:
        if request.method=='GET':
            cid=request.args.get('conversation_id')
            return jsonify({'ok':True,'conversations':memory.listing(),
                            'conversation':memory.load(cid) if cid else None})
        data=request.get_json(silent=True) or {}
        if not isinstance(data,dict): raise ValueError('درخواست معتبر نیست.')
        action=data.get('action','chat')
        if action=='profile':
            from .. import ai_control as control
            with get_db() as conn:control.select(conn,session['user_id'],'agent',str(data.get('profile_id') or ''))
            return jsonify({'ok':True})
        if action=='export': return _export(data)
        if action in {'new','delete','rename'}:
            if action=='new':
                state=memory.new_workspace(); memory.save(state)
            else:
                state=memory.load(data.get('conversation_id'))
                lease=memory.acquire(state['id'])
                try:
                    if action=='delete': memory.delete(state['id'])
                    else:
                        state['title']=str(data.get('title') or '').strip()[:70] or 'گفتگو'
                        memory.save(state)
                finally: memory.release(lease)
            return jsonify({'ok':True,'conversation_id':state['id'] if action!='delete' else None})
        if action!='chat': raise ValueError('عملیات معتبر نیست.')
        query,history,state,lease=_prepare(data)
        try:
            before=set(state['results'])
            msgs_out,answer,tool_calls=run_agent(query,history)
            artifacts=collect_artifacts(msgs_out)
            used=set(state['results'])-before
            for msg in msgs_out:
                if msg.get('role')=='tool':
                    try:
                        parsed=json.loads(msg.get('content',''))
                        if isinstance(parsed,dict) and parsed.get('result_id'): used.add(parsed['result_id'])
                    except (ValueError,TypeError): pass
                for call in msg.get('tool_calls',[]):
                    try:
                        arguments=json.loads(call.get('function',{}).get('arguments','{}'))
                        if isinstance(arguments,dict) and arguments.get('result_id'): used.add(arguments['result_id'])
                    except (ValueError,TypeError): pass
            sources=[{'result_id':r['result_id'],'meta':r['meta']} for rid,r in state['results'].items() if rid in used]
            _finish(state,query,answer,artifacts['reports'],sources)
            audit(session.get('user_id'),'ai_agent_chat','ai_agent',f'query_len:{len(query)};tools:{len(tool_calls)}')
            return jsonify({'ok':True,'answer':answer,'tool_calls':tool_calls,'messages':msgs_out,
                            'conversation_id':state['id'],'reports':artifacts['reports'],
                            'sources':sources,'pending_changes':artifacts['proposals']})
        finally: memory.release(lease)
    except ValueError as exc:
        return jsonify({'ok':False,'error':str(exc)}),400
    except AIProviderError as exc:
        return jsonify({'ok':False,'error':str(exc)}),502


def ai_agent_stream():
    _access()
    # Legacy GET retained for integrations; the UI sends no message in URLs.
    if request.method=='POST': data=request.get_json(silent=True) or {}
    else:
        try: history=json.loads(request.args.get('h','[]'))
        except (ValueError,TypeError): history=[]
        data={'query':request.args.get('q',''),'history':history}
    if not isinstance(data,dict):
        return jsonify({'ok':False,'error':'درخواست معتبر نیست.'}),400
    try: query,history,state,lease=_prepare(data)
    except ValueError as exc: return jsonify({'ok':False,'error':str(exc)}),400
    def event(kind,payload=None):
        return 'data: '+json.dumps({'event':kind,'data':payload},ensure_ascii=False)+'\n\n'
    def generate():
        answer=''; reports=[]; sources=[]; count=0
        try:
            yield event('start')
            yield event('conversation',{'id':state['id']})
            for ev in iter_agent_events(query,history):
                count+=1
                kind=ev['event']; payload=ev['data']
                if kind=='token': answer+=payload
                elif kind=='report': reports.append(payload)
                elif kind=='source': sources.append(payload)
                elif kind=='error':
                    yield event(kind,payload)
                    return
                yield event(kind,payload)
            _finish(state,query,answer,reports,sources)
            audit(session.get('user_id'),'ai_agent_stream','ai_agent',f'query_len:{len(query)};events:{count}')
            yield event('done')
        except (ValueError,AIProviderError) as exc:
            yield event('error',{'message':str(exc)})
        except Exception:
            current_app.logger.exception('AI stream failed')
            yield event('error',{'message':'خطای داخلی در پردازش؛ دوباره تلاش کنید.'})
        finally: memory.release(lease)
    response=Response(stream_with_context(generate()),mimetype='text/event-stream',
                      headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
    response.call_on_close(lambda: None)
    return response


def ai_agent_apply_change():
    """Run a database change the user explicitly approved in the chat.

    The assistant can only *propose* a change; nothing is written until the user
    presses the confirmation button, and only the proposal stored in that user's
    own session can be applied.
    """
    _access()
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'ok': False, 'error': 'درخواست معتبر نیست.'}), 400
    change_id = str(data.get('change_id') or '')
    try:
        result = apply_pending_change(change_id)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    except sqlite3.IntegrityError:
        current_app.logger.exception('AI change violated a database constraint')
        return jsonify({'ok': False, 'error': 'تغییر ثبت نشد: مقدار تکراری، فیلد الزامی یا ارتباط رکوردها معتبر نیست. پیشنهاد باید اصلاح شود.'}), 409
    except sqlite3.Error:
        current_app.logger.exception('AI database change failed')
        return jsonify({'ok': False, 'error': 'تغییر ثبت نشد؛ اجرای دستور پایگاه داده ناموفق بود. جزئیات در گزارش خطای برنامه ثبت شد.'}), 400
    audit(
        session.get('user_id'), 'ai_agent_apply_change', 'ai_agent', 'database_change',
        f"affected:{result['affected']};sql_len:{len(result['sql'])}",
    )
    return jsonify({'ok': True, 'result': result})


def register(app):
    app.add_url_rule('/ai-agent', 'ai_agent', ai_agent_page, methods=['GET'])
    app.add_url_rule('/ai-agent/chat', 'ai_agent_chat', ai_agent_chat, methods=['GET','POST'])
    app.add_url_rule('/ai-agent/stream', 'ai_agent_stream', ai_agent_stream, methods=['GET','POST'])
    app.add_url_rule(
        '/ai-agent/apply-change', 'ai_agent_apply_change',
        ai_agent_apply_change, methods=['POST'],
    )
