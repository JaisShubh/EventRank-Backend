import math
from datetime import datetime

from ranking import (
    GLOBAL_AVG,
    PRIOR_WEIGHT,
    TOLERANCE,
    MIN_WEIGHT,
    MAX_ROUNDS,
    PREDICTION_PRIOR,
    event_score,
    rank_events,
    predicted_score,
)

def calculate_event_rank(
    avg_rating: float,
    num_reviews: int,
    actual_turnout: int,
    capacity: int,
    organizer_avg_rating: float = 4.0,
    days_until_event: float = 0.0,
    m_confidence: int = 5
) -> float:
    """
    Calculates the 0–100 EventRank score.
    
    Parameters:
      - avg_rating: Mean star rating (1.0 - 5.0) of the event.
      - num_reviews: Total number of verified reviews.
      - actual_turnout: Verified check-ins / RSVPs.
      - capacity: Max capacity of the venue.
      - organizer_avg_rating: Historical rating of the host club (1.0 - 5.0).
      - days_until_event: Days until the event starts (or since posted).
      - m_confidence: Minimum review threshold for Bayesian smoothing.
    """
    # 1. Bayesian Weighted Rating Score (Scale 0 - 100)
    # C is assumed prior average rating (3.5 out of 5)
    prior_rating = 3.5
    bayesian_rating = ((m_confidence * prior_rating) + (num_reviews * avg_rating)) / (m_confidence + num_reviews)
    rating_score = (bayesian_rating / 5.0) * 100.0

    # 2. Turnout / Attendance Score (Scale 0 - 100)
    if capacity > 0:
        turnout_ratio = min(actual_turnout / capacity, 1.2)  # Cap at 120% overflow
        turnout_score = (turnout_ratio / 1.2) * 100.0
    else:
        turnout_score = 50.0  # Neutral default if no capacity set

    # 3. Organizer Track Record Score (Scale 0 - 100)
    organizer_score = (max(1.0, min(5.0, organizer_avg_rating)) / 5.0) * 100.0

    # 4. Weighted Composite Base Score
    # Weights: 50% Reviews/Ratings, 30% Turnout, 20% Organizer Reputation
    base_score = (0.50 * rating_score) + (0.30 * turnout_score) + (0.20 * organizer_score)

    # 5. Time Decay Factor (Recency Penalty)
    # Half-life decay for past events or urgency multiplier for upcoming events
    if days_until_event >= 0:
        # Upcoming event: small decay boost for events happening soon (within 7 days)
        recency_factor = 1.0 + (0.05 * math.exp(-days_until_event / 7.0))
    else:
        # Past event: exponential decay based on days passed
        days_past = abs(days_until_event)
        recency_factor = math.exp(-days_past / 30.0)

    final_score = base_score * recency_factor
    return round(max(0.0, min(100.0, final_score)), 1)