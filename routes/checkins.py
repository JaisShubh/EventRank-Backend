"""Check-in routes: rotating QR code generation, GPS radius verification, and verified check-ins.

Uses time-windowed cryptographic HMAC signatures to prevent static QR screenshot sharing,
Haversine distance calculation to ensure physical venue presence,
and early check-in window checks.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import io
import math
import time
from flask import Blueprint, Response, g, jsonify, request

import config
from db import get_db
from routes.auth import get_current_user, require_auth

bp = Blueprint("checkins", __name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two GPS coordinates in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def generate_qr_token(event_id: int) -> tuple[str, int, int]:
    """Generate a time-windowed HMAC signature for an event QR code.

    Returns (token_str, time_slice, seconds_remaining).
    """
    now = time.time()
    time_slice = int(now) // config.QR_WINDOW_SECONDS
    seconds_remaining = config.QR_WINDOW_SECONDS - (int(now) % config.QR_WINDOW_SECONDS)

    msg = f"{event_id}:{time_slice}".encode("utf-8")
    sig = hmac.new(config.QR_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:16]
    token = f"{time_slice}.{sig}"
    return token, time_slice, seconds_remaining


def verify_qr_token(event_id: int, token: str) -> bool:
    """Verify that a token was signed with QR_SECRET and belongs to the current time window."""
    if not token or "." not in token:
        return False
    parts = token.split(".", 1)
    try:
        token_slice = int(parts[0])
    except ValueError:
        return False
    provided_sig = parts[1]

    current_slice = int(time.time()) // config.QR_WINDOW_SECONDS
    # Allow current window, previous window, or next window (±1 window) for network latency
    if abs(current_slice - token_slice) > 1:
        return False

    msg = f"{event_id}:{token_slice}".encode("utf-8")
    expected_sig = hmac.new(config.QR_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:16]
    return hmac.compare_digest(provided_sig, expected_sig)


@bp.get("/events/<int:event_id>/qr.png")
def get_qr_png(event_id: int):
    """Generate a rotating, signed QR code image linking to the frontend check-in screen."""
    db = get_db()
    event_res = db.table("events").select("id, title").eq("id", event_id).execute()
    if not event_res.data:
        return jsonify({"error": "Event not found."}), 404

    token, _, seconds_remaining = generate_qr_token(event_id)
    target_url = f"{config.FRONTEND_URL}/checkin.html?event_id={event_id}&token={token}"

    try:
        import qrcode
        import qrcode.image.pure

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=3,
            image_factory=qrcode.image.pure.PyPNGImage,
        )
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf)
        buf.seek(0)
        png_bytes = buf.getvalue()
    except Exception as err:
        return jsonify({"error": f"Failed to generate QR code image: {err}"}), 500

    response = Response(png_bytes, mimetype="image/png")
    # Tell browsers and proxies never to cache dynamic check-in codes
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["X-QR-Expires-In"] = str(seconds_remaining)
    return response


@bp.get("/events/<int:event_id>/qr-data")
def get_qr_data(event_id: int):
    """Return raw rotating QR code data and expiry for frontend dynamic renderers."""
    db = get_db()
    event_res = db.table("events").select("id, title").eq("id", event_id).execute()
    if not event_res.data:
        return jsonify({"error": "Event not found."}), 404

    token, _, seconds_remaining = generate_qr_token(event_id)
    target_url = f"{config.FRONTEND_URL}/checkin.html?event_id={event_id}&token={token}"

    return jsonify({
        "event_id": event_id,
        "token": token,
        "checkin_url": target_url,
        "window_seconds": config.QR_WINDOW_SECONDS,
        "expires_in_seconds": seconds_remaining,
    }), 200


@bp.post("/checkin")
@require_auth
def checkin():
    """Verify QR token, GPS location radius, and event timing to complete attendance check-in."""
    data = request.get_json(silent=True) or {}
    user = g.user

    event_id_raw = data.get("event_id")
    if event_id_raw is None:
        return jsonify({"error": "event_id is required."}), 400

    try:
        event_id = int(event_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid event_id."}), 400

    db = get_db()
    event_res = db.table("events").select("*").eq("id", event_id).execute()
    if not event_res.data:
        return jsonify({"error": "Event not found."}), 404
    event = event_res.data[0]

    # 1. Verify dynamic QR token
    token = str(data.get("token", "")).strip()
    if not verify_qr_token(event_id, token):
        return jsonify({
            "error": "The scanned QR code is required and must be active. Please scan the current code on the venue screen."
        }), 400

    # 2. Timing check: early check-in window
    start_time_raw = event.get("start_time")
    if not start_time_raw:
        return jsonify({"error": "This event has no start time; check-in is unavailable."}), 400
    try:
        clean_time = str(start_time_raw).replace("Z", "+00:00")
        start_dt = datetime.fromisoformat(clean_time)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        earliest_checkin = start_dt - timedelta(minutes=config.EARLY_CHECKIN_MINUTES)
        if now < earliest_checkin:
            diff_minutes = int((earliest_checkin - now).total_seconds() / 60)
            return jsonify({
                "error": f"Check-in opens {config.EARLY_CHECKIN_MINUTES} minutes before the event (in ~{diff_minutes} min)."
            }), 400
    except (TypeError, ValueError):
        return jsonify({"error": "This event has an invalid start time; check-in is unavailable."}), 400

    # 3. Geofencing GPS radius verification
    event_lat = event.get("lat")
    event_lng = event.get("lng")
    user_lat = data.get("lat")
    user_lng = data.get("lng")

    if any(value is None for value in (event_lat, event_lng, user_lat, user_lng)):
        return jsonify({"error": "Venue and device coordinates are required to verify attendance."}), 400

    try:
        event_lat, event_lng, user_lat, user_lng = map(
            float, (event_lat, event_lng, user_lat, user_lng)
        )
    except (ValueError, TypeError):
        return jsonify({"error": "Venue and device coordinates must be valid numbers."}), 400

    coordinates = (event_lat, event_lng, user_lat, user_lng)
    if (
        not all(math.isfinite(value) for value in coordinates)
        or not -90 <= event_lat <= 90
        or not -90 <= user_lat <= 90
        or not -180 <= event_lng <= 180
        or not -180 <= user_lng <= 180
    ):
        return jsonify({"error": "Venue and device coordinates are out of range."}), 400

    dist_meters = haversine_distance(user_lat, user_lng, event_lat, event_lng)
    if dist_meters > config.VENUE_RADIUS_METERS:
        return jsonify({
            "error": (
                f"Location check failed. You are {int(dist_meters)}m from the venue. "
                f"Check-in is only allowed within {config.VENUE_RADIUS_METERS}m."
            ),
            "distance_meters": round(dist_meters, 1),
            "allowed_radius": config.VENUE_RADIUS_METERS,
        }), 400

    # 4. Check for existing check-in to prevent duplicate records
    existing = db.table("checkins").select("id, created_at").eq("event_id", event_id).eq("user_id", user["id"]).execute()
    if existing.data:
        return jsonify({
            "message": "You are already checked in for this event.",
            "already_checked_in": True,
            "checkin": existing.data[0],
            "verified": True,
        }), 200

    # 5. Insert new verified check-in
    payload = {
        "event_id": event_id,
        "user_id": user["id"],
    }
    try:
        insert_res = db.table("checkins").insert(payload).execute()
        created = insert_res.data[0] if insert_res.data else payload
        return jsonify({
            "message": "Check-in successful! Your attendance is verified.",
            "verified": True,
            "checkin": created,
        }), 201
    except Exception as err:
        return jsonify({"error": f"Failed to record check-in: {err}"}), 500


@bp.get("/checkin/status")
def checkin_status():
    """Check if the requesting user has checked in for a specified event."""
    user = get_current_user(optional=True)
    if not user:
        return jsonify({"authenticated": False, "checked_in": False}), 200

    event_id = request.args.get("event_id", type=int)
    if not event_id:
        return jsonify({"error": "event_id query parameter is required."}), 400

    db = get_db()
    existing = db.table("checkins").select("id, created_at").eq("event_id", event_id).eq("user_id", user["id"]).execute()
    checked_in = bool(existing.data)

    return jsonify({
        "authenticated": True,
        "checked_in": checked_in,
        "checkin": existing.data[0] if checked_in else None,
    }), 200


@bp.get("/events/<int:event_id>/checkins")
def list_event_checkins(event_id: int):
    """Return turnout count and verified check-ins for an event."""
    db = get_db()
    try:
        res = db.table("checkins").select("id, user_id, created_at").eq("event_id", event_id).execute()
        checkins = res.data or []
        return jsonify({
            "event_id": event_id,
            "turnout_count": len(checkins),
            "checkins": checkins,
        }), 200
    except Exception as err:
        return jsonify({"error": f"Failed to fetch check-ins: {err}"}), 500
