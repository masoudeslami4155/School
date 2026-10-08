#!/usr/bin/env python
"""مرکز پشتیبان‌گیری و ذخیره‌سازی — سامانهٔ جامع مدیریت مدرسه.

این ابزار پشتیبان‌گیری را مستقیم با Python اجرا می‌کند و متن فارسی را هم
برای کنسول کلاسیک ویندوز آماده می‌کند
(چسباندن حروف و ترتیب راست‌به‌چپ با ``tools/console_text.py``).

از ریشهٔ پروژه اجرا کنید::

    python tools/backup_center.py                 # منوی تعاملی
    python tools/backup_center.py --full          # پشتیبان کامل آفلاین
    python tools/backup_center.py --repo          # فقط مخزن گیت
    python tools/backup_center.py --db            # فقط عکس فوری دیتابیس
    python tools/backup_center.py --verify        # بررسی سلامت آخرین بسته
    python tools/backup_center.py --copy \\\\server\\share\\backups
    python tools/backup_center.py --push --yes    # ارسال به گیت‌هاب
    python tools/backup_center.py --commit -m "پیام" --yes
    python tools/backup_center.py --status        # گزارش وضعیت کامل
    python tools/backup_center.py --guide         # راهنمای بازیابی

هر عملیات در ``logs/backup_tool.log`` ثبت می‌شود و کد خروج ۰ یعنی موفق،
۱ یعنی ناموفق (مناسب زمان‌بندی با Task Scheduler).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / 'tools'
for _entry in (str(TOOLS), str(ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import offline_backup as engine  # noqa: E402  — موتور پشتیبان‌سازی آفلاین
from console_text import cinput, cprint, shaping_hint  # noqa: E402

OUT_DIR = ROOT / 'offline_backups'
BACKUPS_DIR = ROOT / 'backups'
LOG_FILE = ROOT / 'logs' / 'backup_tool.log'
TARGET_FILE = TOOLS / 'backup_target.txt'
DB_NAME = 'school.db'
BACKUP_KEEP = 10  # چند پشتیبان تازه‌تر برنامه داخل بستهٔ ZIP برود (۰ = همه)

INTERACTIVE = True  # در حالت خط فرمان، پرسش‌ها نمایش داده نمی‌شوند

MENU = (
    ('1', 'پشتیبان کامل آفلاین: مخزن + دیتابیس + پشتیبان‌ها', 'full ZIP'),
    ('2', 'فقط مخزن گیت بدون داده', 'bundle'),
    ('3', 'عکس فوری سریع از دیتابیس', 'school.db'),
    ('4', 'بررسی سلامت یک بستهٔ ZIP', 'verify'),
    ('5', 'کپی آخرین بسته به مقصد بیرونی: USB / فضای ابری', 'copy'),
    ('6', 'ارسال تغییرات به گیت‌هاب', 'git push'),
    ('7', 'ثبت تغییرات در گیت با پیام دلخواه', 'commit'),
    ('8', 'گزارش وضعیت کامل', 'status'),
    ('9', 'راهنمای بازیابی روی رایانهٔ دیگر', 'restore'),
    ('0', 'خروج', 'exit'),
)


# --------------------------------------------------------------------------
# کمکی‌های عمومی
# --------------------------------------------------------------------------
def log(message: str) -> None:
    """ثبت عملیات در ``logs/backup_tool.log`` (متن خام، بدون اصلاح نمایشی)."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open('a', encoding='utf-8') as handle:
            handle.write(f'[{datetime.now().isoformat(timespec="seconds")}] {message}\n')
    except OSError:
        pass


def _git(args: list[str], capture: bool = False) -> subprocess.CompletedProcess[str] | None:
    git = shutil.which('git')
    if not git:
        return None
    try:
        return subprocess.run(
            [git, *args],
            cwd=str(ROOT),
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT if capture else None,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _git_out(args: list[str], default: str = '') -> str:
    result = _git(args, capture=True)
    if result is None or result.returncode != 0:
        return default
    return (result.stdout or '').strip()


def _git_upstream() -> str:
    """Return the configured upstream instead of assuming origin/main."""
    return _git_out(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}'])


def packages() -> list[Path]:
    """بسته‌های ZIP موجود، تازه‌ترین اول."""
    if not OUT_DIR.is_dir():
        return []
    return sorted(OUT_DIR.glob('*.zip'), key=lambda item: item.stat().st_mtime, reverse=True)


def human_size(size: int) -> str:
    if size >= 1024 ** 3:
        return f'{size / 1024 ** 3:.2f} گیگابایت'
    if size >= 1024 ** 2:
        return f'{size / 1024 ** 2:.2f} مگابایت'
    return f'{size / 1024:.1f} کیلوبایت'


def confirm(question: str) -> bool:
    """پرسش بله/خیر؛ در حالت خط فرمان هم می‌پرسد."""
    answer = cinput(f'  {question} (y/N): ').strip().lower()
    return answer in ('y', 'yes', 'بله', 'ب')


def pause() -> None:
    if INTERACTIVE:
        cinput('  برای ادامه Enter بزنید... ')


def finish(label: str, result: bool | None) -> bool:
    """گزارش پایان یک عملیات؛ ``None`` یعنی کاربر انصراف داد."""
    if result is None:
        cprint('  [−] عملیات لغو شد.')
        pause()
        return False
    if result:
        cprint(f'  [OK] {label} انجام شد.')
        log(f'OK: {label}')
    else:
        cprint(f'  [X] {label} انجام نشد.')
        log(f'FAILED: {label}')
    pause()
    return result


def require_python_libs() -> None:
    hint = shaping_hint()
    if hint:
        cprint(f'  {hint}')
        cprint('')


# --------------------------------------------------------------------------
# عملیات
# --------------------------------------------------------------------------
def act_full() -> bool:
    cprint('\n=== پشتیبان کامل آفلاین: مخزن + دیتابیس + پشتیبان‌ها ===')
    archive, error = engine.build_archive(OUT_DIR, last_backups=BACKUP_KEEP, quiet=True)
    if archive is None:
        cprint(f'  ✗ {error}')
        return finish('پشتیبان کامل آفلاین', False)
    cprint(f'  ✓ بسته ساخته شد: {archive.name}  ({human_size(archive.stat().st_size)})')
    cprint(f'  محل فایل: {archive}')
    cprint('  برای نگه‌داشتن در جای دیگر، گزینهٔ ۵ (کپی به مقصد بیرونی) را بزنید.')
    return finish('پشتیبان کامل آفلاین', True)


def act_repo() -> bool:
    cprint('\n=== فقط مخزن گیت، بدون داده ===')
    archive, error = engine.build_archive(
        OUT_DIR, last_backups=BACKUP_KEEP, include_db=False, quiet=True,
    )
    if archive is None:
        cprint(f'  ✗ {error}')
        return finish('پشتیبان مخزن گیت', False)
    cprint(f'  ✓ بسته ساخته شد: {archive.name}  ({human_size(archive.stat().st_size)})')
    return finish('پشتیبان مخزن گیت', True)


def act_db() -> bool:
    cprint('\n=== عکس فوری دیتابیس مدرسه ===')
    snapshot, note = engine.export_database(OUT_DIR)
    if snapshot is None:
        cprint(f'  ✗ {note}')
        return finish('عکس فوری دیتابیس', False)
    if note:
        cprint(f'  گزارش: {note}')
    cprint(f'  ✓ فایل ساخته شد: {snapshot.name}  ({human_size(snapshot.stat().st_size)})')
    return finish('عکس فوری دیتابیس', True)


def act_verify(archive: str | None = None) -> bool:
    cprint('\n=== بررسی سلامت بستهٔ پشتیبان ===')
    if archive:
        target = Path(archive)
    else:
        available = packages()
        if not available:
            cprint(f'  ✗ هیچ بستهٔ ZIP ای در {OUT_DIR.name} نیست؛ اول گزینهٔ ۱ را اجرا کنید.')
            return finish('بررسی سلامت بسته', False)
        target = available[0]
        if INTERACTIVE:
            cprint('  بسته‌های موجود:')
            for index, item in enumerate(available[:9], start=1):
                cprint(f'    [{index}] {item.name}  ({human_size(item.stat().st_size)})')
            choice = cinput('  شماره بسته (Enter = تازه‌ترین): ').strip()
            if choice.isdigit() and 1 <= int(choice) <= min(9, len(available)):
                target = available[int(choice) - 1]
            elif choice:
                cprint('  [!] شمارهٔ نامعتبر؛ تازه‌ترین بسته بررسی می‌شود.')
    cprint(f'  بسته: {target.name}')
    ok = engine.verify_archive(target)
    return finish('بررسی سلامت بسته', ok)


def detect_external_targets() -> dict[str, Path]:
    """مقصدهای بیرونیِ در دسترس: ذخیره‌شده، USB/دیسک خارجی و پوشهٔ ابری."""
    found: dict[str, Path] = {}
    if TARGET_FILE.is_file():
        try:
            saved = TARGET_FILE.read_text(encoding='utf-8').strip()
            if saved:
                found['ذخیره‌شدهٔ شما'] = Path(saved)
        except OSError:
            pass
    for letter in 'DEFGHIJKL':
        candidate = Path(f'{letter}:\\school_backups')
        try:
            if candidate.is_dir():
                found[f'درایو {letter}:'] = candidate
                break
        except OSError:
            continue
    onedrive = os.environ.get('OneDrive')
    if onedrive:
        found['پوشهٔ ابری (OneDrive)'] = Path(onedrive) / 'school_backups'
    return found


def save_target(target: Path) -> None:
    try:
        TARGET_FILE.parent.mkdir(parents=True, exist_ok=True)
        TARGET_FILE.write_text(str(target) + '\n', encoding='utf-8')
    except OSError:
        pass


def act_copy(target: str | None = None) -> bool:
    cprint('\n=== کپی آخرین بسته به مقصد بیرونی ===')
    available = packages()
    if not available:
        cprint(f'  ✗ هیچ بستهٔ ZIP ای در {OUT_DIR.name} نیست؛ اول گزینهٔ ۱ را اجرا کنید.')
        return finish('کپی بسته', False)
    newest = available[0]
    cprint(f'  بسته: {newest.name}  ({human_size(newest.stat().st_size)})')

    if target:
        destination = Path(target)
    else:
        candidates = detect_external_targets()
        default = next(iter(candidates.values()), None)
        if candidates:
            cprint('  مقصدهای پیشنهادی:')
            for label, path in candidates.items():
                cprint(f'    {label}: {path}')
        if not INTERACTIVE:
            if default is None:
                cprint('  ✗ مقصدی تنظیم نشده؛ یک‌بار گزینهٔ ۵ را به‌صورت تعاملی اجرا کنید.')
                return finish('کپی بسته', False)
            destination = default
        else:
            answer = cinput(f'  مسیر مقصد (Enter = {default or "بدون پیشنهاد"}، 0 = انصراف): ').strip()
            if answer == '0':
                return finish('کپی بسته', None)
            if not answer and default is None:
                cprint('  ✗ مقصدی وارد نشد.')
                return finish('کپی بسته', False)
            destination = Path(answer) if answer else default

    try:
        destination.mkdir(parents=True, exist_ok=True)
        copy_result = shutil.copy2(newest, destination / newest.name)
        save_target(destination)
        cprint(f'  ✓ کپی شد به: {copy_result}')
    except OSError as error:
        cprint(f'  ✗ کپی انجام نشد: {error}')
        return finish('کپی بسته', False)
    return finish('کپی بسته', True)


def act_push(skip_confirm: bool = False) -> bool:
    cprint('\n=== ارسال تغییرات به گیت‌هاب ===')
    _git(['status', '-sb'])
    upstream = _git_upstream()
    if upstream:
        pending = _git_out(['rev-list', '--count', f'{upstream}..HEAD'])
        if pending in ('', '0'):
            cprint(f'  کامیت تازه‌ای برای ارسال به {upstream} نیست.')
        else:
            cprint(f'  کامیت‌های آمادهٔ ارسال به {upstream}: {pending}')
    else:
        cprint('  شاخهٔ فعلی upstream تنظیم‌شده ندارد؛ نتیجهٔ git push تعیین‌کننده است.')
    if not skip_confirm and not confirm('ارسال به origin/main انجام شود؟'):
        return finish('ارسال به گیت‌هاب', None)
    result = _git(['push'])
    if result is None:
        cprint('  ✗ فرمان git پیدا نشد.')
        return finish('ارسال به گیت‌هاب', False)
    _git(['status', '-sb'])
    return finish('ارسال به گیت‌هاب', result.returncode == 0)


def act_commit(message: str | None = None, skip_confirm: bool = False) -> bool:
    cprint('\n=== ثبت تغییرات در گیت ===')
    _git(['status', '--short'])
    if message is None:
        if not INTERACTIVE:
            cprint('  ✗ در حالت خط فرمان باید پیام را با -m بدهید.')
            return finish('ثبت تغییرات در گیت', False)
        message = cinput('  پیام کامیت (خالی = انصراف): ').strip()
    if not message:
        return finish('ثبت تغییرات در گیت', None)
    if not skip_confirm and not confirm('همهٔ تغییرات بالا stage و کامیت شوند؟'):
        return finish('ثبت تغییرات در گیت', None)
    if _git(['add', '-A']) is None:
        cprint('  ✗ فرمان git پیدا نشد.')
        return finish('ثبت تغییرات در گیت', False)
    result = _git(['commit', '-m', message])
    return finish('ثبت تغییرات در گیت', result is not None and result.returncode == 0)


def act_status() -> bool:
    cprint('\n--- مخزن گیت ---')
    _git(['status', '-sb'])
    head = _git_out(['log', '-1', '--oneline'])
    cprint(f'  آخرین کامیت: {head or "—"}')
    upstream = _git_upstream()
    if upstream:
        pending = _git_out(['rev-list', '--count', f'{upstream}..HEAD'])
        if pending:
            cprint(f'  کامیت‌های push‌نشده نسبت به {upstream}: {pending}')
    else:
        cprint('  upstream برای شاخهٔ فعلی تنظیم نشده است.')
    hooks = _git_out(['config', '--local', '--get', 'core.hooksPath'])
    if hooks:
        cprint(f'  هوک‌های گیت: فعال از {hooks}')
    else:
        cprint('  هوک‌های گیت: غیرفعال — در صورت نیاز python tools/install_hooks.py را اجرا کنید')

    cprint('\n--- داده و پشتیبان‌ها ---')
    database = ROOT / DB_NAME
    if database.is_file():
        cprint(f'  حجم دیتابیس: {human_size(database.stat().st_size)}')
    backup_files = sorted(BACKUPS_DIR.glob('*')) if BACKUPS_DIR.is_dir() else []
    if backup_files:
        total = sum(item.stat().st_size for item in backup_files)
        cprint(f'  پشتیبان‌های برنامه: {len(backup_files)} فایل ({human_size(total)})')
    else:
        cprint('  پشتیبان‌های برنامه: هنوز چیزی در پوشهٔ backups نیست')
    available = packages()
    if available:
        total = sum(item.stat().st_size for item in available)
        cprint(f'  بسته‌های ZIP: {len(available)} فایل ({human_size(total)})')
        cprint(f'  تازه‌ترین بسته: {available[0].name}  ({human_size(available[0].stat().st_size)})')
    else:
        cprint('  بسته‌های ZIP: هنوز ساخته نشده')
    free = shutil.disk_usage(ROOT).free
    cprint(f'  فضای آزاد روی دیسک: {human_size(free)}')

    cprint('\n--- مقصدهای بیرونی ---')
    candidates = detect_external_targets()
    if candidates:
        for label, path in candidates.items():
            cprint(f'  {label}: {path}')
    else:
        cprint('  هیچ مقصد بیرونی‌ای پیدا نشد؛ در گزینهٔ ۵ مسیر را وارد کنید.')
    return finish('گزارش وضعیت', True)


def act_guide() -> bool:
    cprint('\n=== راهنمای بازیابی روی رایانهٔ بدون اینترنت ===')
    cprint(engine.RESTORE_GUIDE)
    if INTERACTIVE and OUT_DIR.is_dir():
        if confirm('پوشهٔ بسته‌ها در ویندوز باز شود؟'):
            try:
                os.startfile(str(OUT_DIR))  # noqa: S606 — فقط روی ویندوز
            except (AttributeError, OSError):
                cprint(f'  [!] باز کردن پوشه ممکن نشد: {OUT_DIR}')
    return finish('نمایش راهنمای بازیابی', True)


# --------------------------------------------------------------------------
# منوی تعاملی و خط فرمان
# --------------------------------------------------------------------------
def header() -> None:
    cprint('=' * 62)
    cprint('  سامانه جامع مدیریت مدرسه  —  مرکز پشتیبان‌گیری')
    cprint('  School Management  —  Backup Center')
    cprint('=' * 62)
    cprint(f'  پوشهٔ پروژه: {ROOT}')
    cprint(f'  زمان: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    head = _git_out(['log', '-1', '--oneline'])
    if head:
        cprint(f'  آخرین کامیت: {head}')
    cprint('')


def interactive() -> int:
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        header()
        for key, title, hint in MENU:
            cprint(f'  [{key}] {title}   -   {hint}')
        cprint('')
        choice = cinput('  شماره را بزنید و Enter: ').strip()
        if choice == '0':
            cprint('  خداحافظ! (همهٔ کارها در logs/backup_tool.log ثبت شده است)')
            return 0
        handlers = {
            '1': act_full,
            '2': act_repo,
            '3': act_db,
            '4': act_verify,
            '5': act_copy,
            '6': act_push,
            '7': act_commit,
            '8': act_status,
            '9': act_guide,
        }
        handler = handlers.get(choice)
        if handler is None:
            cprint('  [!] شمارهٔ نامعتبر.')
            pause()
            continue
        try:
            handler()
        except KeyboardInterrupt:
            cprint('\n  [−] لغو شد.')
            pause()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='مرکز پشتیبان‌گیری و ذخیره‌سازی سامانهٔ مدیریت مدرسه.',
    )
    parser.add_argument('--full', action='store_true', help='پشتیبان کامل آفلاین (ZIP)')
    parser.add_argument('--repo', action='store_true', help='فقط مخزن گیت (bundle)')
    parser.add_argument('--db', action='store_true', help='فقط عکس فوری دیتابیس')
    parser.add_argument('--verify', nargs='?', const='', metavar='ZIP', help='بررسی سلامت بسته (پیش‌فرض: تازه‌ترین)')
    parser.add_argument('--copy', nargs='?', const='', metavar='TARGET', help='کپی آخرین بسته به مقصد داده‌شده')
    parser.add_argument('--push', action='store_true', help='ارسال تغییرات به گیت‌هاب')
    parser.add_argument('--commit', action='store_true', help='ثبت تغییرات در گیت (با -m)')
    parser.add_argument('-m', '--message', help='پیام کامیت برای --commit')
    parser.add_argument('--status', action='store_true', help='گزارش وضعیت کامل')
    parser.add_argument('--guide', action='store_true', help='راهنمای بازیابی')
    parser.add_argument('--yes', action='store_true', help='رد کردن پرسش‌های تأیید')
    return parser


def main(argv: list[str] | None = None) -> int:
    global INTERACTIVE
    for stream in (sys.stdout, sys.stderr):  # چاپ امن روی کنسول‌های ویندوزی
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    actions = (args.full, args.repo, args.db, args.verify is not None, args.copy is not None,
               args.push, args.commit, args.status, args.guide)
    if not any(actions):
        INTERACTIVE = True
        require_python_libs()
        try:
            return interactive()
        except KeyboardInterrupt:
            cprint('\n  خداحافظ!')
            return 0

    INTERACTIVE = False
    if args.full:
        return 0 if act_full() else 1
    if args.repo:
        return 0 if act_repo() else 1
    if args.db:
        return 0 if act_db() else 1
    if args.verify is not None:
        return 0 if act_verify(args.verify or None) else 1
    if args.copy is not None:
        return 0 if act_copy(args.copy or None) else 1
    if args.push:
        return 0 if act_push(skip_confirm=args.yes) else 1
    if args.commit:
        return 0 if act_commit(args.message, skip_confirm=args.yes) else 1
    if args.status:
        return 0 if act_status() else 1
    if args.guide:
        return 0 if act_guide() else 1
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
