from __future__ import annotations

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for, send_file

from ..ai_documents import (
    AIProviderError,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_URL,
    DEFAULT_OLLAMA_URL,
    DOCUMENT_TYPES,
    MAX_STUDENTS,
    effective_private_provider_config,
    effective_public_provider_config,
    generate_document,
    generate_letter_document,
    is_remote_provider,
    list_ollama_models,
    load_provider_selection,
    local_ollama_url,
    ollama_status,
    provider_choices,
    public_provider_config,
    save_provider_config,
    save_provider_selection,
)
from ..ai_letter_layout import (
    default_layout as default_letter_layout,
    list_templates as list_letter_templates,
    load_layout as load_letter_layout,
    load_template as load_letter_template,
)
from ..database import auto_backup, get_db
from ..dates import get_today_jalali, month_order_sql, today_string
from ..security import audit, current_session_endpoints
from .. import ai_control as control
from .. import ai_document_store as archive
from ..ai_workspace import temporal_context
import json
import html


_PAPER_SIZES = {'a4-portrait', 'a4-landscape', 'a5', 'card'}
_PERSIAN_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')

# نمونهٔ نمایشی پیش‌نمایش چاپ نامه؛ همان مقادیر نمونهٔ استودیو.
_LETTER_SAMPLE = {
    'today': '۱۴۰۵/۰۷/۱۱',
    'school_name': 'مدرسهٔ نمونه',
    'subject': 'تذکر حضور و انضباط دانش‌آموز',
    'body': 'با سلام و احترام؛ بدینوسیله به استحضار می‌رساند که دانش‌آموز یادشده در جلسات اخیر از حضور و انضباط کلاس کمتری نشان داده است. خواهشمند است با فرزند خود در این باره صحبت کنید و راهنمایی لازم را انجام دهید.',
    'student_name': 'زهرا آزمونی',
    'grade': 'پایه سوم',
    'class_name': 'کلاس ۲',
}


def _letter_page_size(paper: str, layout: dict) -> tuple[float, float, str]:
    """Return ``(width, height, effective_paper)`` in millimetres.

    For A4 papers the orientation saved in the letter studio decides
    the final page, so what the user designed is what they print.
    """
    if paper == 'a5':
        return 148.0, 210.0, 'a5'
    if paper == 'card':
        return 90.0, 50.0, 'card'
    landscape = layout.get('orientation') == 'landscape'
    if landscape:
        return 297.0, 210.0, 'a4-landscape'
    return 210.0, 297.0, 'a4-portrait'


def _selected_ids(raw) -> list[int]:
    if not isinstance(raw, list):
        raise ValueError('یک یا چند دانش‌آموز را انتخاب کنید.')
    ids = []
    for value in raw:
        try:
            student_id = int(value)
        except (TypeError, ValueError):
            continue
        if student_id > 0 and student_id not in ids:
            ids.append(student_id)
    if not ids:
        raise ValueError('یک یا چند دانش‌آموز را انتخاب کنید.')
    if len(ids) > MAX_STUDENTS:
        raise ValueError(f'در هر نوبت حداکثر {MAX_STUDENTS} دانش‌آموز انتخاب کنید.')
    return ids


def _money(value) -> str:
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f'{amount:,} تومان'.translate(_PERSIAN_DIGITS)


def _load_records(conn, student_ids: list[int], document_type: str, service_id=None) -> list[dict[str, str]]:
    include_parent = document_type in {'letter', 'invitation'}
    columns = ['id', 'first_name', 'last_name', 'grade', 'class_name']
    if include_parent:
        columns.append('father_name')
    placeholders = ','.join('?' for _ in student_ids)
    rows = conn.execute(
        f"SELECT {','.join(columns)} FROM students WHERE id IN ({placeholders}) "
        "AND (status='فعال' OR status IS NULL OR TRIM(status)='')",
        student_ids,
    ).fetchall()
    by_id = {row['id']: row for row in rows}
    if len(by_id) != len(student_ids):
        invalid=[]
        for ident in student_ids:
            if ident not in by_id:
                student=conn.execute('SELECT first_name,last_name FROM students WHERE id=?',(ident,)).fetchone()
                name=' '.join(str(student[k] or '') for k in ('first_name','last_name')).strip() if student else ''
                invalid.append(name or ('شناسه '+str(ident)))
        raise ValueError('این دانش‌آموزان فعال نیستند یا وجود ندارند: '+'، '.join(invalid)+'؛ هیچ سندی از این گروه ذخیره نشد. فهرست را تازه کنید.')

    year, _month, _day = get_today_jalali()
    academic_year = temporal_context()['academic_year'].translate(_PERSIAN_DIGITS)
    today = temporal_context()['today'].translate(_PERSIAN_DIGITS)
    records = []
    for student_id in student_ids:
        row = by_id[student_id]
        full_name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
        record = {
            'student_name': full_name,
            'grade': str(row['grade'] or ''),
            'class_name': str(row['class_name'] or ''),
            'school_name': str(current_app.config.get('SCHOOL_NAME') or ''),
            'academic_year': academic_year,
            'today': today,
        }
        if include_parent:
            record['parent_name'] = str(row['father_name'] or '')
        if document_type == 'receipt':
            service = conn.execute(
                f'''SELECT id, year, month, service_type, amount, paid_amount, status, payment_date
                   FROM monthly_service
                   WHERE student_code=(SELECT code FROM students WHERE id=?)
                     AND CAST(COALESCE(amount,0) AS INTEGER)>0 AND (? IS NULL OR id=?)
                   ORDER BY CAST(COALESCE(year,0) AS INTEGER) DESC,
                     {month_order_sql('month')} DESC, id DESC LIMIT 1''',
                (student_id,service_id,service_id),
            ).fetchone()
            if not service:
                raise ValueError(f'برای «{full_name}» سابقهٔ مبلغ سرویس ثبت‌شده پیدا نشد؛ رسید قابل تولید نیست.')
            amount = max(0, int(service['amount'] or 0))
            paid = max(0, int(service['paid_amount'] or 0))
            record.update({
                '_service_id':service['id'],
                '_financial_snapshot':[service['amount'],service['paid_amount'],service['payment_date']],
                'service_reference':str(service['id']),
                'payment_date':str(service['payment_date'] or 'ثبت نشده'),
                'service_year': str(service['year'] or '').translate(_PERSIAN_DIGITS),
                'service_month': str(service['month'] or ''),
                'amount_due': _money(amount),
                'amount_paid': _money(paid),
                'remaining': _money(max(0, amount - paid)),
                'payment_status': str(service['status'] or ''),
                'service_type': str(service['service_type'] or ''),
            })
        records.append(record)
    return records


def ai_documents():
    if session.get('role') not in {'admin', 'manager'}:
        abort(403)
    if request.method=='POST' or request.args.get('api')=='1':
        return document_api()
    with get_db() as conn:
        students = conn.execute(
            '''SELECT id, first_name, last_name, grade, class_name
               FROM students WHERE status='فعال' OR status IS NULL OR TRIM(status)=''
               ORDER BY first_name COLLATE NOCASE, last_name COLLATE NOCASE, id'''
        ).fetchall()
        user_id = session.get('user_id')
        provider = effective_public_provider_config(conn, user_id)
        choices = provider_choices(conn)
        selection = load_provider_selection(conn, user_id)
        letter_templates = list_letter_templates(conn, user_id)
        connections=control.public(control.read(conn))['profiles']
        if provider['provider'] not in {c['key'] for c in choices}:
            choices.append({'key':provider['provider'],'label':provider['provider_label'],'remote':True,'model':provider['model'],'ready':provider['configured']})
    return render_template(
        'ai_documents.html',
        students=students,
        document_types=DOCUMENT_TYPES,
        provider=provider,
        provider_choices=choices,
        selection=selection,
        remote=is_remote_provider(provider['provider']),
        letter_templates=letter_templates, connections=connections,
    )


def _compose_brief(data,kind):
    from ..ai_workspace import date_range
    from ..dates import normalize_digits
    import re
    brief=str(data.get('brief') or '').strip()
    if not brief:raise ValueError('متن یا شرح سند را وارد کنید.')
    parts=[brief]
    if kind=='invitation':
        missing=[label for key,label in (('event_date','تاریخ'),('event_time','ساعت'),('event_place','محل')) if not str(data.get(key) or '').strip()]
        if missing:raise ValueError('برای دعوت‌نامه این موارد را مشخص کنید: '+'، '.join(missing))
        start,end=date_range(str(data['event_date']))
        if start!=end:raise ValueError('برای دعوت‌نامه یک روز مشخص انتخاب کنید.')
        clock=normalize_digits(str(data['event_time']))
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',clock):raise ValueError('ساعت دعوت معتبر نیست؛ قالب ۱۰:۳۰ لازم است.')
        parts.extend(['تاریخ: '+start,'ساعت: '+clock,'محل: '+str(data['event_place'])[:500]])
    for key,label in (('subject','موضوع'),('recipient','مخاطب'),('attachments','پیوست')):
        if data.get(key):parts.append(label+': '+str(data[key])[:500])
    result='\n'.join(parts)
    if len(result)>3000:raise ValueError('مجموع شرح و جزئیات سند باید حداکثر ۳۰۰۰ نویسه باشد.')
    return result


def ai_documents_generate():
    if session.get('role') not in {'admin', 'manager'}:
        abort(403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    document_type = str(data.get('document_type') or '')
    brief = str(data.get('brief') or '').strip()
    paper = str(data.get('paper') or 'a4-portrait')
    try:
        student_ids = _selected_ids(data.get('student_ids'))
        if document_type not in DOCUMENT_TYPES:
            raise ValueError('نوع سند را انتخاب کنید.')
        if document_type == 'receipt' and 'monthly_service' not in current_session_endpoints():abort(403)
        if document_type == 'receipt' and not data.get('service_id'):
            raise ValueError('سابقهٔ مالی دقیق رسید را انتخاب کنید؛ آخرین سابقه به‌طور خودکار انتخاب نمی‌شود.')
        if document_type == 'receipt' and len(student_ids) != 1:
            raise ValueError('برای جلوگیری از اشتباه مالی، رسید را برای هر بار فقط به نام یک دانش‌آموز بسازید.')
        if not brief or len(brief) > 3000:
            raise ValueError('شرح طرح را وارد کنید (حداکثر ۳۰۰۰ نویسه).')
        if paper not in _PAPER_SIZES:
            raise ValueError('اندازهٔ کاغذ معتبر نیست.')
        with get_db() as conn:
            provider = effective_private_provider_config(conn, session.get('user_id'))
            if not provider['configured']:
                raise AIProviderError('ابتدا مدیر سامانه باید سرویس و مدل را در تنظیمات هوش مصنوعی ثبت کند.')
            if is_remote_provider(provider['provider']) and data.get('allow_external_data') is not True:
                raise ValueError('برای ارسال دادهٔ انتخاب‌شده به API اینترنتی، اجازهٔ ارسال را تأیید کنید.')
            records = _load_records(conn, student_ids, document_type, data.get('service_id'))
        control.allowed(provider,'documents',data.get('allow_external_data'))
        brief=_compose_brief(data,document_type)
        title, rendered_html = generate_document(provider, document_type, brief, records)
        if document_type=='receipt':
            rendered_html += '<p>مرجع سابقه: '+html.escape(records[0]['service_reference'])+' · تاریخ ثبت پرداخت: '+html.escape(records[0]['payment_date'])+' — این سند وضعیت مالی سابقهٔ منتخب است، نه رسید تراکنش بانکی.</p>'
        documents=archive.create_batch(title,rendered_html,records,student_ids,document_type,paper,brief)

        audit(
            session.get('user_id'), 'generate_ai_document', 'ai_document', document_type,
            f"students:{len(records)};provider:{provider['provider']};model:{provider['model']}",
        )
        return jsonify({'ok': True, 'title': title, 'html': rendered_html, 'paper': paper,'documents':[document_public(d) for d in documents]})
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    except AIProviderError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 502


def ai_documents_models():
    """Installed local Ollama models, so the design page can offer them.

    The URL is never taken from the request: only the local endpoint the app
    already uses is queried, so this cannot be turned into an open proxy.
    """
    if session.get('role') not in {'admin', 'manager'}:
        abort(403)
    with get_db() as conn:
        status = ollama_status(local_ollama_url(public_provider_config(conn)))
    return jsonify(status)


def ai_documents_select_provider():
    """Save which service (and local model) this user wants to work with."""
    if session.get('role') not in {'admin', 'manager'}:
        abort(403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = request.form
    try:
        if 'profile_id' in data:
            with get_db() as conn:
                task=str(data.get('use_case') or 'documents')
                control.select(conn,session['user_id'],task,str(data.get('profile_id') or ''))
                provider=effective_public_provider_config(conn,session['user_id'],task)
            return jsonify({'ok':True,'provider':provider})
        with get_db() as conn:
            control.select(conn,session['user_id'],'documents','__legacy__')
            provider = save_provider_selection(
                conn,
                session.get('user_id'),
                str(data.get('provider') or ''),
                str(data.get('model') or ''),
            )
            conn.commit()
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    audit(
        session.get('user_id'), 'select_ai_document_provider', 'ai_document',
        provider['provider'], f"provider:{provider['provider']};model:{provider['model']}",
    )
    return jsonify({'ok': True, 'provider': provider})


def ai_documents_save_connection():
    """Register the online service once, right from the design page (admin only).

    The design page is where the model is actually used, so the admin can paste
    the address and the API key here instead of walking to the settings page on
    every visit. The key is encrypted the same way the settings page does it.
    """
    if session.get('role') != 'admin':
        abort(403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = request.form.to_dict()
    form = dict(data)
    if form.pop('clear_api_key', False):
        form['clear_api_key'] = 'on'
    try:
        auto_backup()
        with get_db() as conn:
            saved = save_provider_config(conn, form)
            conn.commit()
            choices = provider_choices(conn)
        audit(
            session.get('user_id'), 'save_ai_document_provider', 'app_settings',
            'ai_documents:provider_config', f"{saved['provider']}:{saved['model']}",
        )
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    return jsonify({'ok': True, 'provider': saved, 'choices': choices})


def ai_documents_generate_letter():
    if session.get('role') not in {'admin', 'manager'}:
        abort(403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    brief = str(data.get('brief') or '').strip()
    paper = str(data.get('paper') or 'a4-portrait')
    template_key = str(data.get('template') or '').strip()
    raw_ids = data.get('student_ids')
    if not isinstance(raw_ids, list) and data.get('student_id') is not None:
        raw_ids = [data.get('student_id')]
    try:
        student_ids = _selected_ids(raw_ids)
        if not brief or len(brief) > 3000:
            raise ValueError('شرح متن نامه را وارد کنید (حداکثر ۳۰۰۰ نویسه).')
        if paper not in _PAPER_SIZES:
            raise ValueError('اندازهٔ کاغذ معتبر نیست.')
        with get_db() as conn:
            records = _load_records(conn, student_ids, 'letter')
            if template_key:
                layout = load_letter_template(conn, session.get('user_id'), template_key)
                if not layout:
                    raise ValueError('الگوی نامهٔ انتخاب‌شده پیدا نشد؛ فهرست الگوها را تازه کنید.')
            else:
                layout = load_letter_layout(conn, session.get('user_id'))
        width, height, effective_paper = _letter_page_size(paper, layout)
        fields={key:str(data.get(key) or '').strip()[:500] for key in ('subject','recipient','attachments')}
        copies=[]
        for record in records:
            title,copy_html=generate_letter_document(
                brief,record['student_name'],record['grade'],record['class_name'],record['school_name'],record['today'],
                layout=layout,page_size=(width,height),fields=fields)
            copies.append('<article class="ai-document-copy">'+copy_html+'</article>')
        rendered_html=''.join(copies)
        documents=archive.create_batch(title,rendered_html,records,student_ids,'letter',effective_paper,brief,fields)
        audit(
            session.get('user_id'), 'generate_letter', 'ai_document', 'letter',
            f"students:{len(records)};template:{template_key or 'current'};paper:{effective_paper}",
        )
        return jsonify({'ok': True, 'title': title, 'html': rendered_html, 'paper': effective_paper,'documents':[document_public(d) for d in documents]})
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400


def ai_letter_preview():
    """Real-size print preview of the letter with the saved layout."""
    if session.get('role') not in {'admin', 'manager'}:
        abort(403)
    with get_db() as conn:
        layout = load_letter_layout(conn, session.get('user_id'))
    return render_template(
        'ai_letter_preview.html',
        layout=layout,
        values=_LETTER_SAMPLE,
    )


def ai_documents_settings():
    if session.get('role') != 'admin':
        abort(403)
    from .. import ai_control as control
    if request.method == 'GET' and request.args.get('api') == '1':
        with get_db() as conn:
            return jsonify({'ok':True,'state':control.public(control.read(conn)),'usage':control.usage(conn)})
    if request.method == 'POST' and request.is_json:
        try:
            data=request.get_json(silent=True)
            if not isinstance(data,dict): raise ValueError('درخواست معتبر نیست.')
            if data.get('action')=='test':
                return jsonify({'ok':True,'test':control.test_profile(data)})
            auto_backup()
            state=control.update(data)
            audit(session.get('user_id'),'ai_control_update','app_settings',str(data.get('action')))
            return jsonify({'ok':True,'state':state})
        except (ValueError,TypeError,AIProviderError) as exc:
            return jsonify({'ok':False,'error':str(exc)}),400
    if request.method == 'POST':
        try:
            auto_backup()
            with get_db() as conn:
                saved = save_provider_config(conn, request.form)
                conn.commit()
            audit(
                session.get('user_id'), 'save_ai_document_provider', 'app_settings',
                'ai_documents:provider_config', f"{saved['provider']}:{saved['model']}",
            )
            flash('تنظیمات هوش مصنوعی ذخیره شد؛ کلید API به شکل رمزگذاری‌شده نگه‌داری می‌شود.', 'success')
            return redirect(url_for('ai_documents_settings'))
        except ValueError as exc:
            flash(str(exc), 'danger')

    with get_db() as conn:
        provider = public_provider_config(conn)
    return render_template(
        'ai_documents_settings.html',
        provider=provider,
        default_ollama_url=DEFAULT_OLLAMA_URL,
        default_gemini_url=DEFAULT_GEMINI_URL,
        default_gemini_model=DEFAULT_GEMINI_MODEL,
    )


def document_public(doc):
    return {**doc,'display_html':archive.display_html(doc),'warnings':archive.quality(doc)}


def document_api():
    try:
        if request.method=='GET':
            with get_db() as conn:
                ident=request.args.get('id')
                formrow=conn.execute('SELECT value FROM app_settings WHERE key=?',(f'ai_document_form:{session["user_id"]}',)).fetchone()
                form=json.loads(formrow['value']) if formrow else {}
                from ..ai_workspace import fingerprint
                if form.get('_fingerprint')!=fingerprint():form={}
                return jsonify({'ok':True,'documents':archive.list_docs(conn),'document':document_public(archive.load(conn,ident)) if ident else None,'form':form})
        data=request.get_json(silent=True)
        if not isinstance(data,dict):raise ValueError('درخواست معتبر نیست.')
        action=data.get('action')
        if action in ('design_preview','design_generate'):
            from .. import ai_design
            title,content=ai_design.user_content(data)
            brief=str(data.get('design_brief') or '')
            if len(brief)>2000:raise ValueError('شرح طراحی حداکثر ۲۰۰۰ نویسه است.')
            with get_db() as conn:cfg=effective_private_provider_config(conn,session['user_id'])
            if action=='design_preview':
                return jsonify({'ok':True,'payload':{'provider':cfg['provider'],'model':cfg['model'],'system':ai_design.DESIGN_PROMPT,'design_brief':brief,'note':'متن نامه و سلول‌های جدول محلی درج می‌شوند؛ فقط شرح طراحی ارسال می‌شود.'}})
            control.allowed(cfg,'documents',data.get('allow_external_data'))
            layout=ai_design.generate_layout(cfg,brief)
            doc=ai_design.save(title,content,layout,'designed_table' if data.get('kind')=='table' else 'designed_letter')
            return jsonify({'ok':True,'document':document_public(doc)})
        if action=='form_save':
            raw=data.get('form') or {}
            if not isinstance(raw,dict):raise ValueError('فرم معتبر نیست.')
            allowed_fields=('aiDocumentType','aiPaper','aiBrief','documentSubject','documentRecipient','documentAttachments','eventDate','eventTime','eventPlace')
            form={k:str(raw.get(k,'') or '')[:3000 if k=='aiBrief' else 200] for k in allowed_fields}
            form['student_ids']=[str(x) for x in raw.get('student_ids',[])[:100] if str(x).isdigit()] if isinstance(raw.get('student_ids',[]),list) else []
            from ..ai_workspace import fingerprint
            form['_fingerprint']=fingerprint()
            with get_db() as conn:conn.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(f'ai_document_form:{session["user_id"]}',json.dumps(form,ensure_ascii=False)))
            return jsonify({'ok':True})
        if action=='receipts':
            if 'monthly_service' not in current_session_endpoints():abort(403)
            ids=_selected_ids(data.get('student_ids'))
            if len(ids)!=1:raise ValueError('یک دانش‌آموز انتخاب کنید.')
            with get_db() as conn:
                rows=conn.execute('SELECT ms.id,ms.year,ms.month,ms.service_type,ms.amount,ms.paid_amount,ms.payment_date FROM monthly_service ms JOIN students s ON s.code=ms.student_code WHERE s.id=? ORDER BY ms.id DESC',(ids[0],)).fetchall()
            return jsonify({'ok':True,'records':[dict(r) for r in rows]})
        if action=='payload_preview':
            ids=_selected_ids(data.get('student_ids'));kind=str(data.get('document_type'))
            if kind not in DOCUMENT_TYPES:raise ValueError('نوع سند معتبر نیست.')
            if kind=='receipt' and 'monthly_service' not in current_session_endpoints():abort(403)
            with get_db() as conn:
                records=_load_records(conn,ids,kind,data.get('service_id'))
                policy=control.read(conn)['policy'];cfg=effective_public_provider_config(conn,session['user_id'])
            sent=[{k:'{{'+k+'}}' for k in records[0] if not k.startswith('_')}] if policy['anonymous_documents'] and cfg['provider']!='ollama' else [{k:v for k,v in rec.items() if not k.startswith('_')} for rec in records]
            return jsonify({'ok':True,'payload':{'brief':_compose_brief(data,kind),'students':sent,'provider':cfg['provider'],'school':'{{school_name}}' if policy['anonymous_documents'] and cfg['provider']!='ollama' else current_app.config.get('SCHOOL_NAME','')}})
        if action=='from_agent':
            from .. import ai_workspace as memory
            state=memory.load(data.get('conversation_id'));result=state['results'].get(data.get('result_id'))
            if not result or result['meta']['source']!='search_students':raise ValueError('فقط نتیجهٔ جستجوی دانش‌آموزان قابل انتقال است.')
            rows=result.get('rows') or [];ids=[int(r['id']) for r in rows if str(r.get('id','')).isdigit()]
            return jsonify({'ok':True,'student_ids':ids,'coverage':result['meta']['coverage']})
        if action=='export':
            with get_db() as conn:doc=archive.load(conn,data.get('id'))
            kind=str(data.get('format'));output=archive.export(doc,kind)
            types={'pdf':'application/pdf','pdf_design':'application/pdf','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','html':'text/html'}
            return send_file(output,as_attachment=True,download_name='document.'+('pdf' if kind=='pdf_design' else kind),mimetype=types[kind])
        if action=='revise':
            with get_db() as conn:cfg=effective_private_provider_config(conn,session['user_id'])
            control.allowed(cfg,'documents',data.get('allow_external_data'))
            doc=archive.revise_with_ai(data,cfg)
        else:doc=archive.mutate(data)
        audit(session['user_id'],'ai_document_'+str(action),'ai_document',str(data.get('id')))
        return jsonify({'ok':True,'document':document_public(doc) if doc else None})
    except (ValueError,TypeError,AIProviderError) as exc:
        return jsonify({'ok':False,'error':str(exc)}),400


def ai_settings_models():
    if session.get('role')!='admin': abort(403)
    try:
        status=ollama_status(request.args.get('url','') or DEFAULT_OLLAMA_URL)
        return jsonify({'ok':True,**status,'entries':status['models'],'models':[m['name'] for m in status['models']]})
    except ValueError as exc:
        return jsonify({'ok':False,'error':str(exc)}),400


def register(app):
    app.add_url_rule('/ai-documents', 'ai_documents', ai_documents, methods=['GET','POST'])
    app.add_url_rule('/ai-documents/generate', 'ai_documents_generate', ai_documents_generate, methods=['POST'])
    app.add_url_rule('/ai-documents/models', 'ai_documents_models', ai_documents_models, methods=['GET'])
    app.add_url_rule(
        '/ai-documents/provider', 'ai_documents_select_provider',
        ai_documents_select_provider, methods=['POST'],
    )
    app.add_url_rule(
        '/ai-documents/connection', 'ai_documents_save_connection',
        ai_documents_save_connection, methods=['POST'],
    )
    app.add_url_rule('/ai-documents/generate-letter', 'ai_documents_generate_letter', ai_documents_generate_letter, methods=['POST'])
    app.add_url_rule(
        '/settings/ai-documents', 'ai_documents_settings', ai_documents_settings,
        methods=['GET', 'POST'],
    )
    app.add_url_rule('/ai-letter-preview', 'ai_letter_preview', ai_letter_preview, methods=['GET'])
    app.add_url_rule(
        '/settings/ai-documents/models', 'ai_documents_list_models',
        ai_settings_models,
        methods=['GET'],
    )
