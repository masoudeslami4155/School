"""Isolated synthetic fixtures for the user's frequency-statistics redesign."""
import os
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
TMP=Path(tempfile.mkdtemp(prefix='statistics-463-'))
os.environ.update(DATABASE_PATH=str(TMP/'school.db'),BACKUP_DIR=str(TMP/'backups'),LOG_DIR=str(TMP/'logs'),UPLOAD_FOLDER=str(TMP/'uploads'),SECRET_KEY='statistics-463-isolated-test-key')
from school_app import app
from school_app.database import get_db
app.config.update(TESTING=True,PROPAGATE_EXCEPTIONS=True)
with app.app_context():
    with get_db() as c:
        c.execute("INSERT INTO teachers(code,first_name,last_name) VALUES('T1','معلم','اول'),('T2','معلم','دوم'),(' T1 ','نام','تکراری')")
        specs=[('T1','پایه اول','پسر','فعال','الف'),('T1','پایه اول','male',None,'الف'),('T1','پایه اول','مونث',' ','الف'),('T2','پایه اول','دختر','فارغ‌التحصیل','الف'),('T1','پایه دوم','','فعال','ب'),('T2','پایه دوم','پسر','فعال','ب'),('T2','پایه دوم','پسر','ترک تحصیل','ب'),(None,'آمادگی مقدماتی','نامعتبر','فعال','ب'),('INVALID','آمادگی تکمیلی','دختر','فعال','ب'),('T2',None,'پسر','فعال','ب')]
        for i,(teacher,grade,gender,status,klass) in enumerate(specs,1):
            c.execute('INSERT INTO students(code,first_name,last_name,status,teacher_code,grade,gender,class_name,sida_class) VALUES(?,?,?,?,?,?,?,?,?)',(str(i).zfill(4),'نمونه '+str(i),'آزمایشی',status,teacher,grade,gender,klass,'سیدا الف' if klass=='الف' else 'سیدا ب'))


def client(role='admin',permissions='',user_id=463):
    c=app.test_client()
    with c.session_transaction() as s:s.update(user_id=user_id,role=role,personnel_number='T1',full_name='آزمایش آمار',permissions=permissions,_csrf_token='test-463')
    return c
