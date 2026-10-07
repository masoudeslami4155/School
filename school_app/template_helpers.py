from __future__ import annotations

from pathlib import Path

from .dates import display_jalali_datetime
from .report_print_layouts import element_css as report_element_css


def _frontend_built() -> bool:
    """True only when `npm run build` output exists (static/frontend/main.js)."""
    here = Path(__file__).resolve().parent.parent
    return (here / 'static' / 'frontend' / 'main.js').exists()


def register_template_helpers(app):
    @app.template_filter('format_number')
    def format_number(value):
        try:
            return f"{int(value or 0):,}"
        except (TypeError, ValueError):
            return '0'

    @app.template_filter('fa_digits')
    def fa_digits(value):
        """Render all visible numbers with Persian digits, including phone numbers."""
        if value is None:
            return ''
        return str(value).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')).translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '۰۱۲۳۴۵۶۷۸۹'))

    @app.template_filter('yes_no')
    def yes_no(value):
        return '✅ بله' if value in ('1', 1, True) else '❌ خیر'

    @app.template_filter('report_element_css')
    def report_element_css_filter(layout):
        return report_element_css(layout)

    @app.context_processor
    def inject_jalali_date():
        date, date_time, year, month, day = display_jalali_datetime()
        return {'jalali_date': date, 'jalali_datetime': date_time,
                'jalali_year': year, 'jalali_month': month, 'jalali_day': day,
                'frontend_built': _frontend_built()}
