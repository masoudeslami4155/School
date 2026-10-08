from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _stable_secret() -> str:
    provided = os.environ.get('SECRET_KEY', '').strip()
    if provided:
        return provided
    path = BASE_DIR / '.secret_key'
    try:
        if path.exists():
            value = path.read_text(encoding='utf-8').strip()
            if len(value) >= 32:
                return value
        value = secrets.token_hex(32)
        path.write_text(value, encoding='utf-8')
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return value
    except OSError:
        # A read-only installation can still start, but its sessions will reset on restart.
        return secrets.token_hex(32)


class Config:
    SECRET_KEY = _stable_secret()
    # Optional stable, separately managed key; changing it requires re-entering API keys.
    AI_ENCRYPTION_KEY = os.environ.get('AI_ENCRYPTION_KEY', '').strip()
    DATABASE = os.environ.get('DATABASE_PATH') or str(BASE_DIR / 'school.db')
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or str(BASE_DIR / 'static' / 'uploads')
    LOG_DIR = os.environ.get('LOG_DIR') or str(BASE_DIR / 'logs')
    BACKUP_DIR = os.environ.get('BACKUP_DIR') or str(BASE_DIR / 'backups')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = bool(os.environ.get('HTTPS_ENABLED'))
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8
    # School identity is configurable for a local installation, with the
    # requested school and programmer shown by default throughout the UI.
    SCHOOL_NAME = os.environ.get('SCHOOL_NAME') or 'مدرسه استثنایی حمید باخرز'
    PROGRAMMER_NAME = os.environ.get('PROGRAMMER_NAME') or 'مسعود اسلامی'
    CERTIFICATE_SCHOOL_NAME = os.environ.get('CERTIFICATE_SCHOOL_NAME') or 'حمید'
    CERTIFICATE_SCHOOL_CODE = os.environ.get('CERTIFICATE_SCHOOL_CODE') or '55614406'
    CERTIFICATE_EDUCATION_PERIOD = os.environ.get('CERTIFICATE_EDUCATION_PERIOD') or 'ابتدایی استثنایی'
    CERTIFICATE_STUDY_PROGRAM = os.environ.get('CERTIFICATE_STUDY_PROGRAM') or 'آموزش ابتدایی توصیفی برای دانش آموزان کم توان ذهنی'
    CERTIFICATE_DIRECTOR = os.environ.get('CERTIFICATE_DIRECTOR') or 'زهرا قیاسی داللیان'
    APP_VERSION = '۴.۶۴'
