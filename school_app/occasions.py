"""Offline Jalali occasions (مناسبت‌های تقویم شمسی) from persian-holidays.

The dataset is a local copy of the ``persian-holidays`` package (Jalali data):
https://github.com/karfekr/persian-holidays

Keeping a copy inside the project is deliberate: the school system works
completely offline and must never call the network at runtime.

Data notes
----------
* ``fixed`` events carry only ``month`` and ``day``, so they repeat on the same
  Jalali month/day of every year and are year-independent.
* ``relative`` events carry a rule (e.g. "last Wednesday of a month"). These are
  resolved at runtime for the current Jalali year and merged into the index.
* ``isHolidayInIran`` marks official public holidays (تعطیل رسمی). It comes
  straight from the source data and is now surfaced in the calendar UI.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .dates import get_today_jalali, jalali_month_days, jalali_to_gregorian, parse_jalali_date

DATA_FILE = Path(__file__).resolve().parent / 'data' / 'jalali_events.json'
SOURCE_URL = 'https://github.com/karfekr/persian-holidays'

# Category labels rendered in Persian for the interface.
CATEGORY_LABELS = {
    'government': 'ملی / دولتی',
    'religious': 'مذهبی',
    'shia': 'شیعه',
    'sunni': 'سنی',
    'ancient': 'ایران باستان',
    'international': 'بین‌المللی',
    'historical': 'تاریخی',
    'united_nations': 'سازمان ملل',
    'world_health_organization': 'بهداشت جهانی',
    'unesco': 'یونسکو',
}
DEFAULT_LABEL = 'مناسبت'
HOLIDAY_LABEL = 'تعطیل رسمی'


def _read_dataset() -> dict[str, Any]:
    try:
        return json.loads(DATA_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        # A missing or damaged data file must never break the calendar page.
        return {'events': []}


@lru_cache(maxsize=1)
def _raw_events() -> tuple[dict[str, Any], ...]:
    """Validated raw events (fixed + relative) as a tuple of dicts."""
    out: list[dict[str, Any]] = []
    for raw in _read_dataset().get('events', []):
        if not isinstance(raw, dict):
            continue
        title = (raw.get('title') or {}).get('fa') or ''
        if not title:
            continue
        out.append(raw)
    return tuple(out)


def _py_weekday_to_js(py_weekday: int) -> int:
    """Convert Python weekday (Mon=0..Sun=6) to the 0=Sun..6=Sat convention."""
    return (py_weekday + 1) % 7


def _first_weekday_of_month(year: int, month: int) -> int:
    gy, gm, gd = jalali_to_gregorian(year, month, 1)
    import datetime

    return _py_weekday_to_js(datetime.date(gy, gm, gd).weekday())


def _resolve_nth_weekday(rule: dict[str, Any], year: int) -> list[tuple[int, int]]:
    month = int(rule['month'])
    weekday = int(rule['weekday'])
    occurrence = rule.get('occurrence') or 'first'
    length = jalali_month_days(year, month)
    first = _first_weekday_of_month(year, month)
    matches = [d for d in range(1, length + 1) if (first + d - 1) % 7 == weekday]
    if not matches:
        return []
    index = matches.index(max(matches)) if occurrence == 'last' else \
        {'first': 0, 'second': 1, 'third': 2, 'fourth': 3}.get(occurrence, 0)
    if index >= len(matches):
        index = len(matches) - 1
    return [(month, matches[index])]


def _resolve_rule(rule: dict[str, Any], year: int) -> list[tuple[int, int]]:
    base = rule.get('base')
    if base == 'nth-weekday-of-month':
        return _resolve_nth_weekday(rule, year)
    return []


def _label_for(categories: list[str]) -> str:
    for cat in categories:
        label = CATEGORY_LABELS.get(cat)
        if label:
            return label
    return DEFAULT_LABEL


def _labels_for(categories: list[str]) -> list[str]:
    labels = [CATEGORY_LABELS[c] for c in categories if c in CATEGORY_LABELS]
    return labels or [DEFAULT_LABEL]


def _event_to_item(raw: dict[str, Any]) -> dict[str, Any]:
    title = (raw.get('title') or {}).get('fa') or ''
    title_en = (raw.get('title') or {}).get('en') or ''
    categories = [str(c) for c in (raw.get('categories') or [])]
    holiday = bool(raw.get('isHolidayInIran', False))
    labels = _labels_for(categories)
    return {
        'title': title,
        'title_en': title_en,
        'categories': categories,
        'holiday': holiday,
        'labels': labels,
        'label': HOLIDAY_LABEL if holiday else (labels[0] if labels else DEFAULT_LABEL),
        'type': raw.get('type', 'fixed'),
    }


@lru_cache(maxsize=1)
def _index() -> dict[tuple[int, int], list[dict[str, Any]]]:
    """Group every occasion by ``(month, day)`` and sort holidays first."""
    index: dict[tuple[int, int], list[dict[str, Any]]] = {}
    relative_rules: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for raw in _raw_events():
        if raw.get('type') == 'relative':
            rule = raw.get('rule')
            if isinstance(rule, dict):
                relative_rules.append((rule, raw))
            continue
        try:
            month, day = int(raw.get('month')), int(raw.get('day'))
        except (TypeError, ValueError):
            continue
        if not 1 <= month <= 12 or not 1 <= day <= 31:
            continue
        index.setdefault((month, day), []).append(_event_to_item(raw))

    # Resolve relative rules for the current Jalali year.
    current_year, _, _ = get_today_jalali()
    for rule, raw in relative_rules:
        for (month, day) in _resolve_rule(rule, current_year):
            index.setdefault((month, day), []).append(_event_to_item(raw))

    for items in index.values():
        items.sort(key=lambda item: (not item['holiday'], item['title']))
    return index


def for_month_day(month: int, day: int) -> list[dict[str, Any]]:
    """All occasions of a Jalali month/day (independent of the year)."""
    try:
        key = (int(month), int(day))
    except (TypeError, ValueError):
        return []
    return list(_index().get(key, []))


def for_date(value: str | None) -> list[dict[str, Any]]:
    """All occasions of a Jalali date string such as ``1403/01/01``."""
    if not value:
        return []
    try:
        _year, month, day = parse_jalali_date(str(value))
    except (TypeError, ValueError):
        return []
    return for_month_day(month, day)


def has_official(value: str | None) -> bool:
    """True when a date carries at least one official public holiday."""
    return any(item['holiday'] for item in for_date(value))


def for_month(month: int) -> list[dict[str, Any]]:
    """Every occasion of a month, ordered by day — ready for a printed list."""
    try:
        month = int(month)
    except (TypeError, ValueError):
        return []
    return [
        {'day': day, 'items': list(items)}
        for (item_month, day), items in sorted(_index().items())
        if item_month == month
    ]


def titles_for(month: int, day: int) -> list[str]:
    return [item['title'] for item in for_month_day(month, day)]


def today_items() -> list[dict[str, Any]]:
    _year, month, day = get_today_jalali()
    return for_month_day(month, day)


def client_map() -> dict[str, dict[str, Any]]:
    """Compact ``MM/DD`` map handed to the month-grid JavaScript (offline)."""
    payload: dict[str, dict[str, Any]] = {}
    for (month, day), items in sorted(_index().items()):
        payload[f'{month:02d}/{day:02d}'] = {
            't': [item['title'] for item in items],
            'h': 1 if any(item['holiday'] for item in items) else 0,
            'l': sorted({label for item in items for label in item['labels']}),
        }
    return payload


def stats() -> dict[str, Any]:
    index = _index()
    total = sum(len(items) for items in index.values())
    return {
        'events': total,
        'days': len(index),
        'holiday_days': sum(
            1 for items in index.values() if any(item['holiday'] for item in items)
        ),
        'source': SOURCE_URL,
    }
