#!/usr/bin/env python
"""Optional real Chromium/PyMuPDF multi-page graphic-PDF regression."""
import pymupdf
import ai_agent_test as base
from school_app import ai_design as design
from school_app import ai_document_store as archive
with base.app.app_context():
    body='<h1>گزارش چندصفحه‌ای</h1><table><thead><tr><th>CODE</th><th>وضعیت</th></tr></thead><tbody>'+''.join('<tr><td>ROW%03d</td><td>آزمایشی</td></tr>'%i for i in range(1,201))+'</tbody></table>'
    doc={'title':'آزمون چاپ','html':design.compose(None,body),'paper':'a4','status':'void','number':'1405/000001','updated':archive.timestamp()}
    output=design.graphic_pdf(doc)
    pdf=pymupdf.open(stream=output.getvalue(),filetype='pdf')
    assert len(pdf)>1
    for page in pdf:
        text=page.get_text()
        assert 'باطل' in text,text
        assert '1405/000001' in text,text
        assert 'CODE' in text,text
    assert 'ROW200' in ''.join(p.get_text() for p in pdf)
    print('PASS: %s graphic PDF pages, repeated table header, repeated void status/number, final row preserved'%len(pdf))
