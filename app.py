"""LEXI: run locally with `python app.py`, or use `gunicorn app:app`."""

from datetime import datetime, timedelta, timezone as utc_timezone
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, render_template, request, send_from_directory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from lexi.catalog import load_catalog
from lexi.selection import EPOCH, select_word
from lexi.schedule import daily_schedule
from lexi.database import init_database, local_secret
from lexi.accounts import accounts

ROOT = Path(__file__).resolve().parent


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(LEXI_TIMEZONE=os.environ.get("LEXI_TIMEZONE", "Asia/Bishkek"))
    if test_config:
        app.config.update(test_config)
    instance = Path(app.instance_path)
    instance.mkdir(parents=True, exist_ok=True)
    app.config.setdefault('DATABASE_URL', os.environ.get('DATABASE_URL') or (
        'sqlite:///:memory:' if app.testing else f'sqlite:///{instance / "lexi.sqlite3"}'))
    app.config['SECRET_KEY'] = app.config.get('SECRET_KEY') or os.environ.get('SECRET_KEY') or (
        'test-only-key-not-for-deployment-2026' if app.testing else local_secret(instance))
    app.config.update(
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        SESSION_COOKIE_NAME='lexi_session', SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('LEXI_COOKIE_SECURE') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(days=7), SESSION_REFRESH_EACH_REQUEST=False,
    )
    engine = init_database(app)
    app.extensions['dummy_password_hash'] = generate_password_hash('dummy-password-not-a-user-account', method='scrypt')
    app.register_blueprint(accounts)
    if os.environ.get('LEXI_TRUST_PROXY') == '1':
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    @app.cli.command('init-db')
    def init_db_command():
        """Tables are created safely on startup; this command checks connectivity."""
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        print('Account database is ready.')

    @app.errorhandler(413)
    def too_large(error):
        return jsonify(error='That upload is too large. Choose a photo up to 5 MB.'), 413

    def catalog_response():
        try:
            collections, words, site = load_catalog(ROOT)
            timezone = app.config["LEXI_TIMEZONE"]
            today = datetime.now(ZoneInfo(timezone)).date().isoformat()
            return {"collections": collections, "words": words, "site": site,
                    "timezone": timezone, "today": today, "epoch": EPOCH.isoformat()}
        except (ValueError, ZoneInfoNotFoundError) as error:
            app.logger.error("Vocabulary configuration error: %s", error)
            return None

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/api/catalog")
    def catalog():
        data = catalog_response()
        if data is None:
            return jsonify(error="The vocabulary could not be loaded. Check the JSON data and timezone configuration."), 503
        response = jsonify(data)
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/daily")
    def daily():
        data = catalog_response()
        if data is None:
            return jsonify(error="Vocabulary is unavailable. Check the server log and JSON files."), 503
        selected = request.args.get("collections")
        selected_ids = selected.split(",") if selected is not None else [item["id"] for item in data["collections"]]
        try:
            schedule = daily_schedule(
                datetime.now(utc_timezone.utc), request.args.get("timezone", data["timezone"]),
                request.args.get("update_time", "00:00"),
            )
            word = select_word(data["collections"], data["words"], selected_ids, schedule["date"])
        except ZoneInfoNotFoundError:
            return jsonify(error="Choose a valid IANA timezone, such as Europe/London."), 400
        except ValueError as error:
            return jsonify(error=str(error)), 400
        response = jsonify(word=word, **schedule)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        ready = catalog_response() is not None
        if ready:
            try:
                with engine.connect() as connection:
                    connection.execute(text('SELECT 1'))
            except SQLAlchemyError:
                app.logger.error('The account database is unavailable.')
                ready = False
        return jsonify(status="ok" if ready else "error"), 200 if ready else 503

    @app.get("/sw.js")
    def service_worker():
        response = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/manifest.webmanifest")
    def manifest():
        return send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; "
            "img-src 'self' data: blob:; connect-src 'self'; worker-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)

