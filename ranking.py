"""EventRank scoring: how a pile of review ratings becomes one score out of 10.

Three ideas keep the ranking fair:

1. Smoothing. One perfect review should not beat fifty great ones, so every
   event starts with a few "imaginary" average reviews that real reviews must
   outweigh. (event_score)

2. Credibility. A reviewer whose ratings keep landing far from what everyone
   else said about the same events counts for less. Review bombing and fake
   accounts barely move the score. (rank_events)

3. Prediction. A brand-new event has no reviews, so we estimate its score from
   the organizer's past events and similar events. (predicted_score)

Only plain Python in here (no database, no Flask), so it is easy to test.
"""
from collections import defaultdict

GLOBAL_AVG = 7.0        # what we expect an average event to score
PRIOR_WEIGHT = 5        # how many imaginary average reviews each event starts with
TOLERANCE = 2.0         # rating points a reviewer may differ from the crowd with little penalty
MIN_WEIGHT = 0.1        # even the least credible reviewer still counts a little
MAX_ROUNDS = 20         # safety limit on the credibility loop
PREDICTION_PRIOR = 2    # how strongly predictions are pulled toward GLOBAL_AVG


def event_score(ratings, weights=None, global_avg=GLOBAL_AVG, prior=PRIOR_WEIGHT):
    """Smoothed average of ratings (optionally weighted), to 1 decimal place.

    event_score([10])      -> 7.5   (one review is not enough to trust)
    event_score([9] * 50)  -> 8.8   (many reviews: the score follows them)
    """
    if not ratings:
        return global_avg
    if weights is None:
        weights = [1.0] * len(ratings)
    weighted_sum = sum(r * w for r, w in zip(ratings, weights))
    return round((weighted_sum + prior * global_avg) / (sum(weights) + prior), 1)


def _clean(reviews):
    """Keep only usable reviews and force ratings into the 1 to 10 range."""
    cleaned = []
    for r in reviews:
        try:
            rating = float(r["rating"])
        except (KeyError, TypeError, ValueError):
            continue
        if r.get("event_id") is None or r.get("user_id") is None:
            continue
        cleaned.append({
            "event_id": r["event_id"],
            "user_id": r["user_id"],
            "rating": min(10.0, max(1.0, rating)),
        })
    return cleaned


def rank_events(reviews, max_rounds=MAX_ROUNDS):
    """Credibility-weighted scores for every event that has reviews.

    reviews: list of dicts with event_id, user_id and rating.
    Returns (scores, weights):
        scores  = {event_id: score out of 10}
        weights = {user_id: credibility from 0.1 (low) to 1.0 (high)}

    How it works: everyone starts equal. Each round we ask "how far is each
    reviewer from what the OTHER reviewers said about the same events?" and
    lower the weight of people who are far off. Then we repeat with the new
    weights until nothing changes much.
    """
    reviews = _clean(reviews)
    if not reviews:
        return {}, {}

    by_event = defaultdict(list)
    for r in reviews:
        by_event[r["event_id"]].append(r)

    weights = {r["user_id"]: 1.0 for r in reviews}

    for _ in range(max_rounds):
        gaps = defaultdict(list)  # user -> how far off they were, per event
        for event_reviews in by_event.values():
            total = sum(weights[r["user_id"]] for r in event_reviews)
            weighted_sum = sum(weights[r["user_id"]] * r["rating"] for r in event_reviews)
            for r in event_reviews:
                own = weights[r["user_id"]]
                others = total - own
                if others <= 0:
                    continue  # the only reviewer: nobody to compare with
                crowd = (weighted_sum - own * r["rating"]) / others  # average of everyone else
                gaps[r["user_id"]].append(abs(r["rating"] - crowd))

        if not gaps:
            break  # no event has two reviewers yet, so credibility can't be judged

        new_weights = {}
        for user in weights:
            if user in gaps:
                gap = sum(gaps[user]) / len(gaps[user])
                new_weights[user] = max(MIN_WEIGHT, 1 / (1 + (gap / TOLERANCE) ** 2))
            else:
                new_weights[user] = 1.0  # nothing to compare yet: stay neutral

        top = max(new_weights.values())
        new_weights = {user: w / top for user, w in new_weights.items()}  # best reviewer = 1.0

        change = max(abs(new_weights[u] - weights[u]) for u in weights)
        weights = new_weights
        if change < 0.0001:
            break

    scores = {
        event_id: event_score(
            [r["rating"] for r in event_reviews],
            [weights[r["user_id"]] for r in event_reviews],
        )
        for event_id, event_reviews in by_event.items()
    }
    return scores, weights


def predicted_score(event, scored_events, global_avg=GLOBAL_AVG):
    """Estimate the score of an event that has no reviews yet.

    scored_events: events that already have a review-based "score".
    Events by the same organizer count double, events in the same category
    count once (an event that is both counts three times). The estimate is
    pulled toward the campus average, so one lucky past event can't create a
    sky-high prediction.
    """
    organizer = event.get("organizer")
    category = event.get("category")

    total_weight = 0.0
    total_score = 0.0
    for other in scored_events:
        weight = 0
        if organizer and other.get("organizer") == organizer:
            weight += 2
        if category and other.get("category") == category:
            weight += 1
        if weight:
            total_weight += weight
            total_score += weight * other["score"]

    return round((total_score + PREDICTION_PRIOR * global_avg) / (total_weight + PREDICTION_PRIOR), 1)