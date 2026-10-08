from __future__ import annotations

import os
import re
import secrets
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from flask import current_app
from werkzeug.security import generate_password_hash


def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _database_path() -> str:
    root = _base_dir()
    return os.environ.get('DATABASE_PATH') or str(root / 'school.db')


@contextmanager
def get_db():
    path = current_app.config.get('DATABASE', _database_path())
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 30000')
    try:
        conn.execute('PRAGMA journal_mode = WAL')
        conn.execute('PRAGMA synchronous = NORMAL')
    except sqlite3.Error:
        pass
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row['name'] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')


def _normalise_legacy_attendance(conn: sqlite3.Connection) -> None:
    """Repair old attendance rows, reconcile legacy codes, and store Jalali dates.

    Older releases sometimes saved student codes without leading or embedded zeroes
    while foreign-key enforcement was disabled.  Rebuilding the current attendance
    rows in one pass lets the migration repair those records without violating the
    new foreign key constraint.
    """
    from .dates import gregorian_to_jalali, normalize_digits

    def canonical_digits(value: object) -> str:
        return re.sub(r'[^0-9]', '', normalize_digits(str(value or '').strip()))

    def normalise_date(value: object) -> str:
        date = normalize_digits(str(value or '').strip()).replace('.', '/').replace('-', '/')
        if re.fullmatch(r'\d{4}/\d{2}/\d{2}', date):
            year, month, day = map(int, date.split('/'))
            # A four-digit year beginning with 1 or 2 is treated as Gregorian.
            if year >= 1700:
                jy, jm, jd = gregorian_to_jalali(year, month, day)
                return f'{jy:04d}/{jm:02d}/{jd:02d}'
            return f'{year:04d}/{month:02d}/{day:02d}'
        return date

    student_codes = [str(row['code']) for row in conn.execute(
        "SELECT code FROM students WHERE code IS NOT NULL AND TRIM(code) <> ''"
    ).fetchall()]
    by_exact = {canonical_digits(code): code for code in student_codes}
    by_without_leading_zero: dict[str, list[str]] = {}
    by_without_all_zeroes: dict[str, list[str]] = {}
    for code in student_codes:
        digits = canonical_digits(code)
        by_without_leading_zero.setdefault(digits.lstrip('0') or '0', []).append(code)
        by_without_all_zeroes.setdefault(digits.replace('0', ''), []).append(code)

    def resolve_code(raw_code: object) -> str:
        digits = canonical_digits(raw_code)
        if not digits:
            return ''
        if digits in by_exact:
            return by_exact[digits]
        candidates = by_without_leading_zero.get(digits.lstrip('0') or '0', [])
        if len(candidates) == 1:
            return candidates[0]
        # Some very old imports dropped zeroes in the middle of the code.
        candidates = by_without_all_zeroes.get(digits.replace('0', ''), [])
        return candidates[0] if len(candidates) == 1 else ''

    current_rows = conn.execute(
        'SELECT student_code,date,status FROM attendance_students'
    ).fetchall()
    legacy_rows = []
    has_legacy_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='attendance'"
    ).fetchone()
    if has_legacy_table:
        legacy_rows = conn.execute('SELECT id AS _rowid,student_code,date,status FROM attendance').fetchall()

    # Rebuild the current table so previously invalid foreign-key rows are repaired
    # or safely discarded instead of aborting the complete database migration.
    merged: dict[tuple[str, str], str] = {}
    for row in current_rows:
        code = resolve_code(row['student_code'])
        date = normalise_date(row['date'])
        if code and date:
            merged.setdefault((code, date), row['status'] or 'ثبت نشده')
    for row in legacy_rows:
        code = resolve_code(row['student_code'])
        date = normalise_date(row['date'])
        if code and date:
            merged.setdefault((code, date), row['status'] or 'ثبت نشده')

    conn.execute('DELETE FROM attendance_students')
    conn.executemany(
        'INSERT INTO attendance_students(student_code,date,status) VALUES(?,?,?)',
        [(code, date, status) for (code, date), status in merged.items()],
    )

    # Keep the legacy table internally consistent too; it remains only for backward
    # compatibility with old backups and is not used by current reports.
    if has_legacy_table:
        for row in legacy_rows:
            code = resolve_code(row['student_code'])
            date = normalise_date(row['date'])
            if code and date:
                conn.execute('UPDATE attendance SET student_code=?,date=? WHERE id=?', (code, date, row['_rowid']))
            else:
                conn.execute('DELETE FROM attendance WHERE id=?', (row['_rowid'],))


def _migrate_legacy_payments(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, 'monthly_service')
    if 'paid' in columns:
        conn.execute("""
            UPDATE monthly_service
            SET paid_amount = CASE
                WHEN COALESCE(paid_amount, 0) = 0 THEN COALESCE(CAST(paid AS INTEGER), 0)
                ELSE paid_amount
            END
            WHERE paid IS NOT NULL
        """)
    if 'date' in columns:
        conn.execute("""
            UPDATE monthly_service
            SET payment_date = COALESCE(NULLIF(TRIM(payment_date), ''), date)
            WHERE date IS NOT NULL
        """)
    conn.execute("""
        UPDATE monthly_service
        SET status = CASE
            WHEN COALESCE(amount, 0) <= 0 THEN 'فاقد سرویس'
            WHEN COALESCE(paid_amount, 0) <= 0 THEN 'پرداخت نشده'
            WHEN COALESCE(paid_amount, 0) < COALESCE(amount, 0) THEN 'جزئی'
            ELSE 'کامل'
        END
        WHERE status IS NULL OR TRIM(status) = '' OR status = 'پرداخت نشده'
    """)
    from .dates import normalize_digits

    for row in conn.execute("SELECT id, year FROM monthly_service WHERE TRIM(COALESCE(year,'')) <> ''").fetchall():
        normalised = normalize_digits(str(row['year'])).strip()
        if normalised != str(row['year']):
            conn.execute('UPDATE monthly_service SET year=? WHERE id=?', (normalised, row['id']))


def _rebuild_monthly_service_numbers(conn: sqlite3.Connection) -> None:
    """Rebuild the legacy monthly-service table with real INTEGER money columns.

    Very old installations stored ``paid_amount`` as TEXT (and kept a legacy
    ``paid`` column).  Mixing TEXT and INTEGER made every SQL comparison and
    SUM behave incorrectly, so the table is rebuilt once with numeric columns.
    """
    from .dates import normalize_digits

    info = conn.execute('PRAGMA table_info(monthly_service)').fetchall()
    if not info:
        return
    types = {row['name']: (row['type'] or '').upper() for row in info}
    names = {row['name'] for row in info}
    if types.get('amount') == 'INTEGER' and types.get('paid_amount') == 'INTEGER':
        return

    rows = conn.execute('SELECT * FROM monthly_service').fetchall()

    def number(value) -> int:
        raw = normalize_digits(str(value if value is not None else '0'))
        raw = raw.replace(',', '').replace('٬', '').replace('،', '').strip()
        try:
            return int(raw or 0)
        except ValueError:
            return 0

    def pick(row, name, default=''):
        return row[name] if name in names else default

    conn.execute('ALTER TABLE monthly_service RENAME TO monthly_service_legacy')
    conn.execute('''
        CREATE TABLE monthly_service (
            id INTEGER PRIMARY KEY AUTOINCREMENT, student_code TEXT, year TEXT, month TEXT,
            service_type TEXT DEFAULT 'رفت و برگشت', amount INTEGER DEFAULT 0,
            paid_amount INTEGER DEFAULT 0, payment_date TEXT,
            status TEXT DEFAULT 'پرداخت نشده', description TEXT
        )''')
    for row in rows:
        paid = number(pick(row, 'paid_amount', 0)) if 'paid_amount' in names else 0
        if not paid and 'paid' in names:
            paid = number(pick(row, 'paid', 0))
        payment_date = str(pick(row, 'payment_date', '') or '') or str(pick(row, 'date', '') or '')
        status = str(pick(row, 'status', '') or '')
        if status.strip() not in ('کامل', 'جزئی', 'پرداخت نشده', 'فاقد سرویس'):
            status = ''
        conn.execute(
            '''INSERT INTO monthly_service(id,student_code,year,month,service_type,amount,paid_amount,payment_date,status,description)
               VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (row['id'], pick(row, 'student_code', ''), pick(row, 'year', ''), pick(row, 'month', ''),
             str(pick(row, 'service_type', '') or 'رفت و برگشت'), number(pick(row, 'amount', 0)), paid,
             payment_date, status, str(pick(row, 'description', '') or '')),
        )
    conn.execute('DROP TABLE monthly_service_legacy')
    conn.execute('''UPDATE monthly_service SET status = CASE
        WHEN amount<=0 THEN 'فاقد سرویس'
        WHEN paid_amount<=0 THEN 'پرداخت نشده'
        WHEN paid_amount<amount THEN 'جزئی'
        ELSE 'کامل' END''')


def _migrate_parent_phone_to_father(conn: sqlite3.Connection) -> None:
    """Move the retired general parent phone into the father's phone field.

    The old value is never silently discarded. Empty father-phone fields receive it;
    conflicting values are kept together and recorded in a small migration log.
    """
    rows = conn.execute(
        """SELECT id,code,parent_phone,father_phone FROM students
           WHERE TRIM(COALESCE(parent_phone,'')) <> ''"""
    ).fetchall()
    for row in rows:
        old_phone = str(row['parent_phone'] or '').strip()
        father_phone = str(row['father_phone'] or '').strip()
        if not father_phone:
            new_phone = old_phone
        elif father_phone == old_phone or old_phone in father_phone.split(' / '):
            new_phone = father_phone
        else:
            new_phone = f'{father_phone} / {old_phone}'
            conn.execute(
                '''INSERT INTO parent_phone_migration_conflicts
                   (student_id,student_code,previous_parent_phone,existing_father_phone,migrated_at)
                   VALUES(?,?,?,?,datetime('now'))''',
                (row['id'], row['code'] or '', old_phone, father_phone),
            )
        conn.execute("UPDATE students SET father_phone=?,parent_phone='' WHERE id=?", (new_phone, row['id']))


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS student_custom_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_key TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL,
                field_type TEXT NOT NULL DEFAULT 'text',
                options_json TEXT DEFAULT '[]',
                section_label TEXT DEFAULT 'اطلاعات تکمیلی',
                required INTEGER NOT NULL DEFAULT 0,
                show_to_teacher INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 100,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS student_custom_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                field_id INTEGER NOT NULL,
                value TEXT DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE(student_id, field_id),
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY(field_id) REFERENCES student_custom_fields(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_student_custom_values_student ON student_custom_values(student_id);
            CREATE INDEX IF NOT EXISTS idx_student_custom_values_field ON student_custom_values(field_id);
            CREATE TABLE IF NOT EXISTS student_siblings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                sibling_type TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                age TEXT DEFAULT '',
                education TEXT DEFAULT '',
                marital_status TEXT DEFAULT '',
                job TEXT DEFAULT '',
                physical_status TEXT DEFAULT '',
                mental_status TEXT DEFAULT '',
                kinship TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_student_siblings_student ON student_siblings(student_id);
            CREATE TABLE IF NOT EXISTS parent_phone_migration_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                student_code TEXT,
                previous_parent_phone TEXT NOT NULL,
                existing_father_phone TEXT NOT NULL,
                migrated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT, last_name TEXT, code TEXT UNIQUE, birth_date TEXT,
                grade TEXT, class_name TEXT, sida_class TEXT, parent_phone TEXT,
                father_phone TEXT, mother_phone TEXT, father_name TEXT, father_code TEXT,
                mother_name TEXT, mother_last_name TEXT DEFAULT '', mother_code TEXT, address TEXT, status TEXT DEFAULT 'فعال',
                father_physical_status TEXT DEFAULT '', father_mental_status TEXT DEFAULT '',
                mother_physical_status TEXT DEFAULT '', mother_mental_status TEXT DEFAULT '',
                assessment_result TEXT DEFAULT '', disability_type TEXT DEFAULT '',
                teacher_code TEXT, admission_year TEXT, admission_type TEXT, religion TEXT,
                insurance_type TEXT, sisters_count TEXT, brothers_count TEXT,
                postal_code TEXT DEFAULT '', economic_decile TEXT DEFAULT '', medications TEXT,
                father_job TEXT, father_education TEXT, mother_job TEXT, mother_education TEXT,
                repeat_grade_1 TEXT, repeat_grade_2 TEXT, repeat_grade_3 TEXT,
                repeat_grade_4 TEXT, repeat_grade_5 TEXT, repeat_grade_6 TEXT,
                license_years TEXT DEFAULT '', child_order INTEGER DEFAULT 0,
                diseases TEXT DEFAULT '', vaccinations_complete INTEGER DEFAULT 0,
                drug_allergy INTEGER DEFAULT 0, behavioral_traits TEXT DEFAULT '',
                parents_alive TEXT DEFAULT '', parents_separated INTEGER DEFAULT 0,
                child_lives_with TEXT DEFAULT '', parents_related INTEGER DEFAULT 0,
                martyr_quota INTEGER DEFAULT 0, financial_status TEXT DEFAULT '',
                father_birth_date TEXT DEFAULT '', father_id_serial TEXT DEFAULT '',
                father_id_serial_letter TEXT DEFAULT '', father_id_issue_place TEXT DEFAULT '',
                mother_birth_date TEXT DEFAULT '', mother_id_serial TEXT DEFAULT '',
                mother_id_serial_letter TEXT DEFAULT '', mother_id_issue_place TEXT DEFAULT '',
                student_id_serial TEXT DEFAULT '', student_id_serial_letter TEXT DEFAULT '',
                student_id_issue_place TEXT DEFAULT '', is_emdad_member INTEGER DEFAULT 0,
                is_behzisti_member INTEGER DEFAULT 0, entry_year_grade_prep TEXT DEFAULT '', entry_year_grade_advanced TEXT DEFAULT '', entry_year_grade_first1 TEXT DEFAULT '', entry_year_grade_first2 TEXT DEFAULT '', entry_year_grade_first3 TEXT DEFAULT '', entry_year_grade_1 TEXT DEFAULT '',
                entry_year_grade_2 TEXT DEFAULT '', entry_year_grade_3 TEXT DEFAULT '',
                entry_year_grade_4 TEXT DEFAULT '', entry_year_grade_5 TEXT DEFAULT '',
                entry_year_grade_6 TEXT DEFAULT '', photo TEXT DEFAULT '',
                student_birth_place TEXT DEFAULT '', gender TEXT DEFAULT '',
                student_id_issue_date TEXT DEFAULT '', father_birth_place TEXT DEFAULT '',
                 father_id_issue_date TEXT DEFAULT '', mother_birth_place TEXT DEFAULT '',
                 mother_id_issue_date TEXT DEFAULT '', service_fee INTEGER DEFAULT 0,
                 bank_name TEXT DEFAULT '', iban TEXT DEFAULT '',
                 service_destination_id INTEGER DEFAULT NULL
            );
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT, last_name TEXT, code TEXT UNIQUE, subject TEXT,
                class_name TEXT, sida_class TEXT DEFAULT '', national_id TEXT DEFAULT '',
                phone TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS service_drivers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_name TEXT UNIQUE NOT NULL,
                driver_name TEXT NOT NULL DEFAULT '',
                phone TEXT DEFAULT '',
                vehicle TEXT DEFAULT '',
                plate TEXT DEFAULT ''
            );
             CREATE TABLE IF NOT EXISTS service_driver_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                vehicle TEXT DEFAULT '',
                plate TEXT DEFAULT '',
                 created_at TEXT NOT NULL DEFAULT (datetime('now'))
             );
             CREATE TABLE IF NOT EXISTS service_driver_destinations (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 driver_id INTEGER NOT NULL,
                 destination TEXT NOT NULL DEFAULT '',
                 created_at TEXT NOT NULL DEFAULT (datetime('now')),
                 FOREIGN KEY(driver_id) REFERENCES service_driver_registry(id) ON DELETE CASCADE
             );
            CREATE TABLE IF NOT EXISTS attendance_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT, student_code TEXT, date TEXT, status TEXT
            );
            CREATE TABLE IF NOT EXISTS attendance_teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_code TEXT, date TEXT,
                status TEXT, late_duration INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS discipline (
                id INTEGER PRIMARY KEY AUTOINCREMENT, target_type TEXT, target_code TEXT,
                date TEXT, type TEXT, points INTEGER, description TEXT
            );
            CREATE TABLE IF NOT EXISTS class_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_code TEXT, class_name TEXT,
                date TEXT, report TEXT
            );
            CREATE TABLE IF NOT EXISTS teacher_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_code TEXT, student_code TEXT,
                date TEXT, report TEXT
            );
            CREATE TABLE IF NOT EXISTS financial_help (
                id INTEGER PRIMARY KEY AUTOINCREMENT, student_code TEXT, amount INTEGER,
                date TEXT, description TEXT
            );
            CREATE TABLE IF NOT EXISTS monthly_service (
                id INTEGER PRIMARY KEY AUTOINCREMENT, student_code TEXT, year TEXT, month TEXT,
                service_type TEXT DEFAULT 'رفت و برگشت', amount INTEGER DEFAULT 0,
                paid_amount INTEGER DEFAULT 0, payment_date TEXT,
                status TEXT DEFAULT 'پرداخت نشده', description TEXT
            );
            CREATE TABLE IF NOT EXISTS support_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_code TEXT NOT NULL,
                provider_role TEXT NOT NULL,
                provider_name TEXT DEFAULT '',
                provider_phone TEXT DEFAULT '',
                provider_org TEXT DEFAULT '',
                planned_date TEXT DEFAULT '',
                topic TEXT NOT NULL,
                planned_sessions INTEGER NOT NULL DEFAULT 0,
                completed_sessions INTEGER NOT NULL DEFAULT 0,
                cost INTEGER NOT NULL DEFAULT 0,
                outcome TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'برنامه‌ریزی‌شده',
                notes TEXT DEFAULT '',
                document_path TEXT DEFAULT '',
                document_name TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_support_plans_student ON support_plans(student_code);
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY, value TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, date TEXT, time TEXT,
                description TEXT, type TEXT, priority TEXT DEFAULT 'عادی'
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                due_date TEXT NOT NULL,
                due_time TEXT DEFAULT '',
                priority TEXT DEFAULT 'عادی',
                status TEXT DEFAULT 'باز',
                alarm_enabled INTEGER NOT NULL DEFAULT 1,
                alarm_minutes INTEGER NOT NULL DEFAULT 30,
                category TEXT DEFAULT 'کار',
                created_by INTEGER,
                completed_at TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                personnel_number TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','manager','teacher')),
                is_active INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 1,
                teacher_code TEXT, national_id TEXT DEFAULT '', phone TEXT DEFAULT '',
                permissions TEXT DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recovery_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                code_hash TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT,
                used_at TEXT, created_by INTEGER, FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS password_recovery_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lookup_key TEXT NOT NULL,
                attempted_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, actor_user_id INTEGER,
                action TEXT NOT NULL, entity_type TEXT, entity_id TEXT,
                details TEXT, created_at TEXT NOT NULL
            );
            """
        )

        for table, column, definition in (
            ('students', 'repeat_grade_prep', "TEXT DEFAULT ''"), ('students', 'repeat_grade_advanced', "TEXT DEFAULT ''"), ('students', 'repeat_grade_first1', "TEXT DEFAULT ''"), ('students', 'repeat_grade_first2', "TEXT DEFAULT ''"), ('students', 'repeat_grade_first3', "TEXT DEFAULT ''"), ('students', 'entry_year_grade_prep', "TEXT DEFAULT ''"), ('students', 'entry_year_grade_advanced', "TEXT DEFAULT ''"), ('students', 'entry_year_grade_first1', "TEXT DEFAULT ''"), ('students', 'entry_year_grade_first2', "TEXT DEFAULT ''"), ('students', 'entry_year_grade_first3', "TEXT DEFAULT ''"), ('students', 'sida_class', "TEXT DEFAULT ''"), ('students', 'teacher_code', "TEXT DEFAULT ''"),
             ('students', 'status', "TEXT DEFAULT 'فعال'"), ('students', 'service_fee', 'INTEGER DEFAULT 0'), ('students', 'service_driver_id', 'INTEGER DEFAULT NULL'), ('students', 'service_destination_id', 'INTEGER DEFAULT NULL'), ('students', 'bank_name', "TEXT DEFAULT ''"), ('students', 'iban', "TEXT DEFAULT ''"),
            ('students', 'mother_last_name', "TEXT DEFAULT ''"), ('students', 'father_physical_status', "TEXT DEFAULT ''"), ('students', 'father_mental_status', "TEXT DEFAULT ''"), ('students', 'mother_physical_status', "TEXT DEFAULT ''"), ('students', 'mother_mental_status', "TEXT DEFAULT ''"), ('students', 'assessment_result', "TEXT DEFAULT ''"), ('students', 'disability_type', "TEXT DEFAULT ''"),
            ('teachers', 'sida_class', "TEXT DEFAULT ''"), ('teachers', 'national_id', "TEXT DEFAULT ''"),            ('teachers', 'phone', "TEXT DEFAULT ''"), ('users', 'national_id', "TEXT DEFAULT ''"),
            ('users', 'phone', "TEXT DEFAULT ''"), ('users', 'permissions', "TEXT DEFAULT ''"),
            ('events', 'priority', "TEXT DEFAULT 'عادی'"), ('attendance_teachers', 'late_duration', 'INTEGER DEFAULT 0'),
            ('monthly_service', 'service_type', "TEXT DEFAULT 'رفت و برگشت'"),
            ('monthly_service', 'paid_amount', 'INTEGER DEFAULT 0'), ('monthly_service', 'payment_date', "TEXT DEFAULT ''"),
            ('monthly_service', 'status', "TEXT DEFAULT 'پرداخت نشده'"), ('monthly_service', 'description', "TEXT DEFAULT ''"),
            ('support_plans', 'referral_type', "TEXT DEFAULT 'داخل مدرسه'"), ('support_plans', 'referral_destination', "TEXT DEFAULT ''"), ('support_plans', 'session_date', "TEXT DEFAULT ''"), ('support_plans', 'session_start_time', "TEXT DEFAULT ''"), ('support_plans', 'session_end_time', "TEXT DEFAULT ''"),
            ('support_plans', 'referral_type', "TEXT DEFAULT 'داخل مدرسه'"), ('support_plans', 'referral_destination', "TEXT DEFAULT ''"), ('support_plans', 'session_date', "TEXT DEFAULT ''"), ('support_plans', 'session_start_time', "TEXT DEFAULT ''"), ('support_plans', 'session_end_time', "TEXT DEFAULT ''"),
        ):
            _ensure_column(conn, table, column, definition)

        # Move the previous class-bound driver records into the independent
        # driver registry and preserve matching student assignments.
        conn.execute('''INSERT INTO service_driver_registry(driver_name,phone,vehicle,plate)
                        SELECT old.driver_name,old.phone,old.vehicle,old.plate
                        FROM service_drivers old
                        WHERE TRIM(COALESCE(old.driver_name,''))!=''
                          AND NOT EXISTS (
                              SELECT 1 FROM service_driver_registry current
                              WHERE current.driver_name=old.driver_name
                                AND current.phone=old.phone
                          )''')
        conn.execute('''UPDATE students
                        SET service_driver_id=(
                            SELECT current.id
                            FROM service_drivers old
                            JOIN service_driver_registry current
                              ON current.driver_name=old.driver_name AND current.phone=old.phone
                            WHERE TRIM(COALESCE(old.class_name,''))=TRIM(COALESCE(students.class_name,''))
                            LIMIT 1
                        )
                        WHERE service_driver_id IS NULL
                          AND TRIM(COALESCE(class_name,''))!='' ''')

        conn.execute('CREATE INDEX IF NOT EXISTS idx_students_service_destination ON students(service_destination_id)')
        # Preserve the old behaviour for drivers with exactly one destination;
        # students assigned to multi-destination drivers must be selected explicitly.
        conn.execute('''UPDATE students
                        SET service_destination_id=(
                            SELECT MIN(dest.id)
                            FROM service_driver_destinations dest
                            WHERE dest.driver_id=students.service_driver_id
                        )
                        WHERE service_driver_id IS NOT NULL
                          AND service_destination_id IS NULL
                          AND (SELECT COUNT(*) FROM service_driver_destinations dest
                               WHERE dest.driver_id=students.service_driver_id)=1''')

        # The former general parent-phone field is retired; migrate it once before
        # clearing it from the records. create_app() makes the pre-change backup.
        _migrate_parent_phone_to_father(conn)
        # Preserve the previous single first-grade fields in the new first-grade-one fields.
        conn.execute("UPDATE students SET repeat_grade_first1=COALESCE(NULLIF(TRIM(repeat_grade_first1),''),COALESCE(repeat_grade_1,'')), entry_year_grade_first1=COALESCE(NULLIF(TRIM(entry_year_grade_first1),''),COALESCE(entry_year_grade_1,''))")
        # Repair and migrate old records before creating unique attendance indexes.
        _normalise_legacy_attendance(conn)
        _rebuild_monthly_service_numbers(conn)
        _migrate_legacy_payments(conn)
        conn.execute("UPDATE students SET teacher_code='' WHERE TRIM(COALESCE(teacher_code,''))='فعال'")
        conn.execute("DELETE FROM attendance_students WHERE id NOT IN (SELECT MAX(id) FROM attendance_students GROUP BY student_code,date)")
        conn.execute("DELETE FROM attendance_teachers WHERE id NOT IN (SELECT MAX(id) FROM attendance_teachers GROUP BY teacher_code,date)")
        conn.execute("DELETE FROM monthly_service WHERE TRIM(COALESCE(student_code,'')) <> '' AND id NOT IN (SELECT MAX(id) FROM monthly_service WHERE TRIM(COALESCE(student_code,'')) <> '' GROUP BY student_code,year,month)")
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_students_teacher_code ON students(teacher_code);
            CREATE INDEX IF NOT EXISTS idx_attendance_students_date ON attendance_students(date);
            CREATE INDEX IF NOT EXISTS idx_attendance_students_student_date ON attendance_students(student_code,date);
            CREATE INDEX IF NOT EXISTS idx_attendance_teachers_date ON attendance_teachers(date);
            CREATE INDEX IF NOT EXISTS idx_attendance_teachers_teacher_date ON attendance_teachers(teacher_code,date);
            CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_students_person_date ON attendance_students(student_code,date);
            CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_teachers_person_date ON attendance_teachers(teacher_code,date);
            CREATE INDEX IF NOT EXISTS idx_monthly_service_year_month ON monthly_service(year,month);
            CREATE INDEX IF NOT EXISTS idx_monthly_service_student ON monthly_service(student_code);
            CREATE INDEX IF NOT EXISTS idx_monthly_service_status ON monthly_service(status);
            CREATE UNIQUE INDEX IF NOT EXISTS uq_monthly_service_person_period ON monthly_service(student_code,year,month) WHERE TRIM(COALESCE(student_code,'')) <> '' AND TRIM(COALESCE(year,'')) <> '' AND TRIM(COALESCE(month,'')) <> '';
            CREATE INDEX IF NOT EXISTS idx_recovery_attempts_key_time ON password_recovery_attempts(lookup_key,attempted_at);
            CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
            """
        )

        teacher_rows = conn.execute(
            "SELECT first_name,last_name,code,national_id,phone FROM teachers WHERE code IS NOT NULL AND TRIM(code)<>''"
        ).fetchall()
        generated: list[str] = []
        for teacher in teacher_rows:
            user = conn.execute('SELECT id FROM users WHERE personnel_number=?', (teacher['code'],)).fetchone()
            if not user:
                temporary = secrets.token_urlsafe(10)
                conn.execute(
                    """INSERT INTO users(personnel_number,full_name,password_hash,role,teacher_code,national_id,phone,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (teacher['code'], f"{teacher['first_name'] or ''} {teacher['last_name'] or ''}".strip(),
                     generate_password_hash(temporary), 'teacher', teacher['code'], teacher['national_id'] or '',
                     teacher['phone'] or '', datetime.now().isoformat()),
                )
                generated.append(f"teacher | {teacher['code']} | {temporary}")
            else:
                conn.execute(
                    "UPDATE users SET teacher_code=?, national_id=COALESCE(NULLIF(?,''),national_id), "
                    "phone=COALESCE(NULLIF(?,''),phone) WHERE id=?",
                    (teacher['code'], teacher['national_id'] or '', teacher['phone'] or '', user['id']),
                )

        if not conn.execute("SELECT id FROM users WHERE role='admin'").fetchone():
            temporary = secrets.token_urlsafe(12)
            admin_code = os.environ.get('ADMIN_PERSONNEL_NUMBER', 'admin')
            conn.execute(
                "INSERT INTO users(personnel_number,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                (admin_code, 'مدیر سیستم', generate_password_hash(temporary), 'admin', datetime.now().isoformat()),
            )
            generated.append(f'admin | {admin_code} | {temporary}')

        credentials_path = _base_dir() / 'initial_credentials.txt'
        if generated and not credentials_path.exists():
            credentials_path.write_text(
                'رمزهای اولیه — پس از اولین ورود حتماً تغییر دهید\n' + '\n'.join(generated) + '\n', encoding='utf-8'
            )
        conn.commit()


def auto_backup() -> None:
    try:
        database = Path(current_app.config.get('DATABASE', _database_path()))
        backup_dir = Path(current_app.config.get('BACKUP_DIR', _base_dir() / 'backups'))
    except RuntimeError:
        database = Path(_database_path())
        backup_dir = _base_dir() / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    if database.exists():
        target = backup_dir / f"school_{datetime.now():%Y-%m-%d_%H%M%S_%f}.db"
        shutil.copy2(database, target)
