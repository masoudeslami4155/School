from __future__ import annotations

from flask import redirect, request, url_for

from ..print_layouts import DOCUMENTS


def _document_key(value: str | None) -> str:
    return value if value in DOCUMENTS else 'service_receipt'


def print_layouts():
    document = _document_key(request.args.get('document') or request.form.get('document'))
    code = 307 if request.method == 'POST' else 302
    return redirect(url_for('report_print_layouts', document=document), code=code)


def register(app):
    app.add_url_rule('/print-layouts', 'print_layouts', print_layouts, methods=['GET', 'POST'])
