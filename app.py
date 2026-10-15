"""EventRank backend: the file that starts everything.

Run it from the backend folder:   python app.py
Then open:                        http://127.0.0.1:5000/health
"""
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

import config
from db import get_db
from routes.auth import bp as auth_bp
from routes.checkins import bp as checkins_bp
from routes.events import bp as events_bp
from routes.reviews import bp as reviews_bp


def create_app():
    app = Flask(__name__)

    # Reject huge request bodies (our biggest request is a short review).
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB

    if config.using_default_secret():
        raise RuntimeError("QR_SECRET must contain at least 32 characters.")
    if "*" in config.CORS_ALLOWED_ORIGINS:
        raise RuntimeError("CORS_ALLOWED_ORIGINS must list trusted origins explicitly.")

    CORS(app, origins=config.CORS_ALLOWED_ORIGINS)

    # Each blueprint is one group of URLs, defined in its own file in routes/.
    app.register_blueprint(auth_bp)       # /auth/signup, /auth/login
    app.register_blueprint(events_bp)     # /events ...
    app.register_blueprint(reviews_bp)    # /events/<id>/reviews, /insights
    app.register_blueprint(checkins_bp)   # /events/<id>/qr.png, /checkin

    # Friendly warnings in the terminal if .env isn't set up properly.
    missing = config.missing_settings()
    if missing:
        app.logger.warning("Missing Supabase settings in backend/.env.local: %s", ", ".join(missing))
    register_health_routes(app)
    register_frontend_routes(app)
    register_error_handlers(app)
    return app


def register_frontend_routes(app):
    import os
    from flask import send_from_directory
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

    @app.get("/")
    @app.get("/frontend")
    @app.get("/frontend/")
    def index():
        return send_from_directory(frontend_dir, "index.html")

    @app.get("/frontend/<path:filename>")
    def frontend_files(filename):
        return send_from_directory(frontend_dir, filename)


def register_health_routes(app):
    @app.get("/health")
    def health():
        """Is the server running?"""
        return jsonify({"status": "ok"})

    @app.get("/health/db")
    def health_db():
        """Can the server reach Supabase? Handy when setting up your .env."""
        try:
            get_db().table("events").select("id").limit(1).execute()
        except RuntimeError as err:          # .env values missing
            return jsonify({"database": "not configured", "error": str(err)}), 503
        except Exception as err:             # wrong key, wrong URL, table missing...
            return jsonify({"database": "unreachable", "error": str(err)}), 503
        return jsonify({"database": "ok"})


def register_error_handlers(app):
    """Every error comes back as JSON like {"error": "..."}, so the frontend
    can always show err.message (never an HTML error page)."""

    @app.errorhandler(HTTPException)
    def http_error(err):
        # 404 not found, 405 wrong method, 413 body too large ...
        return jsonify({"error": err.description}), err.code

    @app.errorhandler(RuntimeError)
    def setup_error(err):
        # Raised by db.py when Supabase configuration is unavailable.
        return jsonify({"error": str(err)}), 503

    @app.errorhandler(Exception)
    def unexpected_error(err):
        app.logger.exception("Unexpected error")  # full details go to the terminal
        return jsonify({"error": "Something went wrong on the server"}), 500


app = create_app()

if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=5000)