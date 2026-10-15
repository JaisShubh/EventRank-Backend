"""Settings for the EventRank backend, in one place.

Secrets belong in ignored backend/.env.local, never in code or tracked files.
Every other file asks this file for what it needs:
    import config   ->   config.SUPABASE_URL
"""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Reads backend/.env.local first so local overrides take precedence, then
# backend/.env, no matter which folder you run from.
# "utf-8-sig" also copes with the invisible marker some Windows editors (like
# old Notepad) put at the start of a file, which would otherwise break the first line.
load_dotenv(os.path.join(BASE_DIR, ".env.local"), encoding="utf-8-sig")
load_dotenv(os.path.join(BASE_DIR, ".env"), encoding="utf-8-sig")


def _text(name, default=""):
    """A setting from .env as text, with stray spaces removed."""
    return os.getenv(name, default).strip()


def _number(name, default):
    """A setting from .env as a whole number. Falls back to the default if it isn't one."""
    try:
        return int(_text(name, str(default)))
    except ValueError:
        return default


# ---- Supabase (database + login) ----
SUPABASE_URL = _text("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = _text("SUPABASE_KEY")  # the service_role / secret key: backend only!

# ---- Check-in QR codes ----
QR_SECRET = _text("QR_SECRET")  # required; use a long, random value
QR_WINDOW_SECONDS = 30                                # a QR code stays valid for about this long
VENUE_RADIUS_METERS = _number("VENUE_RADIUS_METERS", 300)      # how close you must be to check in
EARLY_CHECKIN_MINUTES = _number("EARLY_CHECKIN_MINUTES", 30)   # check-in opens this long before the start

# ---- Frontend ----
# The address the frontend is served from. The QR code links to a page on it.
FRONTEND_URL = _text("FRONTEND_URL", "http://127.0.0.1:5500/frontend").rstrip("/")
CORS_ALLOWED_ORIGINS = tuple(
    origin.strip().rstrip("/")
    for origin in _text(
        "CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:5000,http://localhost:5000,http://127.0.0.1:5500,http://localhost:5500",
    ).split(",")
    if origin.strip()
)

# ---- Sign-up rules ----
# Optional: only allow one email domain to sign up, e.g. "college.edu". Empty = anyone.
ALLOWED_EMAIL_DOMAIN = _text("ALLOWED_EMAIL_DOMAIN").lower().lstrip("@")


# ---- Checks used at startup ----
def missing_settings():
    """Names of required Supabase settings that are empty in local config."""
    required = {"SUPABASE_URL": SUPABASE_URL, "SUPABASE_KEY": SUPABASE_KEY}
    return [name for name, value in required.items() if not value]


def using_default_secret():
    """True if QR_SECRET is missing or too short to safely sign QR codes."""
    return len(QR_SECRET) < 32