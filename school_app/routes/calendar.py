from __future__ import annotations

from datetime import datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from ..database import auto_backup, get_db
from ..dates import get_today_jalali, gregorian_to_jalali, jalali_to_gregorian, normalize_jalali_date, today_string
from ..security import audit
from ..occasions import client_map as occasion_client_map, stats as occasion_stats, today_items as occasion_today_items

TASK_PRIORITIES = {'کم', 'عادی', 'مهم', 'فوری'}
TASK_CATEGORIES = {'کار', 'جلسه', 'پیگیری', 'مالی', 'آموزشی', 'سایر'}
TASK_STATUSES = {'باز', 'در حال انجام', 'انجام‌شده', 'لغو‌شده'}
ALARM_MINUTES_ALLOWED = {0, 5, 10, 15, 30, 60, 120, 1440}


def _jalali_after(days: int) -> str:
    day = datetime.now() + timedelta(days=days)
    y, m, d = gregorian_to_jalali(day.year, day.month, day.day)
    return f'{y:04d}/{m:02d}/{d:02d}'


def _date_or_error(value: str) -> str:
    return normalize_jalali_date(value, required=True)


def _normalize_priority(value: str) -> str:
    priority = (value or 'عادی').strip()
    return priority if priority in TASK_PRIORITIES else 'عادی'


def _normalize_category(value: str) -> str:
    category = (value or 'کار').strip()[:40]
    return category if category in TASK_CATEGORIES else 'سایر'


def _normalize_status(value: str) -> str:
    status = (value or 'باز').strip()
    return status if status in TASK_STATUSES else 'باز'


def _normalize_alarm_minutes(value: str | int | None) -> int:
    try:
        minutes = int(value or 30)
    except (TypeError, ValueError):
        minutes = 30
    return minutes if minutes in ALARM_MINUTES_ALLOWED else 30


def _task_datetime(due_date: str, due_time: str | None) -> datetime | None:
    try:
        jy, jm, jd = (int(x) for x in due_date.split('/'))
        gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
        clock = (due_time or '00:00').strip().replace('：', ':')
        parts = clock.split(':')
        hh = int(parts[0]) if parts and parts[0] != '' else 0
        mm = int(parts[1]) if len(parts) > 1 and parts[1] != '' else 0
        return datetime(gy, gm, gd, hh, mm)
    except (ValueError, TypeError, IndexError, AttributeError):
        return None


def _enrich_task(row) -> dict:
    item = dict(row)
    due_at = _task_datetime(item.get('due_date') or '', item.get('due_time'))
    alarm_minutes = int(item.get('alarm_minutes') or 0)
    alarm_enabled = int(item.get('alarm_enabled') or 0) == 1
    status = item.get('status') or 'باز'
    open_status = status not in {'انجام‌شده', 'لغو‌شده'}
    item['open'] = open_status
    item['due_at_iso'] = due_at.strftime('%Y-%m-%dT%H:%M:%S') if due_at else ''
    if due_at and alarm_enabled:
        alarm_at = due_at - timedelta(minutes=alarm_minutes)
        item['alarm_at_iso'] = alarm_at.strftime('%Y-%m-%dT%H:%M:%S')
    else:
        item['alarm_at_iso'] = ''
    item['alarm_active'] = bool(open_status and alarm_enabled and due_at)
    item['urgent'] = (item.get('priority') or 'عادی') == 'فوری'
    item['important'] = (item.get('priority') or 'عادی') in {'فوری', 'مهم'}
    item['time_label'] = item.get('due_time') or 'بدون ساعت'
    item['alarm_label'] = (
        f'{alarm_minutes} دقیقه قبل' if alarm_minutes else 'در موعد'
    ) if alarm_enabled else 'خاموش'
    return item


def _parse_task_form(form) -> dict:
    title = form.get('title', '').strip()[:150]
    if not title:
        raise ValueError('عنوان کار الزامی است.')
    due_date = _date_or_error(form.get('due_date', '') or form.get('date', ''))
    due_time = form.get('due_time', form.get('time', '')).strip()[:20]
    priority = _normalize_priority(form.get('priority', 'عادی'))
    category = _normalize_category(form.get('category', 'کار'))
    status = _normalize_status(form.get('status', 'باز'))
    alarm_enabled = 1 if form.get('alarm_enabled') in {'1', 'on', 'true', 'yes'} else 0
    alarm_minutes = _normalize_alarm_minutes(form.get('alarm_minutes'))
    description = form.get('description', '').strip()[:500]
    return {
        'title': title,
        'description': description,
        'due_date': due_date,
        'due_time': due_time,
        'priority': priority,
        'category': category,
        'status': status,
        'alarm_enabled': alarm_enabled,
        'alarm_minutes': alarm_minutes,
    }


def calendar():
    if request.method == 'POST':
        form_kind = (request.form.get('form_kind') or 'event').strip()
        try:
            if form_kind == 'task':
                data = _parse_task_form(request.form)
                auto_backup()
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                with get_db() as conn:
                    conn.execute(
                        '''INSERT INTO tasks(
                            title, description, due_date, due_time, priority, status,
                            alarm_enabled, alarm_minutes, category, created_by, completed_at, created_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (
                            data['title'], data['description'], data['due_date'], data['due_time'],
                            data['priority'], data['status'], data['alarm_enabled'], data['alarm_minutes'],
                            data['category'], session.get('user_id'),
                            now if data['status'] == 'انجام‌شده' else '',
                            now,
                        ),
                    )
                    conn.commit()
                audit(session.get('user_id'), 'create_task', 'task', data['title'])
                flash('کار / یادآور با موفقیت ثبت شد.', 'success')
            else:
                date = _date_or_error(request.form.get('date', ''))
                title = request.form.get('title', '').strip()[:150]
                if not title:
                    raise ValueError('عنوان رویداد الزامی است.')
                priority = _normalize_priority(request.form.get('priority', 'عادی'))
                auto_backup()
                with get_db() as conn:
                    conn.execute(
                        '''INSERT INTO events(title,date,time,description,type,priority) VALUES(?,?,?,?,?,?)''',
                        (
                            title,
                            date,
                            request.form.get('time', '').strip()[:20],
                            request.form.get('description', '').strip()[:500],
                            request.form.get('type', 'سایر').strip()[:40],
                            priority,
                        ),
                    )
                    conn.commit()
                audit(session.get('user_id'), 'create_event', 'event', title)
                flash('رویداد با موفقیت ثبت شد.', 'success')
        except ValueError as exc:
            flash(str(exc), 'danger')
        except Exception:
            flash('ثبت انجام نشد.', 'danger')
        return redirect(url_for('calendar'))

    today = today_string()
    tomorrow = _jalali_after(1)
    week_end = _jalali_after(7)
    with get_db() as conn:
        events = conn.execute('SELECT * FROM events ORDER BY date ASC,time ASC,id DESC').fetchall()
        today_events = conn.execute(
            'SELECT * FROM events WHERE date=? ORDER BY priority DESC,time,id', (today,)
        ).fetchall()
        tomorrow_events = conn.execute(
            'SELECT * FROM events WHERE date=? ORDER BY priority DESC,time,id', (tomorrow,)
        ).fetchall()
        upcoming = conn.execute(
            'SELECT * FROM events WHERE date>? AND date<=? ORDER BY date,time,id', (today, week_end)
        ).fetchall()
        overdue = conn.execute(
            'SELECT * FROM events WHERE date<? ORDER BY date DESC,time DESC,id DESC LIMIT 20', (today,)
        ).fetchall()
        reminders = list(today_events) + list(tomorrow_events)

        task_rows = conn.execute(
            "SELECT * FROM tasks ORDER BY CASE status WHEN 'انجام‌شده' THEN 2 WHEN 'لغو‌شده' THEN 3 ELSE 0 END, due_date ASC, due_time ASC, id DESC"
        ).fetchall()
        open_tasks = [_enrich_task(r) for r in task_rows if (r['status'] or 'باز') not in {'انجام‌شده', 'لغو‌شده'}]
        done_tasks = [_enrich_task(r) for r in task_rows if (r['status'] or '') == 'انجام‌شده'][:30]
        today_tasks = [t for t in open_tasks if t.get('due_date') == today]
        tomorrow_tasks = [t for t in open_tasks if t.get('due_date') == tomorrow]
        upcoming_tasks = [t for t in open_tasks if today < (t.get('due_date') or '') <= week_end]
        overdue_tasks = [t for t in open_tasks if (t.get('due_date') or '') < today]
        alarm_tasks = [t for t in open_tasks if t.get('alarm_active')]

    jy, jm, jd = get_today_jalali()
    return render_template(
        'calendar.html',
        events=events,
        reminders=reminders,
        today_events=today_events,
        tomorrow_events=tomorrow_events,
        upcoming=upcoming,
        overdue=overdue,
        tasks=open_tasks + done_tasks,
        open_tasks=open_tasks,
        done_tasks=done_tasks,
        today_tasks=today_tasks,
        tomorrow_tasks=tomorrow_tasks,
        upcoming_tasks=upcoming_tasks,
        overdue_tasks=overdue_tasks,
        alarm_tasks=alarm_tasks,
        jalali_year=jy,
        jalali_month=jm,
        jalali_day=jd,
        today_string=today,
        task_categories=sorted(TASK_CATEGORIES),
        alarm_minute_options=sorted(ALARM_MINUTES_ALLOWED),
        occasion_data=occasion_client_map(),
        occasion_today=occasion_today_items(),
        occasion_stats=occasion_stats(),
    )


def edit_event(id):
    with get_db() as conn:
        event = conn.execute('SELECT * FROM events WHERE id=?', (id,)).fetchone()
    if not event:
        flash('رویداد پیدا نشد.', 'danger')
        return redirect(url_for('calendar'))
    if request.method == 'POST':
        try:
            date = _date_or_error(request.form.get('date', ''))
            title = request.form.get('title', '').strip()[:150]
            priority = _normalize_priority(request.form.get('priority', 'عادی'))
            if not title:
                raise ValueError('عنوان رویداد الزامی است.')
            auto_backup()
            with get_db() as conn:
                cursor = conn.execute(
                    '''UPDATE events SET title=?,date=?,time=?,description=?,type=?,priority=? WHERE id=?''',
                    (
                        title,
                        date,
                        request.form.get('time', '').strip()[:20],
                        request.form.get('description', '').strip()[:500],
                        request.form.get('type', 'سایر').strip()[:40],
                        priority,
                        id,
                    ),
                )
                conn.commit()
            if not cursor.rowcount:
                flash('رویداد پیدا نشد.', 'warning')
                return redirect(url_for('calendar'))
            audit(session.get('user_id'), 'edit_event', 'event', id)
            flash('رویداد ویرایش شد.', 'success')
            return redirect(url_for('calendar'))
        except ValueError as exc:
            flash(str(exc), 'danger')
    return render_template('edit_event.html', event=event)


def delete_event(id):
    auto_backup()
    with get_db() as conn:
        cursor = conn.execute('DELETE FROM events WHERE id=?', (id,))
        conn.commit()
    if cursor.rowcount:
        audit(session.get('user_id'), 'delete_event', 'event', id)
        flash('رویداد حذف شد.', 'success')
    else:
        flash('رویداد پیدا نشد.', 'warning')
    return redirect(url_for('calendar'))


def edit_task(id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM tasks WHERE id=?', (id,)).fetchone()
    if not row:
        flash('کار پیدا نشد.', 'danger')
        return redirect(url_for('calendar'))
    task = _enrich_task(row)
    if request.method == 'POST':
        try:
            data = _parse_task_form(request.form)
            completed_at = row['completed_at'] or ''
            if data['status'] == 'انجام‌شده' and (row['status'] or '') != 'انجام‌شده':
                completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elif data['status'] != 'انجام‌شده':
                completed_at = ''
            auto_backup()
            with get_db() as conn:
                cursor = conn.execute(
                    '''UPDATE tasks SET title=?, description=?, due_date=?, due_time=?, priority=?,
                       status=?, alarm_enabled=?, alarm_minutes=?, category=?, completed_at=? WHERE id=?''',
                    (
                        data['title'], data['description'], data['due_date'], data['due_time'],
                        data['priority'], data['status'], data['alarm_enabled'], data['alarm_minutes'],
                        data['category'], completed_at, id,
                    ),
                )
                conn.commit()
            if not cursor.rowcount:
                flash('کار پیدا نشد.', 'warning')
                return redirect(url_for('calendar'))
            audit(session.get('user_id'), 'edit_task', 'task', id)
            flash('کار ویرایش شد.', 'success')
            return redirect(url_for('calendar'))
        except ValueError as exc:
            flash(str(exc), 'danger')
    return render_template(
        'edit_task.html',
        task=task,
        task_categories=sorted(TASK_CATEGORIES),
        alarm_minute_options=sorted(ALARM_MINUTES_ALLOWED),
        task_statuses=sorted(TASK_STATUSES),
    )


def toggle_task(id):
    auto_backup()
    with get_db() as conn:
        row = conn.execute('SELECT id, status FROM tasks WHERE id=?', (id,)).fetchone()
        if not row:
            flash('کار پیدا نشد.', 'warning')
            return redirect(url_for('calendar'))
        if (row['status'] or '') == 'انجام‌شده':
            new_status = 'باز'
            completed_at = ''
        else:
            new_status = 'انجام‌شده'
            completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute(
            'UPDATE tasks SET status=?, completed_at=? WHERE id=?',
            (new_status, completed_at, id),
        )
        conn.commit()
    audit(session.get('user_id'), 'toggle_task', 'task', f'{id}:{new_status}')
    flash('وضعیت کار به‌روز شد.', 'success')
    return redirect(url_for('calendar'))


def delete_task(id):
    auto_backup()
    with get_db() as conn:
        cursor = conn.execute('DELETE FROM tasks WHERE id=?', (id,))
        conn.commit()
    if cursor.rowcount:
        audit(session.get('user_id'), 'delete_task', 'task', id)
        flash('کار حذف شد.', 'success')
    else:
        flash('کار پیدا نشد.', 'warning')
    return redirect(url_for('calendar'))


def daily_digest():
    """End-of-day summary of today's, overdue and tomorrow's events and tasks."""
    today = today_string()
    tomorrow = _jalali_after(1)
    week_end = _jalali_after(7)
    with get_db() as conn:
        today_events = conn.execute(
            'SELECT title,time,priority,type FROM events WHERE date=? ORDER BY priority DESC,time,id', (today,)
        ).fetchall()
        tomorrow_events = conn.execute(
            'SELECT title,time,priority,type FROM events WHERE date=? ORDER BY priority DESC,time,id', (tomorrow,)
        ).fetchall()
        overdue_events = conn.execute(
            'SELECT title,date,time,priority,type FROM events WHERE date<? ORDER BY date,time,id', (today,)
        ).fetchall()
        today_tasks = conn.execute(
            "SELECT title,due_time,priority,category FROM tasks WHERE due_date=? AND status NOT IN ('انجام‌شده','لغو‌شده') ORDER BY priority DESC,due_time,id",
            (today,),
        ).fetchall()
        tomorrow_tasks = conn.execute(
            "SELECT title,due_time,priority,category FROM tasks WHERE due_date=? AND status NOT IN ('انجام‌شده','لغو‌شده') ORDER BY priority DESC,due_time,id",
            (tomorrow,),
        ).fetchall()
        overdue_tasks = conn.execute(
            "SELECT title,due_date,due_time,priority,category FROM tasks WHERE due_date<? AND status NOT IN ('انجام‌شده','لغو‌شده') ORDER BY due_date,due_time,id",
            (today,),
        ).fetchall()
        done_today = conn.execute(
            "SELECT title,completed_at FROM tasks WHERE status='انجام‌شده' AND completed_at LIKE ? ORDER BY completed_at",
            (datetime.now().strftime('%Y-%m-%d') + '%',),
        ).fetchall()

    data = {
        'date': today,
        'tomorrow': tomorrow,
        'events_today': [dict(r) for r in today_events],
        'tasks_today': [dict(r) for r in today_tasks],
        'events_tomorrow': [dict(r) for r in tomorrow_events],
        'tasks_tomorrow': [dict(r) for r in tomorrow_tasks],
        'events_overdue': [dict(r) for r in overdue_events],
        'tasks_overdue': [dict(r) for r in overdue_tasks],
        'tasks_done_today': [dict(r) for r in done_today],
    }
    if request.args.get('format') == 'json':
        return jsonify(data)
    return render_template('daily_digest.html', **data)


def register(app):
    app.add_url_rule('/calendar', 'calendar', calendar, methods=['GET', 'POST'])
    app.add_url_rule('/edit_event/<int:id>', 'edit_event', edit_event, methods=['GET', 'POST'])
    app.add_url_rule('/delete_event/<int:id>', 'delete_event', delete_event, methods=['POST'])
    app.add_url_rule('/edit_task/<int:id>', 'edit_task', edit_task, methods=['GET', 'POST'])
    app.add_url_rule('/toggle_task/<int:id>', 'toggle_task', toggle_task, methods=['POST'])
    app.add_url_rule('/delete_task/<int:id>', 'delete_task', delete_task, methods=['POST'])
    app.add_url_rule('/daily_digest', 'daily_digest', daily_digest, methods=['GET'])
