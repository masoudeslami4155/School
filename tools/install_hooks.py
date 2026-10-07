#!/usr/bin/env python
"""فعال‌سازی خودکار هوک‌های گیت — سامانهٔ جامع مدیریت مدرسه.

هوک‌ها در پوشهٔ ``tools/git-hooks`` داخل مخزن نگهداری می‌شوند و با تنظیم
``core.hooksPath`` روی همان پوشه فعال می‌گردند. چون این تنظیم «محلیِ» هر
مخزن است و همراه کلون منتقل نمی‌شود، این ابزار همه‌جا به‌صورت خودکار
اجرا می‌شود:

* هنگام شروع برنامه با ``python app.py`` (اگر پروژه Git باشد)
* دستی: ``python tools/install_hooks.py``
* بررسی وضعیت بدون تغییر: ``python tools/install_hooks.py --check``

بنابراین روی هر کلون تازه، و حتی اگر پوشهٔ ``.git`` پاک و از نو ساخته
شود، هوک‌ها بدون هیچ کپی دستی برمی‌گردند. در محیط بدون گیت یا بدون
مخزن، ابزار بی‌صدا کنار می‌رود و هیچ‌وقت اجرای برنامه را نمی‌شکند.

خروجی: کد ۰ یعنی هوک‌ها فعال‌اند؛ کد ۱ یعنی فعال‌سازی انجام نشد.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOOKS_REL = 'tools/git-hooks'  # مسیر هوک‌ها نسبت به ریشهٔ پروژه
HOOK_FILES = ('pre-commit', 'post-checkout')
ROOT = Path(__file__).resolve().parent.parent  # ریشهٔ پروژه (والد پوشهٔ tools)

# چاپ متن فارسی برای کنسول کلاسیک ویندوز (اختیاری؛ اگر نبود، چاپ معمولی)
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from console_text import cprint as _say
except Exception:  # pragma: no cover
    _say = print

ACTIVE_STATUSES = ('ok', 'installed')

MESSAGES = {
    'ok': '✓ هوک‌های گیت از قبل فعال‌اند.',
    'installed': '✓ هوک‌های گیت فعال شدند.',
    'not-active': '✗ هوک‌های گیت فعال نیستند.',
    'no-repo': '⚠ این پوشه یک مخزن گیت نیست؛ هوکی نصب نشد.',
    'no-git': '⚠ فرمان git در این سیستم پیدا نشد؛ هوکی نصب نشد.',
    'conflict': '⚠ core.hooksPath روی مسیر دیگری تنظیم شده؛ دست نزدم (برای اجبار: --force).',
    'error': '⚠ فعال‌سازی هوک‌های گیت ناموفق بود.',
}


# --------------------------------------------------------------------------
# کمکی‌های خالص (بدون وابستگی به گیت)
# --------------------------------------------------------------------------
def _find_repo(start: Path | str) -> tuple[Path | None, Path | None]:
    """ریشهٔ مخزن و پوشهٔ .git را از ``start`` به سمت بالا پیدا می‌کند."""
    start = Path(start).resolve()
    for candidate in (start, *start.parents):
        dot_git = candidate / '.git'
        if dot_git.is_dir():
            return candidate, dot_git
        if dot_git.is_file():  # مخزن‌های worktree/submodule فایل .git دارند
            try:
                marker = dot_git.read_text(encoding='utf-8', errors='replace')
            except OSError:
                return None, None
            _, _, target = marker.partition('gitdir:')
            target = target.strip()
            if not target:
                return None, None
            git_dir = Path(target)
            if not git_dir.is_absolute():
                git_dir = candidate / git_dir
            try:
                return candidate, git_dir.resolve()
            except OSError:
                return None, None
    return None, None


def _config_path(git_dir: Path) -> Path:
    return Path(git_dir) / 'config'


def _read_config(git_dir: Path) -> str:
    try:
        return _config_path(git_dir).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def _local_hooks_path(config_text: str) -> str | None:
    """مقدار core.hooksPath را از متن فایل config بیرون می‌کشد."""
    section = ''
    value = None
    for raw in config_text.splitlines():
        line = raw.strip()
        if not line or line[0] in '#;':
            continue
        if line.startswith('['):
            end = line.find(']')
            section = line[1:end].strip().lower() if end > 0 else ''
            continue
        if '=' not in line:
            continue
        key, _, raw_value = line.partition('=')
        if section == 'core' and key.strip().lower() == 'hookspath':
            value = raw_value.strip().strip('"')
    return value


def _normalize(value: str) -> str:
    return os.path.normcase(value.strip().strip('"').replace('\\', '/').rstrip('/'))


def _same_path(left: str, right: str) -> bool:
    return _normalize(left) == _normalize(right)


def _hooks_dir_value(repo_root: Path | None, project_root: Path | None = None) -> str | None:
    """مسیر نسبی هوک‌ها نسبت به ریشهٔ مخزن (مقدار core.hooksPath)."""
    if repo_root is None:
        return None
    base = Path(project_root) if project_root else ROOT
    hooks_dir = (base / HOOKS_REL).resolve()
    try:
        return hooks_dir.relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:  # پوشهٔ هوک‌ها بیرون از این مخزن است
        return None


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
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _ensure_executable(hooks_dir: Path) -> None:
    """روی سیستم‌های یونیکسی، فایل‌های هوک باید اجراشدنی باشند."""
    if os.name == 'nt':
        return
    for name in HOOK_FILES:
        hook = hooks_dir / name
        try:
            if hook.is_file():
                os.chmod(hook, 0o755)
        except OSError:
            pass


# --------------------------------------------------------------------------
# API اصلی — از هر جایی (مثل app.py) قابل فراخوانی است و هرگز استثنا نمی‌دهد
# --------------------------------------------------------------------------
def ensure_hooks(root: Path | str | None = None, force: bool = False, dry_run: bool = False) -> str:
    """هوک‌های گیت را در صورت نیاز فعال می‌کند و وضعیت را برمی‌گرداند.

    مقادیر بازگشتی: ``ok``، ``installed``، ``not-active``، ``no-repo``،
    ``no-git``، ``conflict`` و ``error``. با ``dry_run=True`` هیچ چیزی
    تغییر نمی‌کند و تنها وضعیت گزارش می‌شود.
    """
    try:
        project_root = (Path(root) if root else ROOT).resolve()
        repo_root, git_dir = _find_repo(project_root)
        if repo_root is None or git_dir is None or repo_root != project_root:
            # این پوشه خودش مخزن نیست؛ به مخزن والد هم دست نمی‌زنیم.
            return 'no-repo'
        hooks_value = _hooks_dir_value(repo_root, project_root)
        if not hooks_value:
            return 'no-repo'
        hooks_dir = project_root / HOOKS_REL

        current = _local_hooks_path(_read_config(git_dir))
        if current is not None:
            if _same_path(current, hooks_value):
                if not dry_run:
                    _ensure_executable(hooks_dir)
                return 'ok'
            if not force:
                return 'conflict'
        elif dry_run:
            return 'not-active'

        result = _run_git(['config', '--local', 'core.hooksPath', hooks_value], repo_root)
        if result is None:
            return 'no-git'
        if result.returncode != 0:
            return 'error'

        installed = _local_hooks_path(_read_config(git_dir))
        if installed is None or not _same_path(installed, hooks_value):
            return 'error'
        _ensure_executable(hooks_dir)
        return 'installed'
    except Exception:  # هر خطای غیرمنتظره‌ای هم نباید برنامه را متوقف کند
        return 'error'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='فعال‌سازی هوک‌های گیت سامانهٔ مدیریت مدرسه (بی‌خطر و تکرارپذیر).',
    )
    parser.add_argument('--check', action='store_true', help='فقط وضعیت را بگو (بدون هیچ تغییر)')
    parser.add_argument('--force', action='store_true', help='حتی اگر core.hooksPath مسیر دیگری بود، بازنویسی کن')
    parser.add_argument('--quiet', action='store_true', help='فقط در صورت شکست چیزی چاپ کن')
    return parser


def _print_details(status: str) -> None:
    hooks_list = '، '.join(HOOK_FILES)
    if status in ACTIVE_STATUSES:
        _say(f'  پوشهٔ هوک‌ها: {HOOKS_REL}  ({hooks_list})')
        _say('  رد کردن اضطراری یک کامیت: SKIP_SMOKE=1 git commit ...')
    elif status == 'conflict':
        repo_root, git_dir = _find_repo(ROOT)
        if git_dir is not None:
            _say(f'  مقدار فعلی core.hooksPath: {_local_hooks_path(_read_config(git_dir))}')
        hooks_value = _hooks_dir_value(repo_root, ROOT) or HOOKS_REL
        _say(f'  برای بازنویسی: python tools/install_hooks.py --force  →  {hooks_value}')


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # چاپ امن روی کنسول‌های ویندوزی
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    status = ensure_hooks(force=args.force, dry_run=args.check)
    active = status in ACTIVE_STATUSES
    if not args.quiet or not active:
        _say(MESSAGES.get(status, MESSAGES['error']))
        _print_details(status)
    return 0 if active else 1


if __name__ == '__main__':
    raise SystemExit(main())
