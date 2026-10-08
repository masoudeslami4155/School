from __future__ import annotations

import json

from flask import abort, flash, redirect, render_template, request, session, url_for

from ..database import auto_backup, get_db
from ..print_layouts import (
    DOCUMENTS as SERVICE_DOCUMENTS,
    SLIP_ELEMENT_LABELS,
    default_layout as default_service_layout,
    load_layout as load_service_layout,
    reset_layout as reset_service_layout,
    save_layout as save_service_layout,
)
from ..report_print_layouts import (
    REPORT_COLUMNS,
    REPORT_DOCUMENTS,
    REPORT_SECTIONS,
    default_layout as default_report_layout,
    load_layout as load_report_layout,
    reset_layout as reset_report_layout,
    save_layout as save_report_layout,
)
from ..ai_letter_layout import (
    ELEMENT_LABELS as LETTER_ELEMENT_LABELS,
    default_layout as default_letter_layout,
    delete_user_template as delete_letter_template,
    list_templates as list_letter_templates,
    load_layout as load_letter_layout,
    reset_layout as reset_letter_layout,
    save_layout as save_letter_layout,
    save_user_template as save_letter_template,
)
from ..security import audit
from ..student_dashboard import STUDENT_FILTER_REFERENCE
from ..student_certificate_layout import (
    ELEMENT_LABELS as CERTIFICATE_ELEMENT_LABELS,
    default_layout as default_certificate_layout,
    load_layout as load_certificate_layout,
    reset_layout as reset_certificate_layout,
    save_layout as save_certificate_layout,
)


_STUDENT_CONTEXT_KEYS = ('ids', 'q', 'grade', 'class_name', 'sida_class', 'gender', 'teacher_code')


PRINT_STUDIO_DOCUMENTS = {
    **{
        key: {**info, 'mode': 'service', 'group': 'سرویس و امور مالی'}
        for key, info in SERVICE_DOCUMENTS.items()
    },
    **{
        key: {**info, 'mode': 'report', 'group': 'گزارش‌های مدرسه'}
        for key, info in REPORT_DOCUMENTS.items()
    },
    'student_certificate': {
        'label': 'گواهی اشتغال به تحصیل',
        'short_label': 'گواهی تحصیل',
        'kind': 'certificate',
        'preview_endpoint': 'student_certificate',
        'preview_query': {},
        'mode': 'certificate',
        'group': 'گواهی‌ها',
    },
    'ai_letter': {
        'label': 'نامهٔ اداری هوشمند',
        'short_label': 'نامهٔ اداری',
        'kind': 'ai_letter',
        'preview_endpoint': 'ai_letter_preview',
        'preview_query': {},
        'mode': 'ai_letter',
        'group': 'اسناد هوشمند',
    },
}


def _document_info(document: str) -> dict:
    return PRINT_STUDIO_DOCUMENTS[document]


def _document_key(value: str | None) -> str:
    return value if value in PRINT_STUDIO_DOCUMENTS else 'attendance_students'


def _is_service_document(document: str) -> bool:
    return document in SERVICE_DOCUMENTS


def _is_certificate_document(document: str) -> bool:
    return document == 'student_certificate'


def _is_ai_letter_document(document: str) -> bool:
    return document == 'ai_letter'


def _student_context_args(values=None) -> dict[str, str]:
    values = values or request.values
    return {
        key: value for key in _STUDENT_CONTEXT_KEYS
        if (value := values.get(key)) not in (None, '')
    }


def _preview_url(document: str) -> str:
    info = _document_info(document)
    if _is_certificate_document(document):
        return url_for('student_certificate')
    if _is_ai_letter_document(document):
        return url_for('ai_letter_preview')
    if _is_service_document(document):
        query = {}
        if document == 'service_request':
            query['kind'] = 'requests'
        elif document == 'service_receipt':
            query['kind'] = 'receipts'
        return url_for(info['preview_endpoint'], **query)
    query = dict(info['preview_query'])
    if document == 'wall_cards':
        query.update(_student_context_args())
    if document == 'student_info':
        return url_for(info['preview_endpoint'], q='')
    return url_for(info['preview_endpoint'], **query)


def report_print_layouts():
    document = _document_key(request.args.get('document') or request.form.get('document'))
    user_id = session.get('user_id')
    is_service = _is_service_document(document)
    is_certificate = _is_certificate_document(document)
    is_ai_letter = _is_ai_letter_document(document)
    if (is_service or is_certificate or is_ai_letter) and session.get('role') == 'teacher':
        abort(403)
    if request.method == 'POST':
        action = (request.form.get('action') or 'save').strip()
        auto_backup()
        with get_db() as conn:
            if is_ai_letter and action in {'save_template', 'delete_template'}:
                template_key = str(request.form.get('template_key') or '').strip()
                if action == 'save_template':
                    template_label = str(request.form.get('template_label') or '').strip()
                    try:
                        raw = json.loads(request.form.get('layout_json') or '{}')
                    except (TypeError, ValueError, json.JSONDecodeError):
                        raw = None
                    if not isinstance(raw, dict):
                        flash('چیدمان الگوی نامه معتبر نیست و ذخیره نشد.', 'danger')
                    else:
                        try:
                            save_letter_template(conn, user_id, template_key, template_label, raw)
                            conn.commit()
                            audit(user_id, 'save_ai_letter_template', 'app_settings',
                                  f'user:{user_id}:ai_letter:{template_key}')
                            flash('الگوی نامه با موفقیت ذخیره شد.', 'success')
                        except ValueError as exc:
                            flash(str(exc), 'danger')
                else:
                    try:
                        delete_letter_template(conn, user_id, template_key)
                        conn.commit()
                        audit(user_id, 'delete_ai_letter_template', 'app_settings',
                              f'user:{user_id}:ai_letter:{template_key}')
                        flash('الگوی نامه حذف شد.', 'info')
                    except ValueError as exc:
                        flash(str(exc), 'danger')
                return redirect(url_for(
                    'report_print_layouts', document=document,
                    **_student_context_args(request.values),
                ))
            if action == 'reset':
                if is_certificate:
                    reset_certificate_layout(conn, user_id)
                elif is_ai_letter:
                    reset_letter_layout(conn, user_id)
                else:
                    reset = reset_service_layout if is_service else reset_report_layout
                    reset(conn, document, user_id)
                conn.commit()
                audit_name = (
                    'reset_student_certificate_layout' if is_certificate
                    else 'reset_ai_letter_layout' if is_ai_letter
                    else 'reset_print_layout' if is_service
                    else 'reset_report_print_layout'
                )
                audit(user_id, audit_name, 'app_settings', f'user:{user_id}:{document}')
                flash('چیدمان این چاپ به حالت پیش‌فرض برگشت.', 'info')
            else:
                try:
                    raw = json.loads(request.form.get('layout_json') or '{}')
                except (TypeError, ValueError, json.JSONDecodeError):
                    raw = None
                if not isinstance(raw, dict):
                    flash('تنظیمات چاپ نامعتبر است و ذخیره نشد.', 'danger')
                else:
                    if is_certificate:
                        saved = save_certificate_layout(conn, user_id, raw)
                    elif is_ai_letter:
                        saved = save_letter_layout(conn, user_id, raw)
                    else:
                        save = save_service_layout if is_service else save_report_layout
                        saved = save(conn, document, user_id, raw)
                    conn.commit()
                    audit_name = (
                        'save_student_certificate_layout' if is_certificate
                        else 'save_ai_letter_layout' if is_ai_letter
                        else 'save_print_layout' if is_service
                        else 'save_report_print_layout'
                    )
                    audit(user_id, audit_name, 'app_settings', f'user:{user_id}:{document}',
                          json.dumps(saved, ensure_ascii=False)[:600])
                    flash('چیدمان چاپ با موفقیت ذخیره شد.', 'success')
        return redirect(url_for(
            'report_print_layouts', document=document,
            **_student_context_args(request.values),
        ))

    letter_templates = []
    with get_db() as conn:
        if is_certificate:
            layout = load_certificate_layout(conn, user_id)
        elif is_ai_letter:
            layout = load_letter_layout(conn, user_id)
            letter_templates = list_letter_templates(conn, user_id)
        else:
            load = load_service_layout if is_service else load_report_layout
            layout = load(conn, document, user_id)

    documents = []
    for key, info in PRINT_STUDIO_DOCUMENTS.items():
        documents.append({
            'key': key,
            **info,
            'url': url_for('report_print_layouts', document=key, **_student_context_args()),
            'preview_url': _preview_url(key),
        })

    document_groups = []
    for group in ('سرویس و امور مالی', 'گزارش‌های مدرسه', 'گواهی‌ها', 'اسناد هوشمند'):
        document_groups.append({
            'label': group,
            'items': [item for item in documents if item['group'] == group],
        })
    info = _document_info(document)
    if is_certificate:
        return render_template(
            'student_certificate_studio.html',
            document=document,
            layout=layout,
            layout_json=json.dumps(layout, ensure_ascii=False),
            default_layout_json=json.dumps(default_certificate_layout(), ensure_ascii=False),
            element_labels=CERTIFICATE_ELEMENT_LABELS,
            active_preview_url=_preview_url(document),
        )
    if is_ai_letter:
        return render_template(
            'ai_letter_studio.html',
            document=document,
            layout=layout,
            layout_json=json.dumps(layout, ensure_ascii=False),
            default_layout_json=json.dumps(default_letter_layout(), ensure_ascii=False),
            element_labels=LETTER_ELEMENT_LABELS,
            templates=letter_templates,
            templates_json=json.dumps(letter_templates, ensure_ascii=False),
            active_preview_url=_preview_url(document),
        )

    default = default_service_layout if is_service else default_report_layout

    return render_template(
        'print_studio.html',
        document=document,
        document_kind=info['kind'],
        mode=info['mode'],
        documents=documents,
        document_groups=document_groups,
        layout=layout,
        layout_json=json.dumps(layout, ensure_ascii=False),
        default_layout=default(document),
        element_labels=SLIP_ELEMENT_LABELS if is_service else {},
        columns=REPORT_COLUMNS.get(document, []),
        summary_columns=REPORT_COLUMNS.get('attendance_teachers_summary', []),
        detail_columns=REPORT_COLUMNS.get('attendance_teachers_detail', []),
        sections=REPORT_SECTIONS.get(document, []),
        filter_reference=STUDENT_FILTER_REFERENCE,
        student_context=_student_context_args(),
        active_preview_url=_preview_url(document),
    )


def student_filters_print():
    with get_db() as conn:
        layout = load_report_layout(conn, 'student_filters', session.get('user_id'))
    return render_template(
        'print_student_filters.html',
        filters=STUDENT_FILTER_REFERENCE,
        layout=layout,
        autoprint=request.args.get('autoprint') == '1',
    )


def register(app):
    app.add_url_rule('/report-print-layouts', 'report_print_layouts', report_print_layouts, methods=['GET', 'POST'])
    app.add_url_rule('/print-student-filters', 'student_filters_print', student_filters_print, methods=['GET'])
