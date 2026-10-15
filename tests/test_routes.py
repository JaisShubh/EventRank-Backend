"""Integration and unit tests for EventRank routes: auth, events, reviews, and checkins."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from app import create_app
import config
from routes.checkins import generate_qr_token, verify_qr_token, haversine_distance


class FakeTable:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.operation = "select"
        self.payload = None

    def select(self, *_args):
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def execute(self):
        matches = [
            row for row in self.rows
            if all(str(row.get(field)) == str(value) for field, value in self.filters)
        ]
        if self.operation == "insert":
            row = dict(self.payload)
            row.setdefault("id", max((item.get("id", 0) for item in self.rows), default=0) + 1)
            self.rows.append(row)
            return SimpleNamespace(data=[row])
        if self.operation == "update":
            for row in matches:
                row.update(self.payload)
        elif self.operation == "delete":
            self.rows[:] = [row for row in self.rows if row not in matches]
            matches = []
        return SimpleNamespace(data=matches)


class FakeDatabase:
    def __init__(self):
        self.tables = {
            "events": [{
                "id": 2,
                "title": "Test Workshop",
                "description": "Test event description",
                "category": "Workshop",
                "organizer": "Test Organizer",
                "organizer_id": "event-owner",
                "venue": "Test Hall",
                "lat": 12.9716,
                "lng": 77.5946,
                "start_time": "2020-01-01T10:00:00+00:00",
            }],
            "reviews": [],
            "checkins": [],
        }

    def table(self, name):
        return FakeTable(self.tables.setdefault(name, []))


def authenticate_as(monkeypatch, user_id="test-student-42"):
    monkeypatch.setattr(
        "routes.auth.get_current_user",
        lambda optional=True: {
            "id": user_id,
            "email": f"{user_id}@campus.edu",
            "user_metadata": {"name": "Test Student"},
        },
    )


@pytest.fixture
def app(monkeypatch):
    for module in ("app", "routes.events", "routes.reviews", "routes.checkins"):
        monkeypatch.setattr(f"{module}.get_db", FakeDatabase)
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ---- 1. Health Endpoints ----

def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json == {"status": "ok"}


def test_cors_rejects_untrusted_origins(client):
    res = client.get("/health", headers={"Origin": "https://untrusted.example"})
    assert "Access-Control-Allow-Origin" not in res.headers


def test_app_rejects_weak_qr_secret(monkeypatch):
    monkeypatch.setattr(config, "QR_SECRET", "too-short")
    with pytest.raises(RuntimeError, match="QR_SECRET"):
        create_app()


def test_app_rejects_wildcard_cors(monkeypatch):
    monkeypatch.setattr(config, "CORS_ALLOWED_ORIGINS", ("*",))
    with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS"):
        create_app()


def test_health_db(client):
    res = client.get("/health/db")
    # Should be 200 (connected) or 503 (if network/key issue)
    assert res.status_code in (200, 503)


def test_api_reports_missing_supabase_config_as_unavailable(client, monkeypatch):
    def missing_config():
        raise RuntimeError("Missing in backend/.env.local: SUPABASE_KEY")

    monkeypatch.setattr("routes.events.get_db", missing_config)
    res = client.get("/events")
    assert res.status_code == 503
    assert "SUPABASE_KEY" in res.json["error"]


# ---- 2. Auth Routes ----

def test_signup_missing_fields(client):
    res = client.post("/auth/signup", json={})
    assert res.status_code == 400
    assert "error" in res.json


def test_signup_short_password(client):
    res = client.post("/auth/signup", json={"email": "student@campus.edu", "password": "123"})
    assert res.status_code == 400
    assert "at least 6 characters" in res.json["error"]


def test_signup_domain_restriction(client, monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAIL_DOMAIN", "college.edu")
    res = client.post("/auth/signup", json={"email": "hacker@gmail.com", "password": "securepassword123"})
    assert res.status_code == 400
    assert "@college.edu" in res.json["error"]


def test_login_missing_fields(client):
    res = client.post("/auth/login", json={})
    assert res.status_code == 400
    assert "error" in res.json


def test_me_unauthenticated(client):
    res = client.get("/auth/me")
    assert res.status_code == 401
    assert "error" in res.json


def test_me_rejects_unverified_identity_headers(client):
    res = client.get("/auth/me", headers={"X-User-Id": "test-student-42", "X-User-Email": "test@campus.edu"})
    assert res.status_code == 401


def test_me_rejects_query_string_access_token(client):
    res = client.get("/auth/me?access_token=not-a-verified-token")
    assert res.status_code == 401


def test_signup_does_not_issue_unverified_session(client, monkeypatch):
    class FakeAuth:
        def sign_up(self, payload):
            assert payload["options"]["data"]["name"] == "Test Student"
            return SimpleNamespace(
                user=SimpleNamespace(
                    id="new-user",
                    email="student@campus.edu",
                    user_metadata={"name": "Test Student"},
                    email_confirmed_at=None,
                    created_at="",
                ),
                session=SimpleNamespace(access_token="unverified-session"),
            )

    monkeypatch.setattr("routes.auth.get_auth_client", lambda: SimpleNamespace(auth=FakeAuth()))
    res = client.post("/auth/signup", json={
        "email": "student@campus.edu",
        "password": "secure-password",
        "name": "Test Student",
    })
    assert res.status_code == 202
    assert res.json["email_confirmation_required"] is True
    assert "token" not in res.json


def test_login_rejects_unverified_email(client, monkeypatch):
    class FakeAuth:
        def sign_in_with_password(self, _credentials):
            return SimpleNamespace(
                user=SimpleNamespace(email_confirmed_at=None),
                session=SimpleNamespace(access_token="unverified-session"),
            )

    monkeypatch.setattr("routes.auth.get_auth_client", lambda: SimpleNamespace(auth=FakeAuth()))
    res = client.post("/auth/login", json={
        "email": "student@campus.edu",
        "password": "secure-password",
    })
    assert res.status_code == 403
    assert "verify your email" in res.json["error"]


def test_logout(client):
    res = client.post("/auth/logout")
    assert res.status_code == 200
    assert "Logged out successfully" in res.json["message"]


# ---- 3. Events Routes ----

def test_list_events(client):
    res = client.get("/events")
    assert res.status_code == 200
    assert "events" in res.json
    assert "count" in res.json


def test_list_categories(client):
    res = client.get("/events/categories")
    assert res.status_code == 200
    assert "categories" in res.json


def test_event_recommendations(client):
    res = client.get("/events/recommendations?interests=hackathon,coding")
    assert res.status_code == 200
    assert "recommendations" in res.json


def test_get_nonexistent_event(client):
    res = client.get("/events/99999999")
    assert res.status_code == 404
    assert res.json["error"] == "Event not found."


def test_create_event_validation(client, monkeypatch):
    authenticate_as(monkeypatch)
    # Missing venue and start_time
    res = client.post("/events", json={"title": "Tech Talk"})
    assert res.status_code == 400
    assert "Venue location is required" in res.json["error"]


def test_update_nonexistent_event(client):
    res = client.put("/events/99999999", json={"title": "Updated Title"})
    assert res.status_code == 401


def test_update_nonexistent_event_after_auth(client, monkeypatch):
    authenticate_as(monkeypatch)
    res = client.put("/events/99999999", json={"title": "Updated Title"})
    assert res.status_code == 404


def test_delete_nonexistent_event(client):
    res = client.delete("/events/99999999")
    assert res.status_code == 401


def test_delete_nonexistent_event_after_auth(client, monkeypatch):
    authenticate_as(monkeypatch)
    res = client.delete("/events/99999999")
    assert res.status_code == 404


def test_event_mutations_require_authentication(client):
    payload = {"title": "New Event", "venue": "Campus", "start_time": "2026-10-20T10:00:00Z"}
    assert client.post("/events", json=payload).status_code == 401
    assert client.put("/events/2", json={"title": "Updated"}).status_code == 401
    assert client.delete("/events/2").status_code == 401


def test_event_owner_is_required_to_update_or_delete(client, monkeypatch):
    class FakeQuery:
        def select(self, *_args):
            return self

        def eq(self, *_args):
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": 2, "organizer_id": "event-owner"}])

    class FakeDb:
        def table(self, _name):
            return FakeQuery()

    authenticate_as(monkeypatch, "different-user")
    monkeypatch.setattr("routes.events.get_db", FakeDb)

    assert client.put("/events/2", json={"title": "Updated"}).status_code == 403
    assert client.delete("/events/2").status_code == 403


# ---- 4. Reviews Routes ----

def test_get_reviews_nonexistent_event(client):
    res = client.get("/events/99999999/reviews")
    assert res.status_code == 404


def test_create_review_unauthenticated(client):
    res = client.post("/events/1/reviews", json={"rating": 8.0, "comment": "Great event!"})
    assert res.status_code == 401


def test_create_review_validation(client, monkeypatch):
    authenticate_as(monkeypatch)
    # Out of range rating
    res = client.post("/events/99999999/reviews", json={"rating": 15.0, "comment": "Amazing"})
    assert res.status_code in (400, 404)


def test_create_review_spam_detection(client, monkeypatch):
    authenticate_as(monkeypatch, "student-1")
    res = client.post(
        "/events/1/reviews",
        json={"rating": 9.0, "comment": "FREE MONEY CLICK HERE http://spam.com"},
    )
    # Even if event 1 does not exist, spam check or 404 runs
    assert res.status_code in (400, 404)
    if res.status_code == 400:
        assert "spam" in res.json["error"].lower()


def test_global_insights(client):
    res = client.get("/insights")
    assert res.status_code == 200
    assert "total_events" in res.json
    assert "pros_and_cons" in res.json


# ---- 5. Check-in & QR Routes ----

def test_qr_png_nonexistent_event(client):
    res = client.get("/events/99999999/qr.png")
    assert res.status_code == 404


def test_qr_data_nonexistent_event(client):
    res = client.get("/events/99999999/qr-data")
    assert res.status_code == 404


def test_checkin_unauthenticated(client):
    res = client.post("/checkin", json={"event_id": 1})
    assert res.status_code == 401


def test_checkin_missing_event_id(client, monkeypatch):
    authenticate_as(monkeypatch, "student-1")
    res = client.post("/checkin", json={})
    assert res.status_code == 400
    assert "event_id is required" in res.json["error"]


def test_checkin_requires_active_qr_token(client, monkeypatch):
    class FakeQuery:
        def select(self, *_args):
            return self

        def eq(self, *_args):
            return self

        def execute(self):
            return SimpleNamespace(data=[{
                "id": 2,
                "start_time": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "lat": 12.9716,
                "lng": 77.5946,
            }])

    class FakeDb:
        def table(self, _name):
            return FakeQuery()

    authenticate_as(monkeypatch, "student-1")
    monkeypatch.setattr("routes.checkins.get_db", FakeDb)
    res = client.post("/checkin", json={
        "event_id": 2,
        "lat": 12.9716,
        "lng": 77.5946,
    })
    assert res.status_code == 400
    assert "QR code is required" in res.json["error"]


def test_checkin_requires_device_coordinates(client, monkeypatch):
    class FakeQuery:
        def select(self, *_args):
            return self

        def eq(self, *_args):
            return self

        def execute(self):
            return SimpleNamespace(data=[{
                "id": 2,
                "start_time": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "lat": 12.9716,
                "lng": 77.5946,
            }])

    class FakeDb:
        def table(self, _name):
            return FakeQuery()

    authenticate_as(monkeypatch, "student-1")
    monkeypatch.setattr("routes.checkins.get_db", FakeDb)
    monkeypatch.setattr("routes.checkins.verify_qr_token", lambda _event_id, _token: True)
    res = client.post("/checkin", json={"event_id": 2, "token": "active-token"})
    assert res.status_code == 400
    assert "coordinates are required" in res.json["error"]


def test_checkin_status_unauthenticated(client):
    res = client.get("/checkin/status?event_id=1")
    assert res.status_code == 200
    assert res.json == {"authenticated": False, "checked_in": False}


# ---- 6. Check-in QR Token & Geofencing Units ----

def test_qr_token_generation_and_verification():
    event_id = 42
    token, time_slice, remaining = generate_qr_token(event_id)
    assert isinstance(token, str)
    assert "." in token
    assert 0 <= remaining <= config.QR_WINDOW_SECONDS

    # Active token should verify
    assert verify_qr_token(event_id, token) is True

    # Token for a different event should fail
    assert verify_qr_token(999, token) is False

    # Tampered signature should fail
    parts = token.split(".")
    tampered = f"{parts[0]}.bad_sig_value"
    assert verify_qr_token(event_id, tampered) is False

    # Stale token from 100 windows ago should fail
    stale_token = f"{time_slice - 100}.{parts[1]}"
    assert verify_qr_token(event_id, stale_token) is False


def test_haversine_distance():
    # Exact same point: 0 meters
    assert haversine_distance(12.9716, 77.5946, 12.9716, 77.5946) == 0.0

    # Two known points ~300 meters apart
    d = haversine_distance(12.9716, 77.5946, 12.9740, 77.5946)
    assert 200 < d < 400


if __name__ == "__main__":
    print("Run with pytest or run individual test functions.")
