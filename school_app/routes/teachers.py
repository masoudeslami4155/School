from __future__ import annotations

import re
import secrets
from datetime import datetime

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from ..database import auto_backup, get_db
from ..security import audit


def _data(form):
    return {
        'first_name': (form.get('first_name') or '').strip()[:80],
        'last_name': (form.get('last_name') or '').strip()[:100],
        'code': (form.get('code') or '').strip()[:50],
        'subject': (form.get('subject') or '').strip()[:100],
        'class_name': (form.get('class_name') or '').strip()[:80],
        'sida_class': (form.get('sida_class') or '').strip()[:80],
        'national_id': (form.get('national_id') or '').strip()[:10],
        'phone': (form.get('phone') or '').strip()[:15],
    }


def _errors(data):
    errors = []
    if not data['first_name'] or not data['last_name'] or not data['code']:
        errors.append('نام، نام‌خانوادگی و کد پرسنلی الزامی است.')
    if data['national_id'] and (len(data['national_id']) != 10 or not data['national_id'].isdigit()):
        errors.append('کد ملی باید دقیقاً ۱۰ رقم باشد.')
    if data['phone'] and (not data['phone'].isdigit() or len(data['phone']) < 10):
        errors.append('شماره تماس نامعتبر است.')
    return errors


def teachers():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM teachers ORDER BY id DESC').fetchall()
    return render_template('teachers.html', teachers=rows)


def add_teacher():
    if request.method == 'POST':
        data = _data(request.form)
        errors = _errors(data)
        if errors:
            return render_template('add_teacher.html', errors=errors, form_data=data)
        temporary = secrets.token_urlsafe(10)
        try:
            auto_backup()
            with get_db() as conn:
                conn.execute('''INSERT INTO teachers(first_name,last_name,code,subject,class_name,sida_class,national_id,phone)
                                VALUES(?,?,?,?,?,?,?,?)''', tuple(data.values()))
                user_role = request.form.get('role', 'teacher') if request.form.get('role') in {'teacher', 'manager'} else 'teacher'
                existing = conn.execute('SELECT id FROM users WHERE personnel_number=?', (data['code'],)).fetchone()
                if existing:
                    conn.execute('''UPDATE users SET full_name=?,role=?,teacher_code=?,national_id=?,phone=?,is_active=1
                                    WHERE id=?''',
                                 (f"{data['first_name']} {data['last_name']}", user_role, data['code'], data['national_id'], data['phone'], existing['id']))
                    user_id = existing['id']
                    temporary = None
                else:
                    conn.execute('''INSERT INTO users(personnel_number,full_name,password_hash,role,teacher_code,national_id,phone,created_at)
                                    VALUES(?,?,?,?,?,?,?,?)''',
                                 (data['code'], f"{data['first_name']} {data['last_name']}", generate_password_hash(temporary), user_role,
                                  data['code'], data['national_id'], data['phone'], datetime.now().isoformat()))
                    user_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                conn.commit()
            audit(session.get('user_id'), 'create_teacher', 'teacher', data['code'])
            msg = 'معلم و حساب کاربری ایجاد شد.'
            if temporary:
                msg += f' رمز موقت: {temporary} — آن را حضوری تحویل دهید.'
            flash(msg, 'success')
            return redirect(url_for('teachers'))
        except Exception:
            return render_template('add_teacher.html', errors=['کد پرسنلی تکراری است.'], form_data=data)
    return render_template('add_teacher.html', errors=None, form_data={})


def edit_teacher(id):
    with get_db() as conn:
        teacher = conn.execute('SELECT * FROM teachers WHERE id=?', (id,)).fetchone()
    if not teacher:
        flash('معلم پیدا نشد.', 'danger')
        return redirect(url_for('teachers'))
    if request.method == 'POST':
        data = _data(request.form)
        errors = _errors(data)
        if errors:
            return render_template('edit_teacher.html', errors=errors, form_data=data, teacher_id=id)
        try:
            auto_backup()
            with get_db() as conn:
                conn.execute('''UPDATE teachers SET first_name=?,last_name=?,code=?,subject=?,class_name=?,
                                sida_class=?,national_id=?,phone=? WHERE id=?''', tuple(data.values()) + (id,))
                conn.execute('''UPDATE users SET personnel_number=?,full_name=?,teacher_code=?,national_id=?,phone=?
                                WHERE teacher_code=?''',
                             (data['code'], f"{data['first_name']} {data['last_name']}", data['code'], data['national_id'], data['phone'], teacher['code']))
                conn.execute('UPDATE students SET teacher_code=? WHERE teacher_code=?', (data['code'], teacher['code']))
                conn.execute('UPDATE attendance_teachers SET teacher_code=? WHERE teacher_code=?', (data['code'], teacher['code']))
                conn.commit()
            audit(session.get('user_id'), 'edit_teacher', 'teacher', id)
            flash('اطلاعات معلم به‌روزرسانی شد.', 'success')
            return redirect(url_for('teachers'))
        except Exception:
            return render_template('edit_teacher.html', errors=['کد پرسنلی تکراری است.'], form_data=data, teacher_id=id)
    return render_template('edit_teacher.html', errors=None, form_data=dict(teacher), teacher_id=id)


def delete_teacher(id):
    with get_db() as conn:
        teacher = conn.execute('SELECT * FROM teachers WHERE id=?', (id,)).fetchone()
        if not teacher:
            flash('معلم پیدا نشد.', 'danger')
            return redirect(url_for('teachers'))
        if request.method == 'POST':
            auto_backup()
            conn.execute("UPDATE students SET teacher_code='' WHERE teacher_code=?", (teacher['code'],))
            conn.execute("UPDATE attendance_teachers SET teacher_code='' WHERE teacher_code=?", (teacher['code'],))
            conn.execute("UPDATE users SET is_active=0,teacher_code=NULL WHERE teacher_code=?", (teacher['code'],))
            conn.execute('DELETE FROM teachers WHERE id=?', (id,))
            conn.commit()
    audit(session.get('user_id'), 'delete_teacher', 'teacher', id)
    flash('معلم حذف شد و انتساب‌های او به «ثبت نشده» منتقل شد.', 'success')
    return redirect(url_for('teachers'))


def register(app):
    app.add_url_rule('/teachers', endpoint='teachers', view_func=teachers)
    app.add_url_rule('/add_teacher', endpoint='add_teacher', view_func=add_teacher, methods=['GET', 'POST'])
    app.add_url_rule('/teachers/<int:id>/edit', endpoint='edit_teacher', view_func=edit_teacher, methods=['GET', 'POST'])
    app.add_url_rule('/delete_teacher/<int:id>', endpoint='delete_teacher', view_func=delete_teacher, methods=['POST'])
