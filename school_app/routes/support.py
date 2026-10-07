from __future__ import annotations

import re
import uuid
from pathlib import Path

from flask import abort, current_app, flash, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from ..database import get_db
from ..dates import normalize_digits, normalize_jalali_date, today_string
from ..security import audit

_ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "jpg", "jpeg", "png"}
_ROLES = {"مشاور", "مددکار اجتماعی", "توانبخشی", "روان‌شناس", "روان‌پزشک", "گفتاردرمانگر", "کاردرمانگر", "سایر"}
_STATUSES = {"برنامه‌ریزی‌شده", "در حال پیگیری", "تکمیل‌شده", "متوقف‌شده"}
_REFERRAL_TYPES = {"داخل مدرسه", "خارج از مدرسه"}


def _text(value, limit=500):
    return str(value or "").strip()[:limit]


def _number(value, default=0):
    raw = normalize_digits(str(value or "")).replace(",", "").replace("٬", "").replace("،", "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        raise ValueError("عدد واردشده معتبر نیست.")


def _student_scope(conn, code):
    return conn.execute("SELECT id, code, first_name, last_name, grade, class_name FROM students WHERE code=? AND (status IS NULL OR status='' OR status='فعال')", (code,)).fetchone()


def support_plans():
    with get_db() as conn:
        students = conn.execute("SELECT code, first_name, last_name, grade, class_name FROM students WHERE status IS NULL OR status='' OR status='فعال' ORDER BY last_name, first_name").fetchall()
        plans = conn.execute("""
            SELECT p.*, s.first_name, s.last_name, s.grade, s.class_name
            FROM support_plans p JOIN students s ON s.code=p.student_code
            ORDER BY p.id DESC
        """).fetchall()

    if request.method == "POST":
        try:
            student_code = _text(request.form.get("student_code"), 80)
            provider_role = _text(request.form.get("provider_role"), 40)
            if provider_role not in _ROLES:
                raise ValueError("نقش مشاور یا مددکار معتبر نیست.")
            planned_date = normalize_jalali_date(_text(request.form.get("planned_date"), 20), required=False) or ""
            referral_type = _text(request.form.get('referral_type'), 30) or "داخل مدرسه"
            if referral_type not in _REFERRAL_TYPES:
                raise ValueError("نوع ارجاع معتبر نیست.")
            referral_destination = _text(request.form.get('referral_destination'), 250)
            session_date = normalize_jalali_date(_text(request.form.get('session_date'), 20), required=False) or ""
            session_start_time = _text(request.form.get('session_start_time'), 5)
            session_end_time = _text(request.form.get('session_end_time'), 5)
            time_pattern = re.compile(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')
            if session_start_time and not time_pattern.fullmatch(session_start_time):
                raise ValueError("ساعت شروع جلسه معتبر نیست.")
            if session_end_time and not time_pattern.fullmatch(session_end_time):
                raise ValueError("ساعت پایان جلسه معتبر نیست.")
            if session_start_time and session_end_time and session_end_time <= session_start_time:
                raise ValueError("ساعت پایان جلسه باید بعد از ساعت شروع باشد.")
            status = _text(request.form.get("status"), 30) or "برنامه‌ریزی‌شده"
            if status not in _STATUSES:
                raise ValueError("وضعیت پیگیری معتبر نیست.")
            planned_sessions = _number(request.form.get("planned_sessions"))
            completed_sessions = _number(request.form.get("completed_sessions"))
            if completed_sessions > planned_sessions and planned_sessions:
                raise ValueError("تعداد جلسات انجام‌شده نمی‌تواند از جلسات برنامه‌ریزی‌شده بیشتر باشد.")
            cost = _number(request.form.get("cost"))
            topic = _text(request.form.get("topic"), 1000)
            outcome = _text(request.form.get("outcome"), 1500)
            notes = _text(request.form.get("notes"), 1500)
            provider_name = _text(request.form.get("provider_name"), 200)
            provider_phone = _text(request.form.get("provider_phone"), 40)
            provider_org = _text(request.form.get("provider_org"), 200)
            if not student_code or not topic:
                raise ValueError("دانش‌آموز و موضوع پیگیری الزامی هستند.")
            upload = request.files.get("document")
            document_path = ""
            document_name = ""
            if upload and upload.filename:
                original = secure_filename(upload.filename)
                extension = Path(original).suffix.lower().lstrip(".")
                if extension not in _ALLOWED_EXTENSIONS:
                    raise ValueError("نوع مدرک مجاز نیست. PDF، Word و تصویر قابل ثبت هستند.")
                folder = Path(current_app.config["UPLOAD_FOLDER"]) / "support_documents"
                folder.mkdir(parents=True, exist_ok=True)
                stored = f"{uuid.uuid4().hex}.{extension}"
                upload.save(folder / stored)
                document_path = str(Path("support_documents") / stored)
                document_name = _text(upload.filename, 180)
            with get_db() as conn:
                student = _student_scope(conn, student_code)
                if not student:
                    raise ValueError("دانش‌آموز فعال پیدا نشد.")
                conn.execute("""INSERT INTO support_plans
                    (student_code, provider_role, provider_name, provider_phone, provider_org,
                     planned_date, topic, planned_sessions, completed_sessions, cost, outcome,
                     status, notes, document_path, document_name, referral_type, referral_destination, session_date, session_start_time, session_end_time, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
                    (student_code, provider_role, provider_name, provider_phone, provider_org,
                     planned_date, topic, planned_sessions, completed_sessions, cost, outcome,
                     status, notes, document_path, document_name, referral_type, referral_destination, session_date, session_start_time, session_end_time))
            audit(None, "create_support_plan", "support_plan", student_code, topic)
            flash("برنامه مشاوره/توانبخشی با موفقیت ثبت شد.", "success")
        except (ValueError, TypeError) as exc:
            flash(str(exc), "danger")
        return redirect(url_for("support_plans"))

    return render_template("support_plans.html", students=students, plans=plans, today=today_string())


def download_support_document(plan_id):
    with get_db() as conn:
        row = conn.execute("SELECT document_path, document_name FROM support_plans WHERE id=?", (plan_id,)).fetchone()
    if not row or not row["document_path"]:
        abort(404)
    path = Path(current_app.config["UPLOAD_FOLDER"]) / row["document_path"]
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=row["document_name"] or path.name)


def delete_support_plan(plan_id):
    with get_db() as conn:
        row = conn.execute("SELECT document_path FROM support_plans WHERE id=?", (plan_id,)).fetchone()
        if not row:
            abort(404)
        conn.execute("DELETE FROM support_plans WHERE id=?", (plan_id,))
    audit(None, "delete_support_plan", "support_plan", plan_id, "")
    if row["document_path"]:
        path = Path(current_app.config["UPLOAD_FOLDER"]) / row["document_path"]
        try:
            path.unlink(missing_ok=True)
        except OSError:
            current_app.logger.warning("Could not remove support document %s", path)
    flash("رکورد پیگیری حذف شد.", "success")
    return redirect(url_for("support_plans"))


def register(app):
    app.add_url_rule("/support-plans", endpoint="support_plans", view_func=support_plans, methods=["GET", "POST"])
    app.add_url_rule("/support-plans/<int:plan_id>/document", endpoint="download_support_document", view_func=download_support_document)
    app.add_url_rule("/support-plans/<int:plan_id>/delete", endpoint="delete_support_plan", view_func=delete_support_plan, methods=["POST"])
