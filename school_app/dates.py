from __future__ import annotations

import re
from datetime import datetime, timedelta

PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
MONTH_NAMES = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']

# The school year opens in مهر and closes in خرداد, so monthly rows have to be
# ranked by *academic* order.  Calendar order and alphabetical order both give
# wrong answers (alphabetically «آبان» sorts first, «مهر» almost last).
ACADEMIC_MONTHS = ['مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند', 'فروردین', 'اردیبهشت', 'خرداد']


def normalize_digits(value: str) -> str:
    return (value or '').translate(PERSIAN_DIGITS)


def month_order_sql(column: str) -> str:
    """Return an ``ORDER BY`` CASE expression ranking a Jalali month name column.

    Summer months (تیر…شهریور) and empty values score 0 so they can never
    outrank a real school month.  ``column`` is interpolated into the SQL text,
    so only pass a trusted identifier written in this codebase, never user
    input.
    """
    branches = ' '.join(
        f"WHEN '{name}' THEN {rank}" for rank, name in enumerate(ACADEMIC_MONTHS, start=1)
    )
    return f'CASE {column} {branches} ELSE 0 END'


def is_jalali_leap(year: int) -> bool:
    return year % 33 in (1, 5, 9, 13, 17, 21, 25, 29)


def jalali_month_days(year: int, month: int) -> int:
    if 1 <= month <= 6:
        return 31
    if 7 <= month <= 11:
        return 30
    if month == 12:
        return 30 if is_jalali_leap(year) else 29
    return 0


def parse_jalali_date(value: str) -> tuple[int, int, int]:
    normalized = normalize_digits(value).strip().replace('-', '/').replace('.', '/')
    parts = normalized.split('/')
    if len(parts) != 3 or not all(re.fullmatch(r'\d+', part) for part in parts):
        raise ValueError('تاریخ باید به شکل ۱۴۰۵/۰۶/۰۱ باشد.')
    year, month, day = (int(part) for part in parts)
    if year < 1 or not 1 <= month <= 12 or not 1 <= day <= jalali_month_days(year, month):
        raise ValueError('تاریخ شمسی نامعتبر است.')
    return year, month, day


def normalize_jalali_date(value: str, required: bool = False) -> str:
    if not (value or '').strip():
        if required:
            raise ValueError('لطفاً تاریخ را وارد کنید.')
        return ''
    year, month, day = parse_jalali_date(value)
    return f'{year:04d}/{month:02d}/{day:02d}'


def jalali_sort_key(value: str) -> tuple[int, int, int]:
    return parse_jalali_date(value)


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_day_no = 365 * (gy - 1600) + (gy - 1600 + 3) // 4 - (gy - 1600 + 99) // 100 + (gy - 1600 + 399) // 400
    g_days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    g_day_no += g_days[gm - 1] + gd - 1
    if gm > 2 and (gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)):
        g_day_no += 1
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    if j_day_no < 186:
        jm = 1 + j_day_no // 31
        jd = 1 + j_day_no % 31
    else:
        jm = 7 + (j_day_no - 186) // 30
        jd = 1 + (j_day_no - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """Convert a valid Jalali date to Gregorian without external packages."""
    jy -= 979
    j_day_no = 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4
    for month in range(1, jm):
        j_day_no += 31 if month <= 6 else 30
    j_day_no += jd - 1
    g_day_no = j_day_no + 79
    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097
    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = False
    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461
    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365
    month_days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and g_day_no >= month_days[gm - 1]:
        g_day_no -= month_days[gm - 1]
        gm += 1
    return gy, gm, g_day_no + 1


def get_today_jalali() -> tuple[int, int, int]:
    now = datetime.now()
    return gregorian_to_jalali(now.year, now.month, now.day)


def today_string() -> str:
    y, m, d = get_today_jalali()
    return f'{y:04d}/{m:02d}/{d:02d}'


def tomorrow_string() -> str:
    tomorrow = datetime.now() + timedelta(days=1)
    y, m, d = gregorian_to_jalali(tomorrow.year, tomorrow.month, tomorrow.day)
    return f'{y:04d}/{m:02d}/{d:02d}'


def calculate_jalali_age(value: str | None, today: tuple[int, int, int] | None = None) -> dict[str, object]:
    """Calculate a student's age from a Jalali birth date.

    The application stores birth dates in the Jalali calendar.  The result is
    deliberately component-based (years, months, days) so it remains useful in
    reports and does not depend on a fixed 365-day approximation.  Empty or
    invalid dates are reported instead of guessed.
    """
    result: dict[str, object] = {
        'valid': False,
        'years': None,
        'months': None,
        'days': None,
        'text': 'ثبت نشده',
    }
    if not (value or '').strip():
        return result
    try:
        birth_year, birth_month, birth_day = parse_jalali_date(value)
        today_year, today_month, today_day = today or get_today_jalali()
        birth = (birth_year, birth_month, birth_day)
        current = (today_year, today_month, today_day)
        if birth > current:
            result['text'] = 'تاریخ تولد در آینده است'
            return result

        years = today_year - birth_year
        months = today_month - birth_month
        days = today_day - birth_day
        if days < 0:
            months -= 1
            previous_month = today_month - 1
            previous_year = today_year
            if previous_month == 0:
                previous_month = 12
                previous_year -= 1
            days += jalali_month_days(previous_year, previous_month)
        if months < 0:
            years -= 1
            months += 12

        result.update({
            'valid': True,
            'years': years,
            'months': months,
            'days': days,
            'text': f'{years} سال، {months} ماه و {days} روز',
        })
        return result
    except (TypeError, ValueError):
        result['text'] = 'تاریخ نامعتبر'
        return result


def display_jalali_datetime() -> tuple[str, str, int, int, int]:
    now = datetime.now()
    y, m, d = gregorian_to_jalali(now.year, now.month, now.day)
    date = f'{y} {MONTH_NAMES[m - 1]} {d}'
    return date, f'{date} - {now:%H:%M}', y, m, d
