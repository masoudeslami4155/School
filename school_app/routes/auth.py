from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..database import auto_backup, get_db
from ..security import audit, PERMISSION_LABELS, MANAGER_ENDPOINTS, TEACHER_ENDPOINTS


def _clean(value: str | None, limit: int = 120) -> str:
    return (value or '').strip()[:limit]


def _valid_national_id(value: str) -> bool:
    return not value or (len(value) == 10 and value.isdigit())


def _valid_phone(value: str) -> bool:
    return not value or (value.isdigit() and 10 <= len(value) <= 15)


def health():
    try:
        with get_db() as conn:
            conn.execute('SELECT 1').fetchone()
        return jsonify({'status': 'ok'})
    except Exception:
        return jsonify({'status': 'error'}), 503


def login():
    if request.method == 'POST':
        personnel_number = _clean(request.form.get('personnel_number'), 50)
        password = request.form.get('password', '')
        with get_db() as conn:
            user = conn.execute(
                'SELECT * FROM users WHERE personnel_number=? AND is_active=1', (personnel_number,)
            ).fetchone()
        if not user or not check_password_hash(user['password_hash'], password):
            flash('کد پرسنلی یا رمز عبور نادرست است.', 'danger')
            return render_template('login.html', personnel_number=personnel_number)
        session.clear()
        session.update({
            'user_id': user['id'], 'personnel_number': user['personnel_number'],
            'full_name': user['full_name'], 'role': user['role'],
            'must_change_password': bool(user['must_change_password']),
            'permissions': user['permissions'] or '',
        })
        session.setdefault('_csrf_token', secrets.token_urlsafe(32))
        audit(user['id'], 'login', 'user', user['id'])
        if user['must_change_password']:
            flash('برای امنیت، ابتدا رمز عبور اولیه را تغییر دهید.', 'info')
            return redirect(url_for('change_password'))
        target = request.args.get('next', '')
        return redirect(target if target.startswith('/') and not target.startswith('//') else url_for('index'))
    return render_template('login.html')


def logout():
    user_id = session.get('user_id')
    if user_id:
        audit(user_id, 'logout', 'user', user_id)
    session.clear()
    flash('با موفقیت خارج شدید.', 'success')
    return redirect(url_for('login'))


def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        repeat = request.form.get('repeat_password', '')
        if len(new_password) < 8:
            flash('رمز عبور باید حداقل ۸ کاراکتر باشد.', 'danger')
        elif new_password != repeat:
            flash('تکرار رمز عبور یکسان نیست.', 'danger')
        else:
            auto_backup()
            with get_db() as conn:
                conn.execute(
                    'UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?',
                    (generate_password_hash(new_password), session['user_id']),
                )
                conn.commit()
            session['must_change_password'] = False
            audit(session['user_id'], 'change_password', 'user', session['user_id'])
            flash('رمز عبور با موفقیت تغییر کرد.', 'success')
            return redirect(url_for('index'))
    return render_template('change_password.html')


def users():
    with get_db() as conn:
        rows = conn.execute(
            'SELECT id,personnel_number,full_name,role,is_active,must_change_password,teacher_code,national_id,phone,permissions '
            'FROM users ORDER BY full_name'
        ).fetchall()
    return render_template('users.html', users=rows)


def add_user():
    if request.method == 'POST':
        data = {
            'personnel_number': _clean(request.form.get('personnel_number'), 50),
            'full_name': _clean(request.form.get('full_name'), 120),
            'role': _clean(request.form.get('role'), 20),
            'teacher_code': _clean(request.form.get('teacher_code'), 50),
            'permissions': ','.join(sorted(set(request.form.getlist('permissions')) & set(PERMISSION_LABELS))) or '__none__',
            'national_id': _clean(request.form.get('national_id'), 10),
            'phone': _clean(request.form.get('phone'), 15),
        }
        errors = []
        if not data['personnel_number'] or not data['full_name']:
            errors.append('نام کامل و شماره پرسنلی الزامی است.')
        if data['role'] not in {'admin', 'manager', 'teacher'}:
            errors.append('نقش انتخاب‌شده معتبر نیست.')
        if not _valid_national_id(data['national_id']):
            errors.append('کد ملی باید ۱۰ رقم باشد.')
        if not _valid_phone(data['phone']):
            errors.append('شماره تماس نامعتبر است.')
        if data['role'] == 'teacher' and not data['teacher_code']:
            errors.append('برای حساب معلم، کد معلم الزامی است.')
        if errors:
            return render_template('user_form.html', errors=errors, form_data=data, editing=False, permission_choices=PERMISSION_LABELS)
        temporary = secrets.token_urlsafe(10)
        try:
            auto_backup()
            with get_db() as conn:
                conn.execute(
                    '''INSERT INTO users(personnel_number,full_name,password_hash,role,is_active,
                       must_change_password,teacher_code,national_id,phone,permissions,created_at)
                       VALUES(?,?,?,?,1,1,?,?,?,?,datetime('now'))''',
                    (data['personnel_number'], data['full_name'], generate_password_hash(temporary),
                     data['role'], data['teacher_code'] or None, data['national_id'], data['phone'], data['permissions']),
                )
                conn.commit()
                user_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            audit(session.get('user_id'), 'create_user', 'user', user_id, data['personnel_number'])
            flash(f'کاربر ایجاد شد. رمز موقت: {temporary} — آن را حضوری و امن تحویل دهید.', 'success')
            return redirect(url_for('users'))
        except Exception:
            return render_template('user_form.html', errors=['شماره پرسنلی تکراری است.'], form_data=data, editing=False, permission_choices=PERMISSION_LABELS)
    return render_template('user_form.html', errors=None, form_data={}, editing=False, permission_choices=PERMISSION_LABELS)


def edit_user(id):
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id=?', (id,)).fetchone()
    if not user:
        flash('کاربر پیدا نشد.', 'danger')
        return redirect(url_for('users'))
    if request.method == 'POST':
        data = {
            'personnel_number': _clean(request.form.get('personnel_number'), 50),
            'full_name': _clean(request.form.get('full_name'), 120),
            'role': _clean(request.form.get('role'), 20),
            'teacher_code': _clean(request.form.get('teacher_code'), 50),
            'permissions': ','.join(sorted(set(request.form.getlist('permissions')) & set(PERMISSION_LABELS))) or '__none__',
            'national_id': _clean(request.form.get('national_id'), 10),
            'phone': _clean(request.form.get('phone'), 15),
        }
        errors = []
        if not data['full_name'] or not data['personnel_number']:
            errors.append('نام و شماره پرسنلی الزامی است.')
        if data['role'] not in {'admin', 'manager', 'teacher'}:
            errors.append('نقش معتبر نیست.')
        if not _valid_national_id(data['national_id']):
            errors.append('کد ملی باید ۱۰ رقم باشد.')
        if not _valid_phone(data['phone']):
            errors.append('شماره تماس نامعتبر است.')
        if data['role'] == 'teacher' and not data['teacher_code']:
            errors.append('برای حساب معلم، کد معلم الزامی است.')
        if user['role'] == 'admin' and data['role'] != 'admin':
            with get_db() as conn:
                active_admins = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND is_active=1").fetchone()['n']
            if active_admins <= 1:
                errors.append('نقش آخرین مدیر سیستم قابل کاهش نیست.')
        if errors:
            return render_template('user_form.html', errors=errors, form_data=data, editing=True, user_id=id, permission_choices=PERMISSION_LABELS)
        try:
            auto_backup()
            with get_db() as conn:
                conn.execute(
                    '''UPDATE users SET personnel_number=?,full_name=?,role=?,teacher_code=?,
                       national_id=?,phone=?,permissions=? WHERE id=?''',
                    (data['personnel_number'], data['full_name'], data['role'], data['teacher_code'] or None,
                     data['national_id'], data['phone'], data['permissions'], id),
                )
                conn.commit()
            audit(session.get('user_id'), 'edit_user', 'user', id)
            flash('اطلاعات کاربر به‌روزرسانی شد.', 'success')
            return redirect(url_for('users'))
        except Exception:
            return render_template('user_form.html', errors=['شماره پرسنلی تکراری است.'], form_data=data, editing=True, user_id=id, permission_choices=PERMISSION_LABELS)
    return render_template('user_form.html', errors=None, form_data=dict(user), editing=True, user_id=id, permission_choices=PERMISSION_LABELS)


def toggle_user(id):
    with get_db() as conn:
        user = conn.execute('SELECT id,role,is_active FROM users WHERE id=?', (id,)).fetchone()
        if not user:
            flash('کاربر پیدا نشد.', 'danger')
            return redirect(url_for('users'))
        if user['id'] == session.get('user_id'):
            flash('نمی‌توانید دسترسی حساب جاری خود را قطع کنید.', 'danger')
            return redirect(url_for('users'))
        if user['role'] == 'admin' and user['is_active']:
            active_admins = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND is_active=1").fetchone()['n']
            if active_admins <= 1:
                flash('حداقل یک مدیر سیستم باید فعال بماند.', 'danger')
                return redirect(url_for('users'))
        new_value = 0 if user['is_active'] else 1
        auto_backup()
        conn.execute('UPDATE users SET is_active=? WHERE id=?', (new_value, id))
        conn.commit()
    audit(session.get('user_id'), 'toggle_user', 'user', id, str(new_value))
    flash('دسترسی کاربر ' + ('فعال شد.' if new_value else 'غیرفعال شد.'), 'success')
    return redirect(url_for('users'))


def delete_user(id):
    auto_backup()
    with get_db() as conn:
        user = conn.execute('SELECT id,role FROM users WHERE id=?', (id,)).fetchone()
        if not user or user['id'] == session.get('user_id'):
            flash('حذف این کاربر مجاز نیست.', 'danger')
            return redirect(url_for('users'))
        if user['role'] == 'admin':
            count = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin'").fetchone()['n']
            if count <= 1:
                flash('آخرین مدیر سیستم حذف نمی‌شود؛ دسترسی آن را مدیریت کنید.', 'danger')
                return redirect(url_for('users'))
        conn.execute('DELETE FROM recovery_codes WHERE user_id=?', (id,))
        conn.execute('DELETE FROM users WHERE id=?', (id,))
        conn.commit()
    audit(session.get('user_id'), 'delete_user', 'user', id)
    flash('کاربر حذف شد.', 'success')
    return redirect(url_for('users'))


def reset_user_password(id):
    new_password = secrets.token_urlsafe(10)
    auto_backup()
    with get_db() as conn:
        user = conn.execute('SELECT personnel_number FROM users WHERE id=?', (id,)).fetchone()
        if not user:
            flash('کاربر پیدا نشد.', 'danger')
            return redirect(url_for('users'))
        conn.execute('UPDATE users SET password_hash=?, must_change_password=1 WHERE id=?', (generate_password_hash(new_password), id))
        conn.commit()
    audit(session.get('user_id'), 'reset_password', 'user', id)
    flash(f'رمز موقت کاربر {user["personnel_number"]}: {new_password} — آن را حضوری تحویل دهید.', 'info')
    return redirect(url_for('users'))


def generate_recovery_code(id):
    auto_backup()
    code = secrets.token_urlsafe(18)
    expires = (datetime.now() + timedelta(hours=24)).isoformat(timespec='seconds')
    with get_db() as conn:
        user = conn.execute('SELECT personnel_number FROM users WHERE id=?', (id,)).fetchone()
        if not user:
            flash('کاربر پیدا نشد.', 'danger')
            return redirect(url_for('users'))
        conn.execute('UPDATE recovery_codes SET used_at=datetime("now") WHERE user_id=? AND used_at IS NULL', (id,))
        conn.execute(
            'INSERT INTO recovery_codes(user_id,code_hash,created_at,expires_at,created_by) VALUES(?,?,?,?,?)',
            (id, generate_password_hash(code), datetime.now().isoformat(timespec='seconds'), expires, session.get('user_id')),
        )
        conn.commit()
    audit(session.get('user_id'), 'generate_recovery_code', 'user', id)
    flash(f'کد بازیابی یک‌بارمصرف برای {user["personnel_number"]}: {code} — فقط یک‌بار نمایش داده می‌شود.', 'warning')
    return redirect(url_for('users'))


def forgot_password():
    if request.method == 'POST':
        personnel_number = _clean(request.form.get('personnel_number'), 50)
        code = request.form.get('recovery_code', '').strip()
        new_password = request.form.get('new_password', '')
        repeat = request.form.get('repeat_password', '')
        if len(new_password) < 8 or new_password != repeat:
            flash('رمز جدید باید حداقل ۸ کاراکتر و تکرار آن یکسان باشد.', 'danger')
            return render_template('forgot_password.html', personnel_number=personnel_number)

        # The recovery flow is local, but it still needs protection against
        # repeated guessing on the school computer. Five attempts are allowed
        # per personnel number during a rolling fifteen-minute window.
        lookup_key = personnel_number or '__empty__'
        cutoff = (datetime.now() - timedelta(minutes=15)).isoformat(timespec='seconds')
        with get_db() as conn:
            conn.execute('DELETE FROM password_recovery_attempts WHERE attempted_at < ?', (cutoff,))
            attempts = conn.execute(
                'SELECT COUNT(*) AS n FROM password_recovery_attempts WHERE lookup_key=?', (lookup_key,)
            ).fetchone()['n']
            if attempts >= 5:
                conn.commit()
                flash('تعداد تلاش‌های بازیابی زیاد است. پانزده دقیقه بعد دوباره امتحان کنید.', 'danger')
                return render_template('forgot_password.html', personnel_number=personnel_number)
            conn.execute(
                'INSERT INTO password_recovery_attempts(lookup_key,attempted_at) VALUES(?,?)',
                (lookup_key, datetime.now().isoformat(timespec='seconds')),
            )
            user = conn.execute('SELECT * FROM users WHERE personnel_number=? AND is_active=1', (personnel_number,)).fetchone()
            recovery = None
            if user:
                recovery = conn.execute(
                    'SELECT * FROM recovery_codes WHERE user_id=? AND used_at IS NULL ORDER BY id DESC LIMIT 1',
                    (user['id'],),
                ).fetchone()
            valid = bool(user and recovery and check_password_hash(recovery['code_hash'], code))
            if valid and recovery['expires_at']:
                try:
                    valid = datetime.fromisoformat(recovery['expires_at']) >= datetime.now()
                except ValueError:
                    valid = False
            if not valid:
                conn.commit()
                flash('شماره پرسنلی یا کد بازیابی معتبر نیست یا منقضی شده است.', 'danger')
                return render_template('forgot_password.html', personnel_number=personnel_number)
            user_id = user['id']
            recovery_id = recovery['id']
            conn.execute('DELETE FROM password_recovery_attempts WHERE lookup_key=?', (lookup_key,))
            conn.commit()

        auto_backup()
        with get_db() as conn:
            conn.execute(
                'UPDATE users SET password_hash=?,must_change_password=1 WHERE id=?',
                (generate_password_hash(new_password), user_id),
            )
            conn.execute(
                'UPDATE recovery_codes SET used_at=? WHERE id=?',
                (datetime.now().isoformat(timespec='seconds'), recovery_id),
            )
            conn.commit()
        audit(user_id, 'offline_recovery', 'user', user_id)
        flash('رمز عبور با موفقیت و به‌صورت آفلاین بازنشانی شد.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')


def register(app):
    app.add_url_rule('/health', 'health', health)
    app.add_url_rule('/login', 'login', login, methods=['GET', 'POST'])
    app.add_url_rule('/logout', 'logout', logout, methods=['POST'])
    app.add_url_rule('/change-password', 'change_password', change_password, methods=['GET', 'POST'])
    app.add_url_rule('/forgot-password', 'forgot_password', forgot_password, methods=['GET', 'POST'])
    app.add_url_rule('/users', 'users', users)
    app.add_url_rule('/users/add', 'add_user', add_user, methods=['GET', 'POST'])
    app.add_url_rule('/users/<int:id>/edit', 'edit_user', edit_user, methods=['GET', 'POST'])
    app.add_url_rule('/users/<int:id>/toggle', 'toggle_user', toggle_user, methods=['POST'])
    app.add_url_rule('/users/<int:id>/delete', 'delete_user', delete_user, methods=['POST'])
    app.add_url_rule('/users/<int:id>/reset-password', 'reset_user_password', reset_user_password, methods=['POST'])
    app.add_url_rule('/users/<int:id>/recovery-code', 'generate_recovery_code', generate_recovery_code, methods=['POST'])
