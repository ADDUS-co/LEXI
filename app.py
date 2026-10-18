"""LEXI: run locally with `python app.py`, or use `gunicorn app:app`."""

from datetime import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, render_template, request, send_from_directory

from lexi.catalog import load_catalog
from lexi.selection import EPOCH, select_word

ROOT = Path(__file__).resolve().parent


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(LEXI_TIMEZONE=os.environ.get("LEXI_TIMEZONE", "Asia/Bishkek"))
    if test_config:
        app.config.update(test_config)

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
            word = select_word(data["collections"], data["words"], selected_ids, data["today"])
        except ValueError as error:
            return jsonify(error=str(error)), 400
        response = jsonify(word=word, date=data["today"], timezone=data["timezone"])
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        ready = catalog_response() is not None
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
            "img-src 'self' data:; connect-src 'self'; worker-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)

