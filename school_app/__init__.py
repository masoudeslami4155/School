from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask

from config import Config
from .database import auto_backup, init_db
from .template_helpers import register_template_helpers
from .security import register_security
from .routes import (auth, students, teachers, attendance, finance, management, calendar, reports,
                     student_ages, contacts, data_quality, support, student_columns, meetings,
                     print_layouts, report_print_layouts, student_certificates, ai_documents, ai_agent, preferences)


def configure_logging(app: Flask) -> None:
    log_dir = Path(app.config['LOG_DIR'])
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    app_handler = RotatingFileHandler(log_dir / 'app.log', maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
    app_handler.setFormatter(formatter)
    app_handler.setLevel(logging.INFO)
    error_handler = RotatingFileHandler(log_dir / 'error.log', maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    app.logger.handlers.clear()
    app.logger.addHandler(app_handler)
    app.logger.addHandler(error_handler)
    app.logger.setLevel(logging.INFO)


def create_app() -> Flask:
    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
    app.config.from_object(Config)
    app.secret_key = app.config['SECRET_KEY']
    Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
    configure_logging(app)
    with app.app_context():
        auto_backup()
        init_db()
    register_template_helpers(app)
    register_security(app)
    for module in (auth, students, teachers, attendance, finance, management, calendar, reports, student_ages, contacts, data_quality, support, student_columns, meetings, student_certificates, ai_documents, ai_agent, preferences):
        module.register(app)
    print_layouts.register(app)
    report_print_layouts.register(app)
    return app


app = create_app()
