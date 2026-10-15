"""Review routes: submitting reviews, sentiment analysis, spam filtering, and insights.

Integrates VADER sentiment analysis, spam detection, pros/cons extraction,
and attendee verification against physical QR check-ins.
"""
from flask import Blueprint, g, jsonify, request

from db import get_db
from ranking import rank_events
from routes.auth import get_current_user, require_auth
from services.ranking import calculate_event_rank
from services.sentiments import analyze_review_sentiment, generate_pros_and_cons, is_spam_review

bp = Blueprint("reviews", __name__)


def _get_verified_attendee_ids(event_id: int) -> set:
    """Return the set of user_ids who checked in at the event venue."""
    db = get_db()
    try:
        res = db.table("checkins").select("user_id").eq("event_id", event_id).execute()
        return {str(row["user_id"]) for row in (res.data or []) if row.get("user_id")}
    except Exception:
        return set()


@bp.get("/events/<int:event_id>/reviews")
def get_event_reviews(event_id: int):
    """Retrieve all reviews for an event, enriched with sentiment and attendance verification."""
    db = get_db()

    # Check if event exists
    event = db.table("events").select("id").eq("id", event_id).execute()
    if not event.data:
        return jsonify({"error": "Event not found."}), 404

    try:
        res = db.table("reviews").select("*").eq("event_id", event_id).order("created_at", desc=True).execute()
        reviews = res.data or []
    except Exception as err:
        return jsonify({"error": f"Failed to fetch reviews: {err}"}), 500

    verified_attendees = _get_verified_attendee_ids(event_id)

    enriched = []
    for r in reviews:
        item = dict(r)
        user_id = str(item.get("user_id", ""))
        item["verified_attendee"] = user_id in verified_attendees
        comment = item.get("comment", "")
        item["sentiment"] = analyze_review_sentiment(comment) if comment else None
        enriched.append(item)

    return jsonify({"reviews": enriched, "count": len(enriched)}), 200


@bp.post("/events/<int:event_id>/reviews")
@require_auth
def create_review(event_id: int):
    """Submit a verified review with spam check and rating validation."""
    data = request.get_json(silent=True) or {}
    user = g.user

    db = get_db()
    # Confirm event exists
    event_res = db.table("events").select("id").eq("id", event_id).execute()
    if not event_res.data:
        return jsonify({"error": "Event not found."}), 404

    rating_raw = data.get("rating")
    if rating_raw is None:
        return jsonify({"error": "Rating is required (between 1.0 and 10.0)."}), 400

    try:
        rating = float(rating_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Rating must be a valid number."}), 400

    # Ensure rating is in valid range (1.0 to 10.0)
    if rating < 1.0 or rating > 10.0:
        return jsonify({"error": "Rating must be between 1.0 and 10.0."}), 400

    comment = str(data.get("comment", "")).strip()

    # Spam & low-effort filter
    if comment and is_spam_review(comment):
        return jsonify({
            "error": "Review rejected: contains spam keywords or repeated characters."
        }), 400

    user_id = user["id"]

    # Check for existing review by this user on this event
    existing = db.table("reviews").select("id").eq("event_id", event_id).eq("user_id", user_id).execute()
    if existing.data:
        # Update existing review
        rev_id = existing.data[0]["id"]
        update_payload = {"rating": rating, "comment": comment}
        db.table("reviews").update(update_payload).eq("id", rev_id).execute()
        updated = existing.data[0]
        updated.update(update_payload)
        verified = user_id in _get_verified_attendee_ids(event_id)
        return jsonify({
            "message": "Review updated successfully.",
            "review": updated,
            "verified_attendee": verified,
        }), 200

    # Insert new review
    payload = {
        "event_id": event_id,
        "user_id": user_id,
        "rating": rating,
        "comment": comment,
    }

    try:
        res = db.table("reviews").insert(payload).execute()
        created = res.data[0] if res.data else payload
        verified = user_id in _get_verified_attendee_ids(event_id)
        return jsonify({
            "message": "Review submitted successfully.",
            "review": created,
            "verified_attendee": verified,
        }), 201
    except Exception as err:
        return jsonify({"error": f"Failed to save review: {err}"}), 500


@bp.get("/events/<int:event_id>/insights")
def event_insights(event_id: int):
    """Generate detailed AI insights for a specific event: pros/cons, sentiment, and credibility."""
    db = get_db()
    event_res = db.table("events").select("*").eq("id", event_id).execute()
    if not event_res.data:
        return jsonify({"error": "Event not found."}), 404
    event = event_res.data[0]

    reviews_res = db.table("reviews").select("*").eq("event_id", event_id).execute()
    reviews = reviews_res.data or []

    verified_attendees = _get_verified_attendee_ids(event_id)
    turnout_count = len(verified_attendees)

    comments = [r.get("comment", "").strip() for r in reviews if r.get("comment")]
    ratings = [float(r["rating"]) for r in reviews if r.get("rating") is not None]

    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else 0.0

    # Sentiment distribution
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
    total_compound = 0.0

    for comment in comments:
        analysis = analyze_review_sentiment(comment)
        label = analysis.get("label", "neutral")
        sentiment_counts[label] = sentiment_counts.get(label, 0) + 1
        total_compound += analysis.get("compound", 0.0)

    avg_compound = round(total_compound / len(comments), 3) if comments else 0.0

    # Extract pros and cons
    pros_cons = generate_pros_and_cons(comments)

    # Credibility weighting
    scores, user_weights = rank_events(reviews)
    credibility_score = scores.get(event_id)

    # EventRank score
    composite_rank = calculate_event_rank(
        avg_rating=avg_rating or 3.5,
        num_reviews=len(reviews),
        actual_turnout=turnout_count,
        capacity=100,
    )

    return jsonify({
        "event_id": event_id,
        "title": event.get("title", ""),
        "total_reviews": len(reviews),
        "verified_attendees": turnout_count,
        "average_rating": avg_rating,
        "credibility_score": credibility_score,
        "composite_rank": composite_rank,
        "sentiment_overview": {
            "average_compound": avg_compound,
            "counts": sentiment_counts,
        },
        "pros_and_cons": pros_cons,
    }), 200


@bp.get("/insights")
def global_insights():
    """Campus-wide insights or single-event delegation if ?event_id is provided."""
    event_id = request.args.get("event_id", type=int)
    if event_id:
        return event_insights(event_id)

    db = get_db()
    try:
        events = db.table("events").select("id, title, category").execute().data or []
        reviews = db.table("reviews").select("event_id, rating, comment").execute().data or []
        checkins = db.table("checkins").select("id").execute().data or []
    except Exception as err:
        return jsonify({"error": f"Failed to compile insights: {err}"}), 500

    all_comments = [r.get("comment", "").strip() for r in reviews if r.get("comment")]
    ratings = [float(r["rating"]) for r in reviews if r.get("rating") is not None]

    pros_cons = generate_pros_and_cons(all_comments[:30])

    return jsonify({
        "total_events": len(events),
        "total_reviews": len(reviews),
        "total_checkins": len(checkins),
        "campus_average_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
        "pros_and_cons": pros_cons,
    }), 200


@bp.delete("/events/<int:event_id>/reviews/<int:review_id>")
@bp.delete("/reviews/<int:review_id>")
@require_auth
def delete_review(review_id: int, event_id: int = None):
    """Delete a review (must be the author)."""
    user = g.user
    db = get_db()

    query = db.table("reviews").select("*").eq("id", review_id)
    if event_id:
        query = query.eq("event_id", event_id)
    res = query.execute()

    if not res.data:
        return jsonify({"error": "Review not found."}), 404

    review = res.data[0]
    if str(review.get("user_id")) != str(user["id"]):
        return jsonify({"error": "You are not authorized to delete this review."}), 403

    try:
        db.table("reviews").delete().eq("id", review_id).execute()
        return jsonify({"message": "Review deleted successfully."}), 200
    except Exception as err:
        return jsonify({"error": f"Failed to delete review: {err}"}), 500
