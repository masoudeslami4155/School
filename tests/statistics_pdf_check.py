#!/usr/bin/env python
"""Optional real Chromium/PyMuPDF long-report and detail-export checks."""
import pymupdf
import statistics_fixture as F
from urllib.parse import urlencode
with F.app.app_context():
    with F.get_db() as c:
        for i in range(120):
            c.execute("INSERT INTO students(code,first_name,last_name,grade,class_name,status,teacher_code,gender) VALUES(?,?,?,?,?,'فعال','T1','پسر')",(f'PDF-{i:03d}','نام آزمایشی',f'{i:03d}',f'GRADE{i:03d}','PDF-CHECK'))
client=F.client()
for detail in (False,True):
    query={'action':'students' if detail else 'export','format':'pdf','class_name':'PDF-CHECK','orientation':'portrait','grade_totals':0,'teacher_totals':0}
    response=client.get('/statistics?'+urlencode(query))
    assert response.status_code==200,response.data
    pdf=pymupdf.open(stream=response.data,filetype='pdf');assert len(pdf)>1
    texts=[page.get_text() for page in pdf]
    assert ('PDF-119' if detail else 'GRADE119') in ''.join(texts)
    for text in texts:
        assert 'صفحه' in text,text
        assert 'معلم' in text,text
        assert ('نام' if detail else 'سهم') in text,text
    print('PASS: %s PDF, %s pages, repeated headers/page numbers, final row intact'%('student list' if detail else 'summary',len(pdf)))
