"""Event routes: listing, searching, filtering, creating, updating, and recommending events.

Uses Bayesian credibility ranking and TF-IDF content recommendations.
"""
from datetime import datetime, timezone
from flask import Blueprint, g, jsonify, request

from db import get_db
from ranking import rank_events, predicted_score, GLOBAL_AVG
from routes.auth import require_auth
from services.ranking import calculate_event_rank
from services.recommendations import get_tf_idf_recommendations

bp = Blueprint("events", __name__)


def _compute_scored_events(events, reviews, checkins):
    """Enrich a list of event dicts with credibility scores, turnout, and rankings."""
    # 1. Map reviews by event_id
    reviews_by_event = {}
    for r in reviews:
        eid = r.get("event_id")
        if eid is not None:
            reviews_by_event.setdefault(eid, []).append(r)

    # 2. Map checkins turnout by event_id
    turnout_by_event = {}
    for c in checkins:
        eid = c.get("event_id")
        if eid is not None:
            turnout_by_event[eid] = turnout_by_event.get(eid, 0) + 1

    # 3. Calculate credibility-weighted scores for events with reviews
    review_scores, user_weights = rank_events(reviews)

    # 4. First pass: score events that have reviews
    scored_pool = []
    enriched_events = []
    now_utc = datetime.now(timezone.utc)

    for ev in events:
        eid = ev["id"]
        ev_reviews = reviews_by_event.get(eid, [])
        num_reviews = len(ev_reviews)
        turnout = turnout_by_event.get(eid, 0)
        ratings = [float(r["rating"]) for r in ev_reviews if r.get("rating") is not None]
        avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

        item = dict(ev)
        item["review_count"] = num_reviews
        item["turnout_count"] = turnout
        item["avg_rating"] = avg_rating

        if eid in review_scores:
            item["score"] = review_scores[eid]
            item["is_predicted"] = False
            scored_pool.append(item)
        else:
            item["score"] = None
            item["is_predicted"] = True

        enriched_events.append(item)

    # 5. Second pass: predict scores for events that have no reviews yet
    for item in enriched_events:
        if item["score"] is None:
            item["score"] = predicted_score(item, scored_pool, global_avg=GLOBAL_AVG)

        # Calculate 0-100 EventRank composite score
        days_until = 0.0
        start_time_raw = item.get("start_time")
        if start_time_raw:
            try:
                # Strip potential Z or offset for clean parsing
                clean_time = str(start_time_raw).replace("Z", "+00:00")
                st = datetime.fromisoformat(clean_time)
                if st.tzinfo is None:
                    st = st.replace(tzinfo=timezone.utc)
                days_until = (st - now_utc).total_seconds() / 86400.0
            except Exception:
                days_until = 0.0

        item["composite_score"] = calculate_event_rank(
            avg_rating=item["avg_rating"] or 3.5,
            num_reviews=item["review_count"],
            actual_turnout=item["turnout_count"],
            capacity=100,  # standard default venue capacity
            organizer_avg_rating=4.0,
            days_until_event=days_until,
        )

    return enriched_events


@bp.get("/events")
def list_events():
    """List events with credibility scores, search, category filtering, and sorting."""
    db = get_db()
    try:
        events_res = db.table("events").select("*").execute()
        events = events_res.data or []
    except Exception as err:
        return jsonify({"error": f"Failed to load events: {err}"}), 500

    try:
        reviews_res = db.table("reviews").select("event_id, user_id, rating").execute()
        reviews = reviews_res.data or []
    except Exception:
        reviews = []

    try:
        checkins_res = db.table("checkins").select("event_id").execute()
        checkins = checkins_res.data or []
    except Exception:
        checkins = []

    # Score and enrich events
    enriched = _compute_scored_events(events, reviews, checkins)

    # Filtering by search query
    query = request.args.get("search", "").strip().lower() or request.args.get("q", "").strip().lower()
    if query:
        enriched = [
            e for e in enriched
            if query in str(e.get("title", "")).lower()
            or query in str(e.get("description", "")).lower()
            or query in str(e.get("category", "")).lower()
            or query in str(e.get("organizer", "")).lower()
            or query in str(e.get("venue", "")).lower()
        ]

    # Filtering by category
    category = request.args.get("category", "").strip().lower()
    if category and category != "all":
        enriched = [e for e in enriched if str(e.get("category", "")).lower() == category]

    # Filtering by organizer
    organizer = request.args.get("organizer", "").strip().lower()
    if organizer:
        enriched = [e for e in enriched if organizer in str(e.get("organizer", "")).lower()]

    # Recommendations filter (TF-IDF)
    interests_param = request.args.get("interests", "").strip()
    if interests_param:
        user_interests = [i.strip() for i in interests_param.split(",") if i.strip()]
        if user_interests:
            enriched = get_tf_idf_recommendations(user_interests, enriched, top_n=len(enriched))

    # Sorting
    sort_by = request.args.get("sort", "score").strip().lower()
    if sort_by in ("score", "rank"):
        enriched.sort(key=lambda e: (e.get("score") or 0.0, e.get("composite_score") or 0.0), reverse=True)
    elif sort_by in ("date", "upcoming", "start_time"):
        enriched.sort(key=lambda e: str(e.get("start_time") or ""), reverse=False)
    elif sort_by in ("turnout", "attendance"):
        enriched.sort(key=lambda e: e.get("turnout_count") or 0, reverse=True)
    elif sort_by in ("reviews", "rating"):
        enriched.sort(key=lambda e: (e.get("review_count") or 0, e.get("avg_rating") or 0.0), reverse=True)
    elif sort_by == "title":
        enriched.sort(key=lambda e: str(e.get("title", "")).lower())

    return jsonify({"events": enriched, "count": len(enriched)}), 200


@bp.get("/events/categories")
def list_categories():
    """Return distinct categories of all registered events."""
    db = get_db()
    try:
        res = db.table("events").select("category").execute()
        categories = sorted({
            row["category"].strip() for row in (res.data or [])
            if row.get("category") and row["category"].strip()
        })
        return jsonify({"categories": categories}), 200
    except Exception as err:
        return jsonify({"error": f"Failed to fetch categories: {err}"}), 500


@bp.get("/events/recommendations")
def recommendations():
    """Return personalized recommendations using TF-IDF matching against user interests."""
    interests_arg = request.args.get("interests", "").strip()
    user_interests = [i.strip() for i in interests_arg.split(",") if i.strip()]

    # If no interests in query string, check if JSON payload has them
    if not user_interests and request.is_json:
        body = request.get_json(silent=True) or {}
        user_interests = body.get("interests", [])

    top_n = request.args.get("top_n", 5, type=int)

    db = get_db()
    try:
        events = db.table("events").select("*").execute().data or []
        reviews = db.table("reviews").select("event_id, user_id, rating").execute().data or []
        checkins = db.table("checkins").select("event_id").execute().data or []
    except Exception as err:
        return jsonify({"error": f"Failed to load events: {err}"}), 500

    enriched = _compute_scored_events(events, reviews, checkins)
    recs = get_tf_idf_recommendations(user_interests, enriched, top_n=top_n)
    return jsonify({"recommendations": recs, "count": len(recs)}), 200


@bp.get("/events/<int:event_id>")
def get_event(event_id: int):
    """Retrieve full details and scores for a specific event."""
    db = get_db()
    try:
        event_res = db.table("events").select("*").eq("id", event_id).execute()
        if not event_res.data:
            return jsonify({"error": "Event not found."}), 404
        event = event_res.data[0]
    except Exception as err:
        return jsonify({"error": f"Database error: {err}"}), 500

    try:
        all_events = db.table("events").select("*").execute().data or []
        reviews = db.table("reviews").select("event_id, user_id, rating").execute().data or []
        checkins = db.table("checkins").select("event_id").execute().data or []
    except Exception:
        all_events = [event]
        reviews, checkins = [], []

    scored_list = _compute_scored_events(all_events, reviews, checkins)
    match = next((e for e in scored_list if e["id"] == event_id), event)
    return jsonify({"event": match}), 200


@bp.post("/events")
@require_auth
def create_event():
    """Create a new campus event."""
    data = request.get_json(silent=True) or {}

    title = str(data.get("title", "")).strip()
    venue = str(data.get("venue", "")).strip()
    start_time = str(data.get("start_time", "")).strip()
    description = str(data.get("description", "")).strip()
    category = str(data.get("category", "")).strip() or "General"
    organizer = str(data.get("organizer", "")).strip()

    if not title:
        return jsonify({"error": "Event title is required."}), 400
    if not venue:
        return jsonify({"error": "Venue location is required."}), 400
    if not start_time:
        return jsonify({"error": "Start time is required."}), 400

    user = g.user
    organizer_id = user["id"]
    if not organizer:
        if user and user.get("user_metadata", {}).get("name"):
            organizer = user["user_metadata"]["name"]
        elif user and user.get("email"):
            organizer = user["email"].split("@")[0]
        else:
            organizer = "Campus Community"

    lat = data.get("lat")
    lng = data.get("lng")
    if lat is not None:
        try:
            lat = float(lat)
        except ValueError:
            lat = None
    if lng is not None:
        try:
            lng = float(lng)
        except ValueError:
            lng = None

    payload = {
        "title": title,
        "description": description,
        "category": category,
        "organizer": organizer,
        "organizer_id": str(organizer_id) if organizer_id else None,
        "venue": venue,
        "lat": lat,
        "lng": lng,
        "start_time": start_time,
    }

    db = get_db()
    try:
        res = db.table("events").insert(payload).execute()
        created = res.data[0] if res.data else payload
        return jsonify({"message": "Event created successfully.", "event": created}), 201
    except Exception as err:
        return jsonify({"error": f"Failed to create event: {err}"}), 500


@bp.put("/events/<int:event_id>")
@require_auth
def update_event(event_id: int):
    """Update existing event details."""
    data = request.get_json(silent=True) or {}
    db = get_db()

    # Verify event exists
    existing = db.table("events").select("id, organizer_id").eq("id", event_id).execute()
    if not existing.data:
        return jsonify({"error": "Event not found."}), 404
    if str(existing.data[0].get("organizer_id")) != str(g.user["id"]):
        return jsonify({"error": "You are not authorized to update this event."}), 403

    allowed_fields = ["title", "description", "category", "organizer", "venue", "lat", "lng", "start_time"]
    update_data = {}
    for field in allowed_fields:
        if field in data:
            val = data[field]
            if field in ("lat", "lng") and val is not None:
                try:
                    val = float(val)
                except ValueError:
                    val = None
            update_data[field] = val

    if not update_data:
        return jsonify({"error": "No valid fields provided for update."}), 400

    try:
        res = db.table("events").update(update_data).eq("id", event_id).execute()
        updated = res.data[0] if res.data else update_data
        return jsonify({"message": "Event updated successfully.", "event": updated}), 200
    except Exception as err:
        return jsonify({"error": f"Failed to update event: {err}"}), 500


@bp.delete("/events/<int:event_id>")
@require_auth
def delete_event(event_id: int):
    """Delete an event and its associated reviews and checkins."""
    db = get_db()
    existing = db.table("events").select("id, organizer_id").eq("id", event_id).execute()
    if not existing.data:
        return jsonify({"error": "Event not found."}), 404
    if str(existing.data[0].get("organizer_id")) != str(g.user["id"]):
        return jsonify({"error": "You are not authorized to delete this event."}), 403

    try:
        # Clean up related records
        try:
            db.table("reviews").delete().eq("event_id", event_id).execute()
            db.table("checkins").delete().eq("event_id", event_id).execute()
        except Exception:
            pass

        db.table("events").delete().eq("id", event_id).execute()
        return jsonify({"message": "Event deleted successfully."}), 200
    except Exception as err:
        return jsonify({"error": f"Failed to delete event: {err}"}), 500
