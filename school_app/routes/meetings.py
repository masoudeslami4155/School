from datetime import datetime
from flask import abort, flash, redirect, render_template, request, session, url_for
from ..database import get_db
from ..security import audit, current_user_role
TYPES=('شورای مدرسه','شورای معلمان','سرگروه آموزشی')
ROLES=('مدیر','معاون','مشاور','معاون پرورشی','نماینده معلمان','نماینده انجمن اولیا','سایر')
def schema():
 with get_db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS meetings (id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_type TEXT NOT NULL, meeting_date TEXT NOT NULL, meeting_time TEXT DEFAULT "", location TEXT DEFAULT "", subject TEXT NOT NULL, agenda TEXT DEFAULT "", decisions TEXT DEFAULT "", follow_up TEXT DEFAULT "", created_by INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS meeting_participants (id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id INTEGER NOT NULL, full_name TEXT NOT NULL, participant_role TEXT NOT NULL, source_teacher_id INTEGER, FOREIGN KEY(meeting_id) REFERENCES meetings(id) ON DELETE CASCADE)')
  c.commit()
def staff():
 with get_db() as c:return c.execute('SELECT id,first_name,last_name,subject FROM teachers ORDER BY last_name,first_name').fetchall()
def data(f):return {k:(f.get(k) or '').strip() for k in ('meeting_type','meeting_date','meeting_time','location','subject','agenda','decisions','follow_up')}
def meetings():
 schema()
 with get_db() as c: rows=c.execute('SELECT * FROM meetings ORDER BY id DESC').fetchall()
 return render_template('meetings.html',meetings=rows)
def meeting_new():
 schema(); d=data(request.form) if request.method=='POST' else {}; errors=[]
 if request.method=='POST':
  if d['meeting_type'] not in TYPES: errors.append('نوع جلسه را انتخاب کنید.')
  if not d['meeting_date']: errors.append('تاریخ جلسه الزامی است.')
  if not d['subject']: errors.append('موضوع جلسه الزامی است.')
  ids=request.form.getlist('participant_ids')
  if not ids: errors.append('حداقل یک عضو جلسه را انتخاب کنید.')
  if errors:return render_template('meeting_form.html',form_data=d,staff=staff(),roles=ROLES,errors=errors)
  now=datetime.now().isoformat(timespec='seconds')
  with get_db() as c:
   cur=c.execute('INSERT INTO meetings(meeting_type,meeting_date,meeting_time,location,subject,agenda,decisions,follow_up,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',tuple(d.values())+(session.get('user_id'),now,now)); mid=cur.lastrowid
   rows={str(x['id']):x for x in staff()}
   for sid in ids:
    if sid in rows:
     role=request.form.get('participant_role_'+sid,'سایر'); role=role if role in ROLES else 'سایر'; x=rows[sid]; name=f"{x['first_name'] or ''} {x['last_name'] or ''}".strip(); c.execute('INSERT INTO meeting_participants(meeting_id,full_name,participant_role,source_teacher_id) VALUES(?,?,?,?)',(mid,name,role,x['id']))
   c.commit()
  audit(session.get('user_id'),'create_meeting','meeting',mid,d['meeting_type']); flash('صورت‌جلسه با موفقیت ثبت شد.','success'); return redirect(url_for('meeting_view',id=mid))
 return render_template('meeting_form.html',form_data=d,staff=staff(),roles=ROLES,errors=errors)
def meeting_view(id):
 schema()
 with get_db() as c:m=c.execute('SELECT * FROM meetings WHERE id=?',(id,)).fetchone(); ps=c.execute('SELECT * FROM meeting_participants WHERE meeting_id=? ORDER BY id',(id,)).fetchall()
 if not m:abort(404)
 return render_template('meeting_print.html',meeting=m,participants=ps)
def meeting_delete(id):
 if current_user_role() not in {'admin','manager'}:abort(403)
 schema()
 with get_db() as c:c.execute('DELETE FROM meeting_participants WHERE meeting_id=?',(id,)); c.execute('DELETE FROM meetings WHERE id=?',(id,)); c.commit()
 audit(session.get('user_id'),'delete_meeting','meeting',id); flash('صورت‌جلسه حذف شد.','success'); return redirect(url_for('meetings'))
def register(app):
 app.add_url_rule('/meetings',endpoint='meetings',view_func=meetings); app.add_url_rule('/meetings/new',endpoint='meeting_new',view_func=meeting_new,methods=['GET','POST']); app.add_url_rule('/meetings/<int:id>',endpoint='meeting_view',view_func=meeting_view); app.add_url_rule('/meetings/<int:id>/delete',endpoint='meeting_delete',view_func=meeting_delete,methods=['POST'])
