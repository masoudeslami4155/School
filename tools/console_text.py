#!/usr/bin/env python
"""نمایش درست متن فارسی در کنسول ویندوز (فقط برای چاپ، نه محتوای فایل).

کنسول کلاسیک ویندوز (conhost) حروف فارسی را به هم نمی‌چسباند و ترتیب
راست‌به‌چپ را هم اعمال نمی‌کند؛ نتیجه متنی جدا و برعکس است. این ماژول پیش
از چاپ، متن را با ``arabic-reshaper`` و ``python-bidi`` به شکل نهایی
(حروف چسبیده + ترتیب دیداری) تبدیل می‌کند.

قواعد مهم
---------
* فقط روی متنی که در کنسول چاپ می‌شود اعمال می‌شود؛ محتوای فایل‌ها
  (راهنمای بازیابی، مانیفست، پیام کامیت و …) دست‌نخورده و در ترتیب منطقی
  می‌ماند تا کپی‌کردن و پردازش آن‌ها سالم باشد.
* اگر کتابخانه‌ها نصب نباشند، متن بدون تغییر چاپ می‌شود؛ هیچ‌وقت خطا نمی‌دهد.
* در ترمینال‌های مدرن (Windows Terminal، VS Code، Git Bash) که خودشان
  درست نمایش می‌دهند، اصلاح انجام نمی‌شود تا متن دو بار برعکس نشود.
* اجبار با متغیر محیطی: ``BACKUP_UI_SHAPE=1`` (همیشه) یا ``0`` (هرگز).
* اگر خروجی به فایل یا لوله (pipe) برود، اصلاح انجام نمی‌شود.

آزمون سریع وضعیت::

    python tools/console_text.py --selftest
"""

from __future__ import annotations

import os
import sys

# ترمینال‌هایی که خودشان چسباندن و ترتیب راست‌به‌چپ را درست انجام می‌دهند
_MODERN_TERMINAL_VARS = ('WT_SESSION', 'TERM_PROGRAM', 'MSYSTEM', 'ConEmuANSI')
_MODERN_TERM_VALUES = ('xterm', 'screen', 'tmux', 'cygwin')


def libraries_available() -> bool:
    """آیا کتابخانه‌های اصلاح متن نصب‌اند؟"""
    try:
        import arabic_reshaper  # noqa: F401
        from bidi.algorithm import get_display  # noqa: F401
    except Exception:
        return False
    return True


def _is_modern_terminal() -> bool:
    for name in _MODERN_TERMINAL_VARS:
        if os.environ.get(name):
            return True
    term = (os.environ.get('TERM') or '').lower()
    if any(token in term for token in _MODERN_TERM_VALUES):
        return True
    return False


def shaping_needed() -> bool:
    """آیا باید قبل از چاپ، متن را برای کنسول اصلاح کرد؟"""
    forced = os.environ.get('BACKUP_UI_SHAPE', '').strip()
    if forced in ('0', '1'):
        return forced == '1'
    try:
        if not sys.stdout.isatty():  # خروجی به فایل یا لوله می‌رود
            return False
    except Exception:
        return False
    if _is_modern_terminal():
        return False
    return libraries_available()


def shape(text: str) -> str:
    """متن را برای نمایش در کنسول کلاسیک ویندوز آماده می‌کند."""
    if not text or not shaping_needed():
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def cprint(*values, **kwargs) -> None:
    """مثل ``print``، ولی متن فارسی برای کنسول اصلاح می‌شود."""
    print(*(shape(str(value)) if isinstance(value, str) else value for value in values), **kwargs)


def cinput(prompt: str = '') -> str:
    """مثل ``input``، ولی متن پرسش برای کنسول اصلاح می‌شود."""
    return input(shape(prompt))


def shaping_hint() -> str:
    """راهنمای نصب کتابخانه‌ها، فقط وقتی لازم است."""
    if shaping_needed() or libraries_available():
        return ''
    return (
        'نکته: برای نمایش بهتر فارسی در کنسول کلاسیک ویندوز، این دو کتابخانه '
        'کوچک را نصب کنید: python -m pip install arabic-reshaper python-bidi'
    )


def _selftest() -> int:
    """وضعیت تشخیص و نمونهٔ خروجی را بدون نیاز به کنسول فارسی چاپ می‌کند."""
    sample = 'برنامه مدیریت مدرسه — مرکز پشتیبان‌گیری'
    shaped = shape(sample)
    print(f'libraries_available : {libraries_available()}')
    print(f'isatty              : {sys.stdout.isatty()}')
    print(f'modern_terminal     : {_is_modern_terminal()}')
    print(f'shaping_needed      : {shaping_needed()}')
    print(f'BACKUP_UI_SHAPE     : {os.environ.get("BACKUP_UI_SHAPE", "(unset)")}')
    print(f'shaped_differs      : {shaped != sample}')
    print('raw    codepoints   : ' + ' '.join(f'{ord(ch):04X}' for ch in sample[:12]))
    print('shaped codepoints   : ' + ' '.join(f'{ord(ch):04X}' for ch in shaped[:12]))
    print('shaped_unicode_esc  : ' + shaped[:12].encode('unicode_escape').decode()[:80])
    return 0


if __name__ == '__main__':
    argv = sys.argv[1:]
    if '--selftest' in argv:
        raise SystemExit(_selftest())
    if '--echo' in argv:  # استفاده در اسکریپت‌های شل (مثل هوک پیش از کامیت)
        index = argv.index('--echo')
        text = argv[index + 1] if index + 1 < len(argv) else ''
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass
        print(shape(text))
        raise SystemExit(0)
    print(__doc__)
