#!/usr/bin/env python
"""بستهٔ پشتیبان آفلاین کامل — سامانهٔ جامع مدیریت مدرسه.

کل مخزن گیت را با ``git bundle`` (همراه همهٔ تاریخچه، بدون نیاز به اینترنت یا
گیت‌هاب) برمی‌دارد و همراه دیتابیس مدرسه، پشتیبان‌های برنامه، مانیفست و
راهنمای بازیابی در **یک فایل ZIP زمان‌دار** بسته‌بندی می‌کند.

نمونه‌های اجرا::

    python tools/offline_backup.py                  # بستهٔ کامل با ۱۰ پشتیبان تازه‌تر
    python tools/offline_backup.py --last 0         # همهٔ پشتیبان‌ها بدون محدودیت
    python tools/offline_backup.py --no-db          # فقط مخزن (بدون داده)
    python tools/offline_backup.py --db-only        # فقط عکس فوری دیتابیس (سبک و سریع)
    python tools/offline_backup.py --verify <zip>   # بررسی سالم‌بودن یک بسته

خروجی در ``offline_backups/school_offline_YYYY-MM-DD_HHMMSS.zip`` ساخته
می‌شود (این پوشه در ``.gitignore`` است). بازیابی روی رایانهٔ بدون اینترنت:

    git clone repo.bundle school_management
    copy data\\school.db school_management\\school.db

کد خروج ۰ یعنی بسته با موفقیت ساخته/تأیید شد؛ ۱ یعنی خطا.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # ریشهٔ پروژه (والد پوشهٔ tools)

# چاپ متن فارسی برای کنسول کلاسیک ویندوز (اختیاری؛ اگر نبود، چاپ معمولی)
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from console_text import cprint as _say
except Exception:  # pragma: no cover — بدون کتابخانه‌های اختیاری هم باید کار کند
    _say = print
DEFAULT_OUT_DIR = ROOT / 'offline_backups'
DB_NAME = 'school.db'
BACKUPS_DIR_NAME = 'backups'
BUNDLE_NAME = 'repo.bundle'
MANIFEST_NAME = 'MANIFEST_FA.txt'
RESTORE_NAME = 'RESTORE_FA.txt'

RESTORE_GUIDE = """\
راهنمای بازیابی روی رایانهٔ بدون اینترنت
=========================================
این بسته کاملاً آفلاین است؛ به گیت‌هاب، اینترنت یا ابزار خاصی نیاز ندارد.
پیش‌نیاز رایانهٔ مقصد: Python 3.10+ و Git 2.30+ (همان‌هایی که برنامه با آن‌ها اجرا می‌شود).

۱) فایل ZIP را از حالت فشرده خارج کنید
   ویندوز: راست‌کلیک روی فایل → Extract All…
   نتیجه: پوشه‌ای شامل repo.bundle، MANIFEST_FA.txt، پوشهٔ data/ و همین راهنما.

۲) مخزن را از بستهٔ گیت بازسازی کنید (دستورها را در همان پوشهٔ استخراج‌شده بزنید):
       git clone repo.bundle school_management
   این کار همهٔ تاریخچه و فایل‌های پروژه را می‌سازد.
   اگر از قبل مخزنی دارید و فقط می‌خواهید تاریخچه را به آن اضافه کنید:
       git fetch ..\\repo.bundle main:refs/heads/main

۳) داده‌ها را سرجای خودشان برگردانید (باز هم از پوشهٔ استخراج‌شده):
       copy data\\school.db school_management\\school.db
       xcopy /E /I data\\backups school_management\\backups

۴) برنامه را اجرا کنید:
       cd school_management
        python app.py
   - هوک‌های گیت هنگام اجرای برنامه خودکار فعال می‌شوند؛ نیازی به کپی دستی نیست.
   - کلید نشست (.secret_key) در رایانهٔ جدید خودکار ساخته می‌شود؛ کاربران با
     همان رمزهای قبلی وارد می‌شوند (فقط نشست‌های بازِ قبلی باطل می‌شوند).
   - اگر رمزها را ندارید: python reset_password_offline.py
   - اگر روی این رایانه هم کامیت می‌زنید، یک‌بار هویت گیت را تنظیم کنید
     (هویت از مخزن مبدأ منتقل نمی‌شود):
       git config user.name "مسعود اسلامی"
       git config user.email "ایمیل شما"

۵) بررسی سلامت خود بسته (اختیاری):
       python tools/offline_backup.py --verify <مسیر فایل zip>

نکته‌های امنیتی
---------------
- این بسته شامل school.db است؛ مثل فایل پشتیبان اصلی، آن را در جای امن
  (USB قفل‌شده، گاوصندوق، دیسک رمزگذاری‌شده) نگه دارید و در شبکهٔ عمومی نگذارید.
- بعد از هر بازیابی، اولین کار رمزهای پیش‌فرض/موقت را تغییر دهید.
"""


# --------------------------------------------------------------------------
# ابزارهای پایه
# --------------------------------------------------------------------------
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    git = shutil.which('git')
    if not git:
        return None
    try:
        return subprocess.run(
            [git, *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _git_text(args: list[str]) -> str:
    result = _run_git(args, ROOT)
    if result is None or result.returncode != 0:
        return ''
    return result.stdout.strip()


# --------------------------------------------------------------------------
# جمع‌آوری قطعه‌ها
# --------------------------------------------------------------------------
def collect_repo_info() -> dict[str, str]:
    return {
        'branch': _git_text(['rev-parse', '--abbrev-ref', 'HEAD']) or '؟',
        'head': _git_text(['log', '-1', '--format=%h — %s']) or '؟',
        'count': _git_text(['rev-list', '--count', 'HEAD']) or '؟',
        'dirty': _git_text(['status', '--porcelain']),
    }


def create_bundle(dest: Path) -> tuple[bool, str]:
    """کل مخزن را در یک فایل بستهٔ گیت می‌ریزد (شاخه‌ها، تگ‌ها و HEAD)."""
    result = _run_git(['bundle', 'create', str(dest), '--branches', '--tags', 'HEAD'], ROOT)
    if result is None:
        return False, 'فرمان git پیدا نشد.'
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or '').strip()
    return True, ''


def copy_database(dest: Path) -> tuple[bool, str]:
    """یک عکس لحظه‌ای سازگار از دیتابیس می‌گیرد (حتی اگر برنامه باز باشد).

    اول با API پشتیبان‌گیری SQLite تلاش می‌کند و اگر نشد، کپی فایل معمولی
    (همراه فایل‌های wal/shm) انجام می‌دهد.
    """
    db_path = ROOT / DB_NAME
    if not db_path.is_file():
        return False, f'فایل {DB_NAME} پیدا نشد.'
    try:
        uri = f'{db_path.as_uri()}?mode=ro'
        source = sqlite3.connect(uri, uri=True)
        try:
            with sqlite3.connect(str(dest)) as target:
                source.backup(target)
        finally:
            source.close()
        return True, ''
    except sqlite3.Error as error:
        try:
            shutil.copy2(db_path, dest)
            for suffix in ('-wal', '-shm'):
                sidecar = db_path.with_name(db_path.name + suffix)
                if sidecar.is_file():
                    shutil.copy2(sidecar, dest.with_name(dest.name + suffix))
            return True, f'کپی فایل معمولی ({error})'
        except OSError as copy_error:
            return False, str(copy_error)


def collect_backups(limit: int) -> tuple[list[Path], int]:
    """فایل‌های پشتیبان برنامه (تازه‌ترین‌ها اول) و تعداد کل موجود."""
    folder = ROOT / BACKUPS_DIR_NAME
    if not folder.is_dir():
        return [], 0
    files = sorted(
        (item for item in folder.iterdir() if item.is_file()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    selected = files[:limit] if limit > 0 else files
    return selected, len(files)


# --------------------------------------------------------------------------
# ساخت و بررسی بسته
# --------------------------------------------------------------------------
def build_archive(
    out_dir: Path,
    last_backups: int = 0,
    include_db: bool = True,
    quiet: bool = False,
) -> tuple[Path | None, str]:
    """بستهٔ کامل ZIP را می‌سازد؛ با ``quiet=True`` هیچ پیامی چاپ نمی‌کند."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')
    archive = out_dir / f'school_offline_{stamp}.zip'

    info = collect_repo_info()
    if info['dirty'] and not quiet:
        _say('⚠ تغییرات کامیت‌نشده وجود دارد؛ این تغییرات در بستهٔ گیت نمی‌آیند:')
        for line in info['dirty'].splitlines()[:10]:
            _say(f'    {line}')
        _say('  برای اینکه در پشتیبان هم باشند، اول یک کامیت بزنید.')

    with tempfile.TemporaryDirectory(prefix='school_backup_') as temp_dir:
        temp = Path(temp_dir)
        errors: list[str] = []

        bundle_path = temp / BUNDLE_NAME
        ok, message = create_bundle(bundle_path)
        if not ok:
            return None, f'ساخت بستهٔ گیت ناموفق بود: {message}'

        db_path: Path | None = None
        if include_db:
            candidate = temp / DB_NAME
            ok, message = copy_database(candidate)
            if ok:
                db_path = candidate
                if message and not quiet:
                    _say(f'گزارش دیتابیس: {message}')
            else:
                # A full backup without its database is misleading and cannot
                # be restored as documented, so fail before creating the ZIP.
                return None, f'دیتابیس برداشته نشد: {message}'

        backup_files, backup_total = collect_backups(last_backups)
        if not include_db:
            backup_files, backup_total = [], 0

        lines = [
            'بستهٔ پشتیبان آفلاین — سامانهٔ جامع مدیریت مدرسه',
            '=' * 52,
            f'تاریخ ساخت: {datetime.now().isoformat(timespec="seconds")}',
            f'نام بسته: {archive.name}',
            f'شاخه: {info["branch"]}',
            f'آخرین کامیت: {info["head"]}',
            f'تعداد کامیت‌ها: {info["count"]}',
            f'تغییرات کامیت‌نشده: {"دارد (در بسته نیست)" if info["dirty"] else "ندارد"}',
            '',
            'محتوای بسته:',
        ]

        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            zf.write(bundle_path, BUNDLE_NAME)
            lines.append(
                f'  {BUNDLE_NAME:<28} {bundle_path.stat().st_size / 1024:8.1f} KB  '
                f'sha256={_sha256(bundle_path)[:16]}…'
            )

            if db_path is not None:
                zf.write(db_path, f'data/{DB_NAME}')
                lines.append(
                    f'  data/{DB_NAME:<23} {db_path.stat().st_size / 1024:8.1f} KB  '
                    f'sha256={_sha256(db_path)[:16]}…'
                )
                for suffix in ('-wal', '-shm'):
                    sidecar = db_path.with_name(db_path.name + suffix)
                    if sidecar.is_file():
                        zf.write(sidecar, f'data/{DB_NAME}{suffix}')

            for item in backup_files:
                zf.write(item, f'data/{BACKUPS_DIR_NAME}/{item.name}')
            if backup_files:
                total = sum(item.stat().st_size for item in backup_files) / 1024
                lines.append(
                    f'  data/{BACKUPS_DIR_NAME}/  ({len(backup_files)} فایل از {backup_total} پشتیبان موجود، {total:.1f} KB)'
                )
            elif include_db:
                lines.append(f'  data/{BACKUPS_DIR_NAME}/  (خالی — هیچ پشتیبانی در {BACKUPS_DIR_NAME} نبود)')

            lines += [
                f'  {RESTORE_NAME}',
                f'  {MANIFEST_NAME}',
                '',
                'بازیابی سریع (رایانهٔ بدون اینترنت):',
                '  git clone repo.bundle school_management',
                '  copy data\\school.db school_management\\school.db',
                '  xcopy /E /I data\\backups school_management\\backups',
                'شرح کامل: فایل RESTORE_FA.txt داخل همین بسته.',
            ]
            zf.writestr(MANIFEST_NAME, '\n'.join(lines) + '\n')
            zf.writestr(RESTORE_NAME, RESTORE_GUIDE)

    if errors and not quiet:
        for error in errors:
            _say(f'⚠ {error}')
    return archive, ''


def export_database(out_dir: Path) -> tuple[Path | None, str]:
    """فقط یک عکس فوری از دیتابیس (بدون بستهٔ گیت) — سبک و مناسب پشتیبان روزمره."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')
    dest = out_dir / f'school_db_{stamp}.db'
    ok, message = copy_database(dest)
    if not ok:
        return None, message
    return dest, message


def verify_archive(archive: Path, quiet: bool = False) -> bool:
    """سلامت بسته را بررسی می‌کند: بازشدن ZIP، سالم‌بودن قطعه‌ها و هش دیتابیس.

    با ``quiet=True`` فقط True/False برمی‌گرداند و چیزی چاپ نمی‌کند.
    """
    say = (lambda *args, **kwargs: None) if quiet else _say
    if not archive.is_file():
        say(f'✗ فایل پیدا نشد: {archive}')
        return False
    try:
        with zipfile.ZipFile(archive) as zf:
            bad = zf.testzip()
            if bad is not None:
                say(f'✗ قطعهٔ آسیب‌دیده: {bad}')
                return False
            names = set(zf.namelist())
            required = {BUNDLE_NAME, MANIFEST_NAME, RESTORE_NAME}
            missing = required - names
            if missing:
                say(f'✗ قطعه‌های لازم نیستند: {", ".join(sorted(missing))}')
                return False
            manifest = zf.read(MANIFEST_NAME).decode('utf-8', 'replace')
            db_entry = f'data/{DB_NAME}'
            if db_entry in names:
                expected = None
                for line in manifest.splitlines():
                    if line.strip().startswith(db_entry):
                        for part in line.split():
                            if part.startswith('sha256='):
                                expected = part[len('sha256='):].rstrip('…')
                if expected:
                    digest = hashlib.sha256(zf.read(db_entry)).hexdigest()
                    if not digest.startswith(expected):
                        say('✗ هش دیتابیس با مانیفست نمی‌خواند (بستهٔ دست‌کاری‌شده یا آسیب‌دیده).')
                        return False
    except (zipfile.BadZipFile, OSError) as error:
        say(f'✗ بسته باز نشد: {error}')
        return False

    size_mb = archive.stat().st_size / (1024 * 1024)
    say(f'✓ بسته سالم است: {archive.name}  ({size_mb:.2f} MB)')
    return True


# --------------------------------------------------------------------------
# خط فرمان
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='ساخت بستهٔ پشتیبان آفلاین (مخزن + دیتابیس + پشتیبان‌ها) در یک فایل ZIP.',
    )
    parser.add_argument('--output-dir', default=str(DEFAULT_OUT_DIR), help='پوشهٔ خروجی بسته‌ها')
    parser.add_argument(
        '--last', type=int, default=10, metavar='N',
        help='فقط N پشتیبان تازه‌تر (پیش‌فرض ۱۰، صفر = همه)',
    )
    parser.add_argument('--no-db', action='store_true', help='فقط مخزن؛ دیتابیس و پشتیبان‌ها نه')
    parser.add_argument('--db-only', action='store_true', help='فقط عکس فوری دیتابیس (بدون بستهٔ گیت)')
    parser.add_argument('--verify', metavar='ZIP', help='بررسی سالم‌بودن یک بسته (بدون ساخت بستهٔ نو)')
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # چاپ امن روی کنسول‌های ویندوزی
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)

    if args.verify:
        return 0 if verify_archive(Path(args.verify).expanduser()) else 1

    if args.db_only:
        snapshot, note = export_database(Path(args.output_dir).expanduser())
        if snapshot is None:
            _say(f'✗ عکس دیتابیس ساخته نشد: {note}')
            return 1
        if note:
            _say(f'گزارش دیتابیس: {note}')
        _say(f'✓ عکس دیتابیس ساخته شد: {snapshot}  ({snapshot.stat().st_size / 1024:.1f} KB)')
        return 0

    _say('ساخت بستهٔ پشتیبان آفلاین…')
    archive, error = build_archive(
        Path(args.output_dir).expanduser(),
        last_backups=max(0, args.last),
        include_db=not args.no_db,
    )
    if archive is None:
        _say(f'✗ {error}')
        return 1

    _say(f'✓ بسته ساخته شد: {archive}  ({archive.stat().st_size / (1024 * 1024):.2f} MB)')
    _say('  بازیابی روی رایانهٔ بدون اینترنت:')
    _say('    ۱) فایل ZIP را از حالت فشرده خارج کنید')
    _say('    ۲) git clone repo.bundle school_management')
    _say('    ۳) از پوشهٔ استخراج‌شده: copy data\\school.db school_management\\school.db')
    _say('    ۴) cd school_management و بعد python app.py (توضیح کامل در RESTORE_FA.txt داخل بسته)')
    _say(f'  بررسی سلامت: python tools/offline_backup.py --verify "{archive}"')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
