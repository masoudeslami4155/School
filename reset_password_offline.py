"""Offline emergency password reset for the school application.

Run this file on the same computer as school.db. It never sends a password
or recovery code over a network and never puts the new password in the shell
arguments or in the database as plain text.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from datetime import datetime
from getpass import getpass
from pathlib import Path

from werkzeug.security import generate_password_hash


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="بازنشانی آفلاین رمز سامانه مدرسه")
    parser.add_argument("--database", default=os.environ.get("DATABASE_PATH", str(ROOT / "school.db")))
    args = parser.parse_args()
    database = Path(args.database).expanduser().resolve()
    if not database.exists():
        print(f"فایل دیتابیس پیدا نشد: {database}")
        return 2

    personnel = input("شماره پرسنلی کاربر: ").strip()
    if not personnel:
        print("شماره پرسنلی الزامی است.")
        return 2
    password = getpass("رمز جدید (حداقل ۸ کاراکتر): ")
    repeat = getpass("تکرار رمز جدید: ")
    if len(password) < 8 or password != repeat:
        print("رمز باید حداقل ۸ کاراکتر باشد و با تکرار آن یکسان باشد.")
        return 2

    backup_dir = Path(os.environ.get("BACKUP_DIR", str(ROOT / "backups"))).expanduser()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"school_before_offline_reset_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(database, backup)

    try:
        with sqlite3.connect(database, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            user = conn.execute(
                "SELECT id, full_name, role, is_active FROM users WHERE personnel_number=?",
                (personnel,),
            ).fetchone()
            if not user:
                print("کاربری با این شماره پرسنلی پیدا نشد.")
                return 1
            if not user["is_active"]:
                print("این کاربر غیرفعال است؛ ابتدا دسترسی او را فعال کنید.")
                return 1
            conn.execute(
                "UPDATE users SET password_hash=?, must_change_password=1 WHERE id=?",
                (generate_password_hash(password), user["id"]),
            )
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='recovery_codes'"
            ).fetchone():
                conn.execute(
                    "UPDATE recovery_codes SET used_at=datetime('now') WHERE user_id=? AND used_at IS NULL",
                    (user["id"],),
                )
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='password_recovery_attempts'"
            ).fetchone():
                conn.execute("DELETE FROM password_recovery_attempts WHERE lookup_key=?", (personnel,))
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_log'"
            ).fetchone():
                conn.execute(
                    "INSERT INTO audit_log(actor_user_id,action,entity_type,entity_id,details,created_at) VALUES(NULL,?,?,?,?,datetime('now'))",
                    ("offline_password_reset", "user", str(user["id"]), "physical local recovery"),
                )
            conn.commit()
    except sqlite3.Error as exc:
        print("بازنشانی انجام نشد؛ نسخه پشتیبان حفظ شد.")
        print(f"جزئیات فنی: {exc}")
        return 1

    print(f"رمز کاربر «{user['full_name']}» با موفقیت بازنشانی شد.")
    print("کاربر باید در اولین ورود رمز را تغییر دهد.")
    print(f"نسخه پشتیبان: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
