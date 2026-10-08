from __future__ import annotations

import json
import secrets
from functools import wraps
from urllib.parse import urlparse

from flask import abort, redirect, request, session, url_for

from .database import get_db
from .user_preferences import (
    STUDENT_DISPLAY_FIELDS,
    available_quick_actions,
    default_preferences,
    load_user_preferences,
)

AUTH_EXEMPT_ENDPOINTS = {'login', 'static', 'health', 'forgot_password'}

ADMIN_ENDPOINTS = {
    'users', 'add_user', 'edit_user', 'toggle_user', 'reset_user_password',
    'generate_recovery_code', 'delete_user', 'ai_documents_settings', 'ai_documents_list_models',
    'ai_documents_save_connection',
}

MANAGER_ENDPOINTS = {
    'teachers', 'add_teacher', 'edit_teacher', 'delete_teacher',
    'class_management', 'service_drivers', 'service_drivers_print', 'print_layouts', 'attendance_teachers', 'discipline', 'delete_discipline',
    'class_visit_report', 'delete_class_visit', 'teacher_performance',
    'edit_teacher_performance', 'delete_teacher_performance', 'financial_help',
    'delete_financial_help', 'monthly_service', 'payment_history', 'edit_payment',
    'monthly_service_settings', 'rebuild_monthly_status', 'monthly_service_export', 'monthly_service_print',
    'debtors_by_month', 'calendar', 'edit_event', 'delete_event', 'edit_task', 'toggle_task', 'delete_task', 'daily_digest', 'features_hub', 'student_ages',
    'group_action', 'group_delete', 'export_excel', 'statistics', 'search',
    'update_student_service_fees', 'add_student_to_service', 'remove_student_service_fee',
    'generate_monthly_services', 'delete_monthly_service', 'delete_zero_monthly_services',
    'add_student', 'edit_student', 'confirm_delete_student', 'delete_student', 'permanent_delete_student',
    'restore_student', 'graduates', 'dropouts', 'other_inactive', 'excessive_absences',
    'attendance_quick', 'attendance_report', 'teacher_attendance_report', 'delete_student_attendance', 'update_student_attendance',
    'delete_teacher_attendance', 'delete_filtered_student_absences',
    'delete_filtered_teacher_absences', 'print_filtered_students', 'print_selected', 'print_wall_cards',
    'attendance_report_export', 'support_plans', 'download_support_document', 'delete_support_plan',
    'upload_photo', 'contact_book', 'contact_book_print', 'student_profile', 'print_student', 'student_field_settings',
    'data_quality', 'student_columns', 'student_columns_print', 'student_columns_export',
    'teacher_student_lists','meetings','meeting_new','meeting_view','meeting_delete',
    'list_for_folders','list_for_folders_print', 'report_print_layouts', 'student_filters_print',
    'student_certificate', 'ai_documents', 'ai_documents_generate', 'ai_documents_generate_letter',
    'ai_documents_models', 'ai_documents_select_provider', 'ai_letter_preview',
    'ai_agent', 'ai_agent_chat', 'ai_agent_stream', 'ai_agent_apply_change',
}

TEACHER_ENDPOINTS = {
    'index', 'vdashboard', 'search', 'student_profile', 'print_student', 'print_selected',
    'print_filtered_students', 'print_wall_cards', 'attendance_students', 'change_password', 'logout',
    # A teacher may build the custom column table, but only for their own students
    # and only with the columns their role already reveals.
    'student_columns', 'student_columns_print', 'student_columns_export', 'teacher_student_lists','meetings','meeting_new','meeting_view','meeting_delete','list_for_folders','list_for_folders_print', 'report_print_layouts', 'student_filters_print',
}

COMMON_ENDPOINTS = {'student_print_settings', 'index', 'vdashboard', 'change_password', 'logout', 'student_card_view', 'ui_preferences'}

PERMISSION_LABELS = {
    'student_print_settings': 'تنظیمات چاپ پرونده',
    'index': 'داشبورد و فهرست دانش‌آموزان',
    'ui_preferences': 'تنظیمات نمایش و رابط کاربری',
    'vdashboard': 'داشبورد V (الهام از v-dashboard)',
    'student_profile': 'مشاهده پرونده خوانا',
    'print_student': 'چاپ پرونده دانش‌آموز',
    'print_selected': 'چاپ انتخابی دانش‌آموزان',
    'print_filtered_students': 'چاپ دانش‌آموزان بر اساس فیلتر',
    'print_wall_cards': 'چاپ کارت دیواری دانش‌آموزان',
    'attendance_students': 'حضور و غیاب دانش‌آموزان',
    'attendance_teachers': 'حضور و غیاب کارکنان',
    'attendance_quick': 'ثبت سریع حضور و غیاب کل مدرسه',
    'attendance_report': 'گزارش حضور دانش‌آموزان',
    'attendance_report_export': 'خروجی اکسل گزارش حضور دانش‌آموزان',
    'teacher_attendance_report': 'گزارش حضور کارکنان',
    'teachers': 'فهرست کارکنان',
    'add_teacher': 'ثبت کارکنان',
    'class_management': 'کلاس‌بندی و کلاس سیدا',
    'service_drivers': 'رانندگان سرویس و انتساب دانش‌آموزان',
    'service_drivers_print': 'چاپ جدول رانندگان و دانش‌آموزان',
    'print_layouts': 'استودیو طراحی چاپ و گزارش‌ها',
    'report_print_layouts': 'استودیو طراحی چاپ و گزارش‌ها',
    'ai_documents': 'طراح هوشمند اسناد چاپی',
    'ai_documents_generate': 'تولید سند چاپی با هوش مصنوعی',
    'ai_documents_generate_letter': 'ساخت نامهٔ آماده بدون هوش مصنوعی',
    'ai_documents_models': 'فهرست مدل‌های نصب‌شدهٔ Ollama محلی',
    'ai_documents_select_provider': 'انتخاب سرویس و مدل هوش مصنوعی',
    'ai_letter_preview': 'پیش‌نمایش چاپ نامهٔ اداری',
    'ai_documents_settings': 'تنظیم سرویس هوش مصنوعی اسناد',
    'ai_documents_save_connection': 'ثبت اتصال هوش مصنوعی از صفحهٔ طراح اسناد',
    'student_filters_print': 'چاپ راهنمای فیلترهای دانش‌آموزان',
    'student_certificate': 'صدور گواهی اشتغال به تحصیل',
    'statistics': 'آمار مدیریتی',
    'calendar': 'تقویم، کارها و هشدارها',
    'discipline': 'انضباط',
    'teacher_performance': 'عملکرد معلم',
    'financial_help': 'کمک‌های مالی',
    'monthly_service': 'پرداخت و سرویس',
    'monthly_service_settings': 'مشخصات بانکی سرویس ماهانه',
    'rebuild_monthly_status': 'بازسازی وضعیت سرویس‌ها',
    'monthly_service_export': 'خروجی اکسل سرویس ماهانه',
    'monthly_service_print': 'چاپ برگه‌های سرویس ماهانه',
    'features_hub': 'مرکز امکانات سامانه',
    'contact_book': 'دفترچه تلفن مدرسه',
    'contact_book_print': 'چاپ دفترچه تلفن مدرسه (بدون حاشیه)',
    'student_field_settings': 'فیلدهای سفارشی فرم دانش‌آموز',
    'student_ages': 'محاسبه خودکار سن دانش‌آموزان',
    'export_excel': 'خروجی اکسل',
    'graduates': 'فارغ‌التحصیلان',
    'dropouts': 'ترک‌تحصیل‌ها',
    'data_quality': 'گزارش کیفیت داده‌ها',
    'support_plans': 'مشاوره، مددکاری و توانبخشی',
    'student_columns': 'جدول ستون‌های دلخواه دانش‌آموزان',
    'student_columns_print': 'چاپ A4 جدول ستون‌های دلخواه',
    'student_columns_export': 'خروجی اکسل جدول ستون‌های دلخواه',
    'teacher_student_lists': 'فهرست معلم و دانش‌آموزان، شش‌تایی در A4',
    'list_for_folders':'چاپ لیست چسباننده به پشت پرونده (۶ کارت A4 افقی)',
    'list_for_folders_print':'صفحهٔ چاپ برچسب پرونده (بدون حاشیه)',
    'list_for_folders_print':'صفحهٔ چاپ برچسب پرونده (بدون حاشیه)',
    'meetings':'صورت‌جلسه‌های رسمی مدرسه','meeting_new':'ثبت صورت‌جلسه','meeting_view':'مشاهده و چاپ صورت‌جلسه','meeting_delete':'حذف صورت‌جلسه',
}


def _is_safe_local_url(target: str | None) -> bool:
    if not target:
        return False
    parsed = urlparse(target)
    return not parsed.netloc and not parsed.scheme and target.startswith('/')


def _role_endpoints(role: str | None) -> set[str]:
    if role == 'admin':
        return set(MANAGER_ENDPOINTS) | set(TEACHER_ENDPOINTS) | set(ADMIN_ENDPOINTS) | set(COMMON_ENDPOINTS)
    if role == 'manager':
        return set(MANAGER_ENDPOINTS) | set(COMMON_ENDPOINTS)
    if role == 'teacher':
        return set(TEACHER_ENDPOINTS) | set(COMMON_ENDPOINTS)
    return set()


def _session_endpoints(role: str | None) -> set[str]:
    defaults = _role_endpoints(role)
    raw = session.get('permissions', '')
    if role == 'admin':
        return defaults
    if raw == '__none__':
        return set(COMMON_ENDPOINTS)
    if not raw:
        return defaults
    try:
        chosen = set(json.loads(raw)) if raw.startswith('[') else {x for x in raw.split(',') if x}
    except (TypeError, ValueError):
        chosen = set()
    # A custom grant list can reduce access but never cross the role boundary.
    return (chosen & defaults) | COMMON_ENDPOINTS


def register_security(app):
    @app.before_request
    def require_login_and_authorization():
        endpoint = request.endpoint
        if endpoint in AUTH_EXEMPT_ENDPOINTS or endpoint is None:
            return None
        if 'user_id' not in session:
            next_url = request.full_path if request.method == 'GET' else url_for('login')
            return redirect(url_for('login', next=next_url))
        if session.get('must_change_password') and endpoint not in {'change_password', 'logout'}:
            return redirect(url_for('change_password'))
        if request.method == 'POST' and endpoint not in {'login', 'forgot_password'}:
            expected = session.get('_csrf_token')
            supplied = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token')
            if not expected or not supplied or not secrets.compare_digest(expected, supplied):
                abort(400, description='درخواست نامعتبر است؛ صفحه را تازه‌سازی کنید.')
        role = session.get('role')
        if endpoint in ADMIN_ENDPOINTS and role != 'admin':
            abort(403)
        if role not in {'admin', 'manager', 'teacher'}:
            abort(403)
        if endpoint not in _session_endpoints(role):
            abort(403)
        return None

    @app.before_request
    def ensure_csrf_session():
        session.setdefault('_csrf_token', secrets.token_urlsafe(32))

    @app.context_processor
    def inject_auth_user():
        user_id = session.get('user_id')
        role = session.get('role')
        preferences = load_user_preferences(user_id) if user_id else default_preferences()
        allowed_endpoints = _session_endpoints(role) if user_id else set()
        field_labels = dict(STUDENT_DISPLAY_FIELDS)
        table_fields = [
            (key, field_labels[key])
            for key in preferences.get('student_table_order', ())
            if key in field_labels and key in preferences.get('student_table_fields', ())
        ]
        selected_quick_actions = available_quick_actions(
            role, allowed_endpoints, preferences.get('quick_actions', ()),
        )
        selected_action_keys = {action['key'] for action in selected_quick_actions}
        available_actions = available_quick_actions(role, allowed_endpoints)
        ordered_action_options = selected_quick_actions + [
            action for action in available_actions if action['key'] not in selected_action_keys
        ]
        return {
            'current_user': session.get('full_name'),
            'current_role': role,
            'csrf_token': lambda: session.get('_csrf_token', ''),
            'permission_labels': PERMISSION_LABELS,
            'ui_preferences': preferences,
            'student_display_fields': STUDENT_DISPLAY_FIELDS,
            'student_table_display_fields': table_fields,
            'quick_action_options': ordered_action_options,
            'dashboard_quick_actions': selected_quick_actions,
        }

    @app.errorhandler(400)
    def bad_request(error):
        return getattr(error, 'description', 'درخواست نامعتبر است.'), 400

    @app.errorhandler(403)
    def forbidden(_error):
        return 'دسترسی به این بخش برای حساب شما مجاز نیست.', 403

    @app.errorhandler(404)
    def not_found(_error):
        return 'صفحه مورد نظر پیدا نشد.', 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.exception('Unhandled application error: %s', error)
        return 'خطای داخلی سامانه رخ داد. لطفاً لاگ برنامه را بررسی کنید.', 500


def current_user_role() -> str | None:
    return session.get('role')


def current_session_endpoints() -> set[str]:
    """Return the endpoints already authorized for the active session."""
    return _session_endpoints(session.get('role'))


def teacher_scope() -> str | None:
    return session.get('personnel_number') if session.get('role') == 'teacher' else None


def require_role(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get('role') not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def audit(actor_user_id, action: str, entity_type: str = '', entity_id: str = '', details: str = '') -> None:
    try:
        with get_db() as conn:
            conn.execute(
                'INSERT INTO audit_log(actor_user_id,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,datetime("now"))',
                (actor_user_id, action, entity_type, str(entity_id), details),
            )
            conn.commit()
    except Exception:
        pass
