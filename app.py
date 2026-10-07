from __future__ import annotations

import importlib.util
import os
import socket
import webbrowser
import threading
from pathlib import Path

from school_app import app
from school_app.database import auto_backup


def sync_git_hooks() -> None:
    """هوک‌های گیت را در صورت نیاز فعال می‌کند (روی کلون تازه یا .git از‌نوساخته).

    این کار کاملاً اختیاری و بی‌خطر است: اگر گیت، مخزن یا ابزار نصب نباشد،
    بی‌صدا رد می‌شود و هیچ‌وقت مانع اجرای برنامه نمی‌گردد.
    """
    try:
        installer = Path(__file__).resolve().parent / 'tools' / 'install_hooks.py'
        spec = importlib.util.spec_from_file_location('school_install_hooks', installer)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if module.ensure_hooks() == 'installed':
            print('Git hooks activated: tools/git-hooks (pre-commit, post-checkout)')
    except Exception:
        pass


def get_local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('8.8.8.8', 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return '127.0.0.1'


def open_browser():
    webbrowser.open('http://127.0.0.1:5000')


if __name__ == '__main__':
    sync_git_hooks()
    auto_backup()
    port = int(os.environ.get('PORT', 5000))
    if os.environ.get('RENDER') or os.environ.get('PORT'):
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    else:
        print('=' * 60)
        print('School Management System started successfully!')
        print('Local address: http://127.0.0.1:5000')
        print(f'Network address: http://{get_local_ip()}:5000')
        print('=' * 60)
        
        threading.Timer(1.5, open_browser).start()
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
