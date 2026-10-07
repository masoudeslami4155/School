#!/usr/bin/env python
"""Restore Center (Bazyabi) - School Management System.

Bazyabi az hame-ye manabe-e momken:
  1) baste-ye ZIP-e akhar dar offline_backups/
  2) file-e ZIP ya pooshe-ye delkhah (USB, network, ...)
  3) jostojoo-ye khodkar: flash/USB/OneDrive
  4) faghat DB az pooshe-ye backups/
  5) code az repo.bundle
  6) code az GitHub (online, git pull --ff-only)
  7) gozaresh-e vaziyat va check-e baste ha
  8) rahnama-ye dasti

Hame-ye matn-ha be Finglish neveshte shodeand ta dar har console-i
(Windows Terminal, cmd, VS Code, even redirected output) dorost dideh
shavand; hich niyazi be arabic-reshaper / python-bidi nist.

Nemune-ha::

    python tools/restore_center.py                  # menu-ye karbari
    python tools/restore_center.py --status         # gozaresh-e vaziyat
    python tools/restore_center.py --list           # manabe-e peyda shode
    python tools/restore_center.py --package <zip>  # bazyabi az baste
    python tools/restore_center.py --dir <path>     # ZIP ya pooshe
    python tools/restore_center.py --db <file.db>   # faghat DB
    python tools/restore_center.py --bundle <file>  # code az bundle
    python tools/restore_center.py --online         # code az GitHub
    python tools/restore_center.py --print-steps    # rahnama-ye dasti

Kod-e khoruj: 0 = movafagh, 1 = khatta (khatta-ha dar logs/restore_tool.log).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / 'tools'
for _entry in (str(TOOLS), str(ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import offline_backup as engine  # noqa: E402

DB_NAME = 'school.db'
BACKUPS_DIR = ROOT / 'backups'
PACKAGES_DIR = ROOT / 'offline_backups'
LOG_FILE = ROOT / 'logs' / 'restore_tool.log'
DRIVE_LETTERS = 'DEFGHIJKL'
INTERACTIVE = True

MANUAL_STEPS = (
    '  RAHNAMA-YE DASTI (bazyabi-e kamel):',
    '',
    '  1) file-e ZIP ra baz konid (Rast-click > Extract All)',
    '  2) dar pooshe-ye extract shode:',
    '       git clone repo.bundle school_management',
    '  3) data ra bargardanid (az pooshe-ye extract shode):',
    '       copy data\\school.db school_management\\school.db',
    '       xcopy /E /I data\\backups school_management\\backups',
    '  4) agar school.db-wal ya school.db-shm vojood darad, pak konid',
    '  5) barnameh ra ejra konid:',
    '       cd school_management',
    '       python app.py',
    '',
    '  Nokte: hook-ha-ye git khodkar faal mishavand; agar rooye in',
    '  rayeaneh ham commit mizanid, yek bar identity ra set konid:',
    '       git config user.name "Masoud Eslami"',
    '       git config user.email "you@example.com"',
)


# --------------------------------------------------------------------------
# Abzar-ha-ye komaki
# --------------------------------------------------------------------------
def log(message: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open('a', encoding='utf-8') as handle:
            handle.write(f'[{datetime.now().isoformat(timespec="seconds")}] {message}\n')
    except OSError:
        pass


def ask(question: str) -> bool:
    if not INTERACTIVE:
        return True
    answer = input(f'  {question} (y/N): ').strip().lower()
    return answer in ('y', 'yes', 'b', 'bal', 'bale')


def pause() -> None:
    if INTERACTIVE:
        input('  Enter bezanid... ')


def human(size: float) -> str:
    if size >= 1024 ** 3:
        return f'{size / 1024 ** 3:.2f} GB'
    if size >= 1024 ** 2:
        return f'{size / 1024 ** 2:.2f} MB'
    return f'{size / 1024:.1f} KB'


def stamp() -> str:
    return datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')


# --------------------------------------------------------------------------
# Shenasayi-e manabe
# --------------------------------------------------------------------------
def packages_in(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(folder.glob('*.zip'), key=lambda item: item.stat().st_mtime, reverse=True)


def external_roots() -> list[Path]:
    """Flash/USB/OneDrive/pooshe-ye zakhireshode - baraye jostojoo."""
    roots: list[Path] = []
    for letter in DRIVE_LETTERS:
        candidate = Path(f'{letter}:\\school_backups')
        try:
            if candidate.is_dir():
                roots.append(candidate)
        except OSError:
            continue
    onedrive = os.environ.get('OneDrive')
    if onedrive:
        candidate = Path(onedrive) / 'school_backups'
        try:
            if candidate.is_dir():
                roots.append(candidate)
        except OSError:
            pass
    return roots


def find_external_packages() -> list[Path]:
    found: list[Path] = []
    for root in external_roots():
        for item in packages_in(root):
            found.append(item)
        try:  # bundle-e bedoon-e ZIP ham ghabele estefade ast
            found.extend(path for path in root.glob('repo.bundle') if path.is_file())
        except OSError:
            continue
    found.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return found


def describe_package(archive: Path) -> str:
    """Yek khat-e khobasan-e baste: tarikh, file-ha va check-e DB."""
    try:
        size = human(archive.stat().st_size)
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            has_db = f'data/{DB_NAME}' in names
            backups = sum(1 for name in names if name.startswith(f'data/backups/'))
            has_bundle = 'repo.bundle' in names
        parts = [f'{archive.name} ({size})']
        parts.append('code+bundle' if has_bundle else 'bedoon-e bundle')
        parts.append('DB' if has_db else 'bedoon-e DB')
        if backups:
            parts.append(f'{backups} backup')
        return ' | '.join(parts)
    except (zipfile.BadZipFile, OSError) as error:
        return f'{archive.name} (kharab: {error})'


# --------------------------------------------------------------------------
# DB: check, snapshot-e amni, jaygozini
# --------------------------------------------------------------------------
def _open_readonly(path: Path) -> sqlite3.Connection:
    """Baz-kardan-e DB-e khoundani.

    Baraye DB-ha-ye WAL, SQLite dar halat-e read-only be file-e -shm niyaz
    darad; agar nasazad, be halat-e read-write bar migardim.
    """
    uri = f'{path.resolve().as_uri()}?mode=ro'
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return sqlite3.connect(str(path))


def database_report(path: Path) -> str:
    """Gozaresh-e ASCII az yek DB: integrity, tedad-e jadval va radif."""
    try:
        connection = _open_readonly(path)
        try:
            integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            total = 0
            for (table,) in tables:
                total += connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            students = users = 0
            for (table,) in tables:
                if table == 'students':
                    students = connection.execute('SELECT COUNT(*) FROM students').fetchone()[0]
                if table == 'users':
                    users = connection.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        finally:
            connection.close()
        return (f'integrity={integrity} | tables={len(tables)} | rows={total} | '
                f'students={students} | users={users}')
    except sqlite3.Error as error:
        return f'KHATTA dar khandan-e DB: {error}'


def is_locked(path: Path) -> bool:
    """Agar file ghafel bashad (barnameh dar hal-e ejra), True."""
    if not path.exists():
        return False
    try:
        with path.open('r+b'):
            return False
    except OSError:
        return True


def safety_snapshot(target: Path) -> Path | None:
    """Az DB-e feli yek backup-e amni migirad (ghabl az jaygozini)."""
    if not target.exists():
        return None
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    destination = PACKAGES_DIR / f'pre_restore_{stamp()}.db'
    ok, message = engine.copy_database(destination)
    if not ok:
        print(f'  [!] Backup-e amni sakhteh nashod: {message}')
        return None
    print(f'  [i] Backup-e amni sakhte shod: {destination.name} '
          f'({human(destination.stat().st_size)})')
    return destination


def restore_database(source_db: Path, also_backups: Path | None = None) -> bool:
    """DB ra az source jaygozin mikonad (ba backup-e amni va pak-kardan-e wal)."""
    target = ROOT / DB_NAME
    if is_locked(target):
        print('  [X] school.db ghafel ast; ehtemalan barnameh dar hal-e ejrast.')
        print('      Avval barnameh ra bebandid, pas az pooshe-ye project python app.py ra ejra konid.')
        return False
    if not source_db.is_file():
        print(f'  [X] file-e DB peyda nashod: {source_db}')
        return False

    print(f'  [i] DB-e manba: {source_db.name} | {database_report(source_db)}')
    if target.exists():
        print(f'  [i] DB-e feli : {database_report(target)}')
        safety_snapshot(target)

    try:
        shutil.copy2(source_db, target)
    except OSError as error:
        print(f'  [X] Jaygozini-e DB anjam nashod: {error}')
        return False

    for suffix in ('-wal', '-shm'):  # file-ha-ye jani-e DB-e ghadimi
        sidecar = target.with_name(target.name + suffix)
        try:
            if sidecar.exists():
                sidecar.unlink()
                print(f'  [i] file-e ghadimi pak shod: {sidecar.name}')
        except OSError:
            pass

    print(f'  [OK] DB jaygozin shod: {ROOT / DB_NAME}')
    print(f'  [i] vaziyat-e DB-e jadid: {database_report(target)}')
    log(f'OK: DB restored from {source_db.name} -> {database_report(target)}')

    if also_backups and also_backups.is_dir():
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        copied = skipped = 0
        for item in sorted(also_backups.glob('*')):
            destination = BACKUPS_DIR / item.name
            if destination.exists():
                skipped += 1
                continue
            try:
                shutil.copy2(item, destination)
                copied += 1
            except OSError:
                pass
        print(f'  [i] backups: {copied} file ezafe shod, {skipped} file az ghabl bood')
    return True


# --------------------------------------------------------------------------
# Baste-ye ZIP: bazyabi-e data (+ code)
# --------------------------------------------------------------------------
def restore_from_package(archive: Path, data_only: bool = False, code_only: bool = False,
                         target: Path | None = None) -> bool:
    print(f'\n=== Bazyabi az baste: {archive.name} ===')
    if not archive.is_file():
        print(f'  [X] file peyda nashod: {archive}')
        return False
    if not _package_ok(archive):
        return False

    with tempfile.TemporaryDirectory(prefix='school_restore_') as temp_dir:
        temp = Path(temp_dir)
        try:
            with zipfile.ZipFile(archive) as zf:
                _safe_extract(zf, temp)
        except (ValueError, zipfile.BadZipFile, OSError) as error:
            print(f'  [X] Baz-kardan-e baste momken nashod: {error}')
            return False

        data_dir = temp / 'data'
        package_db = data_dir / DB_NAME
        package_backups = data_dir / 'backups'
        bundle = temp / 'repo.bundle'

        ok = True
        if not code_only:
            if package_db.is_file():
                ok = restore_database(package_db, package_backups) and ok
            else:
                print('  [!] in baste DB nadarad; faghat code ghabele bazyabi ast.')
                ok = False

        if not data_only:
            if bundle.is_file():
                print('\n  --- code az repo.bundle ---')
                ok = restore_code_from_bundle(bundle, target) and ok
            else:
                print('  [!] in baste repo.bundle nadarad; faghat data bargasht.')
        print('\n  [i] Bad az bazyabi: az pooshe-ye project python app.py ra ejra konid.')
    return ok


def _package_ok(archive: Path) -> bool:
    """Check-e salamat-e baste (be jaye engine.verify_archive-e Parsi-goo)."""
    if engine.verify_archive(archive, quiet=True):
        print('  [OK] Baste salem ast (ZIP va hash-e DB dorost ast).')
        return True
    print('  [X] Baste salem nist ya hash-e DB nemikhanad; bazyabi motevaghef shod.')
    return False


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    """Extract a ZIP without allowing traversal or symlink entries."""
    root = destination.resolve()
    for member in archive.infolist():
        name = (member.filename or '').replace('\\', '/')
        relative = Path(name)
        if not name or relative.is_absolute() or '..' in relative.parts:
            raise ValueError(f'مسیر ناامن داخل بسته: {member.filename!r}')

        target = (destination / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise ValueError(f'مسیر خارج از پوشهٔ استخراج: {member.filename!r}') from error

        mode = (member.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise ValueError(f'لینک نمادین داخل بسته مجاز نیست: {member.filename!r}')

        if member.is_dir() or name.endswith('/'):
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, target.open('wb') as output:
            shutil.copyfileobj(source, output)


# --------------------------------------------------------------------------
# Code: bundle / GitHub
# --------------------------------------------------------------------------
def restore_code_from_bundle(bundle: Path, target: Path | None = None) -> bool:
    bundle = Path(bundle).expanduser().resolve()
    if not bundle.is_file():
        print(f'  [X] bundle peyda nashod: {bundle}')
        return False
    git = shutil.which('git')
    if not git:
        print('  [X] git dar in system peyda nashod.')
        return False

    if target is None:
        target = ROOT.parent / f'{ROOT.name}_restored_{stamp()}'
    else:
        target = Path(target).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        print(f'  [X] pooshe-ye maghsad khali nist: {target}')
        return False

    result = subprocess.run(
        [git, 'clone', str(bundle), str(target)],
        cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    if result.returncode != 0:
        print(f'  [X] clone az bundle anjam nashod: {(result.stderr or "").strip()}')
        return False

    commits = subprocess.run(
        [git, '-C', str(target), 'rev-list', '--count', 'HEAD'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
    ).stdout.strip()
    print(f'  [OK] code bazyaft shod: {target}  (commits={commits})')
    log(f'OK: code restored from {bundle.name} -> {target} (commits={commits})')
    return True


def restore_code_online() -> bool:
    git = shutil.which('git')
    if not git:
        print('  [X] git dar in system peyda nashod.')
        return False
    fetch = subprocess.run([git, 'fetch', 'origin'], cwd=str(ROOT))
    if fetch.returncode != 0:
        print('  [X] git fetch anjam nashod (internet ya origin ra check konid).')
        return False
    pull = subprocess.run([git, 'pull', '--ff-only'], cwd=str(ROOT))
    if pull.returncode != 0:
        print('  [!] git pull --ff-only anjam nashod; shayad shakheh-e mahalli joda shode ast.')
        print('      Baraye didan-e vaziyat: git status  |  Baraye reset-e kamel: git reset --hard origin/main')
        return False
    print('  [OK] code az GitHub be-rooz shod (fast-forward).')
    log('OK: code updated from origin (fast-forward)')
    return True


# --------------------------------------------------------------------------
# Bazyabi az pooshe ya file-e delkhah
# --------------------------------------------------------------------------
def handle_path(path: Path, data_only: bool = False, code_only: bool = False,
                target: Path | None = None) -> bool:
    """ZIP / bundle / pooshe-ye data - be soorat-e khodkar tashkhis midahad."""
    if path.is_dir():
        for candidate in (path / 'offline_backups', path):
            found = packages_in(candidate)
            if found:
                print(f'  [i] {len(found)} baste dar {candidate} peyda shod.')
                return restore_from_package(found[0], data_only, code_only, target)
        bundle = path / 'repo.bundle'
        if bundle.is_file():
            return restore_code_from_bundle(bundle, target)
        db_file = path / DB_NAME
        if db_file.is_file():
            return restore_database(db_file, path / 'backups')
        print(f'  [X] dar in pooshe baste, bundle ya DB peyda nashod: {path}')
        return False

    suffix = path.suffix.lower()
    if suffix == '.zip':
        return restore_from_package(path, data_only, code_only, target)
    if suffix == '.bundle' or path.name == 'repo.bundle':
        return restore_code_from_bundle(path, target)
    if suffix == '.db':
        return restore_database(path)
    print(f'  [X] no-e file shenakhte nashod: {path.name}')
    return False


def choose_from_list(items: list[Path], describe) -> Path | None:
    if not items:
        print('  [!] chizi peyda nashod.')
        return None
    for index, item in enumerate(items[:9], start=1):
        print(f'    [{index}] {describe(item)}')
    if not INTERACTIVE:
        return items[0]
    choice = input('  Shomare (Enter = 1): ').strip()
    if not choice:
        return items[0]
    if choice.isdigit() and 1 <= int(choice) <= min(9, len(items)):
        return items[int(choice) - 1]
    print('  [!] shomare-e namotabar; avvalin mored entekhab shod.')
    return items[0]


# --------------------------------------------------------------------------
# Gozaresh
# --------------------------------------------------------------------------
def show_status() -> bool:
    print('\n--- Vaziyat-e project ---')
    print(f'  Pooshe : {ROOT}')
    print(f'  DB     : {"vojood darad" if (ROOT / DB_NAME).exists() else "nadarad"}')
    if (ROOT / DB_NAME).exists():
        print(f'  DB info: {database_report(ROOT / DB_NAME)}')
    if BACKUPS_DIR.is_dir():
        files = list(BACKUPS_DIR.glob('*'))
        total = sum(item.stat().st_size for item in files)
        print(f'  backups/: {len(files)} file ({human(total)})')
    local = packages_in(PACKAGES_DIR)
    print(f'  offline_backups/: {len(local)} baste')
    for item in local[:3]:
        print(f'      {describe_package(item)}')
    external = find_external_packages()
    if external:
        print(f'  Manabe-e birooni: {len(external)} mored')
        for item in external[:3]:
            print(f'      {item}')
    else:
        print('  Manabe-e birooni (USB/OneDrive): peyda nashod')
    print(f'  Faz-e azad: {human(shutil.disk_usage(ROOT).free)}')
    lock = 'GHafel (barnameh ejra ast?)' if is_locked(ROOT / DB_NAME) else 'azad'
    print(f'  school.db: {lock}')
    return True


# --------------------------------------------------------------------------
# Menu
# --------------------------------------------------------------------------
MENU = (
    ('1', 'Bazyabi az akharin baste-ye ZIP (offline_backups/)', 'data + code'),
    ('2', 'Bazyabi az file-e ZIP ya pooshe-ye delkhah', 'ZIP / folder'),
    ('3', 'Jostojoo-ye khodkar dar USB / OneDrive', 'auto scan'),
    ('4', 'Bazyabi-e faghat-DB az pooshe-ye backups/', 'file-e .db'),
    ('5', 'Bazyabi-e code az repo.bundle', 'git clone'),
    ('6', 'Bazyabi-e code az GitHub (online)', 'git pull'),
    ('7', 'Gozaresh-e vaziyat va check-e baste ha', 'status'),
    ('8', 'Rahnama-ye dasti-e bazyabi', 'manual steps'),
    ('0', 'Khoruj', 'exit'),
)


def interactive() -> int:
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print('=' * 66)
        print('  School Management  -  RESTORE CENTER  (Bazyabi)')
        print('=' * 66)
        print(f'  Pooshe: {ROOT}')
        print(f'  Zaman : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        print('')
        for key, title, hint in MENU:
            print(f'  [{key}] {title}   -   {hint}')
        print('')
        choice = input('  Shomare ra bezanid va Enter: ').strip()
        if choice == '0':
            print('  Khoro oj! (log: logs/restore_tool.log)')
            return 0
        try:
            if choice == '1':
                local = packages_in(PACKAGES_DIR)
                picked = choose_from_list(local, describe_package)
                if picked and ask(f'Bazyabi az {picked.name}? (DB jaygozin mishavad)'):
                    print('  [OK]' if restore_from_package(picked) else '  [X] Bazyabi-e nakam')
            elif choice == '2':
                raw = input('  Masir-e ZIP ya pooshe: ').strip().strip('"')
                if raw and ask('Bazyabi az in masir?'):
                    print('  [OK]' if handle_path(Path(raw)) else '  [X] Bazyabi-e nakam')
            elif choice == '3':
                found = find_external_packages()
                picked = choose_from_list(found, describe_package)
                if picked and ask(f'Bazyabi az {picked.name}?'):
                    print('  [OK]' if handle_path(picked) else '  [X] Bazyabi-e nakam')
            elif choice == '4':
                files = sorted(BACKUPS_DIR.glob('*.db'),
                               key=lambda item: item.stat().st_mtime, reverse=True) \
                    if BACKUPS_DIR.is_dir() else []
                picked = choose_from_list(
                    files, lambda item: f'{item.name} ({human(item.stat().st_size)})')
                if picked and ask(f'DB az {picked.name} bargardandeh shavad?'):
                    print('  [OK]' if restore_database(picked) else '  [X] Bazyabi-e nakam')
            elif choice == '5':
                raw = input('  Masir-e repo.bundle (Enter = jostojoo): ').strip().strip('"')
                bundle = Path(raw) if raw else None
                if bundle is None:
                    candidates = [item for item in
                                  (PACKAGES_DIR / 'repo.bundle',) + tuple(
                                      root / 'repo.bundle' for root in external_roots())
                                  if item.is_file()]
                    bundle = choose_from_list(
                        list(candidates), lambda item: f'{item} ({human(item.stat().st_size)})')
                if bundle and ask('Code dar pooshe-ye jadid bazyaft shavad?'):
                    print('  [OK]' if restore_code_from_bundle(bundle) else '  [X] Bazyabi-e nakam')
            elif choice == '6':
                if ask('Code az GitHub be-rooz shavad? (git pull --ff-only)'):
                    print('  [OK]' if restore_code_online() else '  [X] Bazyabi-e nakam')
            elif choice == '7':
                show_status()
            elif choice == '8':
                print('\n'.join(MANUAL_STEPS))
            else:
                print('  [!] Shomare-e namotabar.')
        except KeyboardInterrupt:
            print('\n  [i] laghv shod.')
        pause()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Restore Center - bazyabi az baste, USB, DB, bundle ya GitHub.',
    )
    parser.add_argument('--package', metavar='ZIP', help='bazyabi az yek baste-ye ZIP')
    parser.add_argument('--dir', metavar='PATH', help='ZIP, bundle ya pooshe-ye data')
    parser.add_argument('--db', metavar='FILE', help='faghat DB ra bargardan')
    parser.add_argument('--bundle', metavar='FILE', help='code az repo.bundle')
    parser.add_argument('--online', action='store_true', help='code az GitHub (git pull --ff-only)')
    parser.add_argument('--status', action='store_true', help='gozaresh-e vaziyat')
    parser.add_argument('--list', action='store_true', help='fehrest-e manabe')
    parser.add_argument('--print-steps', action='store_true', help='rahnama-ye dasti')
    parser.add_argument('--target', metavar='DIR', help='pooshe-ye maghsad baraye code')
    parser.add_argument('--data-only', action='store_true', help='faghat data')
    parser.add_argument('--code-only', action='store_true', help='faghat code')
    parser.add_argument('--yes', action='store_true', help='biresun-e taeid-ha')
    return parser


def main(argv: list[str] | None = None) -> int:
    global INTERACTIVE
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    if args.data_only and args.code_only:
        print('  [X] --data-only و --code-only را هم‌زمان استفاده نکنید.')
        return 1
    given = (args.package, args.dir, args.db, args.bundle, args.online,
             args.status, args.list, args.print_steps)
    if not any(given):
        INTERACTIVE = True
        try:
            return interactive()
        except KeyboardInterrupt:
            print('\n  [i] Khoro oj.')
            return 0

    INTERACTIVE = False
    target = Path(args.target) if args.target else None
    ok = True

    if args.print_steps:
        print('\n'.join(MANUAL_STEPS))
        return 0
    if args.status:
        return 0 if show_status() else 1
    if args.list:
        print('Baste-ha dar ' + str(PACKAGES_DIR) + ':')
        for item in packages_in(PACKAGES_DIR):
            print('  - ' + describe_package(item))
        external = find_external_packages()
        print(f'Manabe-e birooni ({len(external)} mored):')
        for item in external:
            print('  - ' + describe_package(item))
        return 0
    if args.package:
        ok = restore_from_package(Path(args.package), args.data_only, args.code_only, target)
    if args.dir:
        ok = handle_path(Path(args.dir), args.data_only, args.code_only, target) and ok
    if args.db:
        ok = restore_database(Path(args.db)) and ok
    if args.bundle:
        ok = restore_code_from_bundle(Path(args.bundle), target) and ok
    if args.online:
        ok = restore_code_online() and ok

    print('\n[i] Natije: ' + ('movafagh' if ok else 'nakam') + '  (log: logs/restore_tool.log)')
    log(('OK: ' if ok else 'FAILED: ') + ' '.join(argv or sys.argv[1:]))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
