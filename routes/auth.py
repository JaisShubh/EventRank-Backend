"""Authentication routes: signup, login, session inspection, and auth helpers.

Integrates with Supabase Auth for student accounts and JWT validation.
"""
from functools import wraps
import re
from flask import Blueprint, g, jsonify, request

import config
from db import get_auth_client

bp = Blueprint("auth", __name__)


def _user_to_dict(user):
    """Serialize a Supabase user object to a JSON-safe dictionary."""
    if not user:
        return None
    if isinstance(user, dict):
        return user
    return {
        "id": str(getattr(user, "id", "")),
        "email": getattr(user, "email", ""),
        "user_metadata": getattr(user, "user_metadata", {}) or {},
        "created_at": str(getattr(user, "created_at", "")),
    }


def _session_to_dict(session):
    """Serialize a Supabase session object to a JSON-safe dictionary."""
    if not session:
        return None
    if isinstance(session, dict):
        return session
    return {
        "access_token": getattr(session, "access_token", None),
        "refresh_token": getattr(session, "refresh_token", None),
        "expires_in": getattr(session, "expires_in", None),
        "expires_at": getattr(session, "expires_at", None),
        "token_type": getattr(session, "token_type", "bearer"),
    }


def get_current_user(optional=True):
    """Extract and verify the current user from the Authorization header or session.

    Returns the user dict if valid, or None if unauthenticated and optional=True.
    """
    auth_header = request.headers.get("Authorization", "").strip()
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if token:
        try:
            client = get_auth_client()
            user_response = client.auth.get_user(token)
            if user_response and user_response.user:
                return _user_to_dict(user_response.user)
        except Exception:
            pass

    return None


def require_auth(f):
    """Decorator to require login on protected endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user(optional=False)
        if not user:
            return jsonify({"error": "Authentication required. Please provide a valid Bearer token."}), 401
        g.user = user
        return f(*args, **kwargs)
    return decorated


@bp.post("/auth/signup")
@bp.post("/signup")
def signup():
    """Register a new student account with email and password."""
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", "")).strip()
    name = str(data.get("name", "")).strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long."}), 400

    # Domain restriction check
    if config.ALLOWED_EMAIL_DOMAIN:
        expected_suffix = f"@{config.ALLOWED_EMAIL_DOMAIN.lower()}"
        if not email.endswith(expected_suffix):
            return jsonify({
                "error": f"Only campus email addresses ending with '{expected_suffix}' are allowed."
            }), 400

    client = get_auth_client()

    try:
        response = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"name": name} if name else {}},
        })
        user_dict = _user_to_dict(response.user)
        session_dict = _session_to_dict(response.session)
        token = session_dict.get("access_token") if session_dict else None
        email_confirmed = getattr(response.user, "email_confirmed_at", None)

        if not token or not email_confirmed:
            return jsonify({
                "message": "Account created. Check your email to verify your address before logging in.",
                "user": user_dict,
                "email_confirmation_required": True,
            }), 202

        return jsonify({
            "message": "Sign up successful.",
            "user": user_dict,
            "session": session_dict,
            "token": token,
        }), 201

    except Exception as err:
        error_msg = str(err)
        if "already registered" in error_msg.lower() or "already exists" in error_msg.lower():
            return jsonify({"error": "An account with this email already exists. Please log in."}), 400
        return jsonify({"error": error_msg}), 400



@bp.post("/auth/login")
@bp.post("/login")
def login():
    """Sign in an existing user and return an access token session."""
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", "")).strip()

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    client = get_auth_client()
    try:
        response = client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        if not getattr(response.user, "email_confirmed_at", None):
            return jsonify({"error": "Please verify your email address before logging in."}), 403
        user_dict = _user_to_dict(response.user)
        session_dict = _session_to_dict(response.session)
        token = session_dict.get("access_token") if session_dict else None

        return jsonify({
            "message": "Login successful.",
            "token": token,
            "user": user_dict,
            "session": session_dict,
        }), 200

    except Exception as err:
        return jsonify({"error": "Invalid email or password."}), 401


@bp.post("/auth/logout")
@bp.post("/logout")
def logout():
    """Sign out the current session."""
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        try:
            client = get_auth_client()
            client.auth.sign_out({"scope": "local"})
        except Exception:
            pass

    return jsonify({"message": "Logged out successfully."}), 200


@bp.get("/auth/me")
@bp.get("/auth/user")
@bp.get("/me")
def me():
    """Return profile details for the currently logged in user."""
    user = get_current_user(optional=True)
    if not user:
        return jsonify({"error": "Not authenticated."}), 401

    return jsonify({"user": user}), 200
