from services.ranking import GLOBAL_AVG, event_score, predicted_score, rank_events


def review(event_id, user_id, rating):
    return {"event_id": event_id, "user_id": user_id, "rating": rating}


def honest_reviews(events=(1, 2, 3)):
    """Five honest students rating each event around 8 to 10."""
    ratings = [9, 9, 8, 10, 9]
    return [review(e, f"honest{i}", r) for e in events for i, r in enumerate(ratings)]


# ---- event_score: smoothing ----

def test_one_perfect_review_does_not_beat_many_good_ones():
    assert event_score([10]) < event_score([9] * 50)


def test_no_reviews_gives_the_default():
    assert event_score([]) == GLOBAL_AVG


def test_score_stays_between_1_and_10():
    assert 1 <= event_score([1] * 100) <= 10
    assert 1 <= event_score([10] * 100) <= 10


def test_low_weight_reviews_count_for_less():
    assert event_score([9, 9, 1], weights=[1, 1, 0.1]) > event_score([9, 9, 1])


# ---- rank_events: credibility ----

def test_review_bomber_is_discounted():
    reviews = honest_reviews() + [review(e, "bomber", 1) for e in (1, 2, 3)]
    scores, weights = rank_events(reviews)

    plain = event_score([r["rating"] for r in reviews if r["event_id"] == 1])
    assert scores[1] > plain
    assert weights["bomber"] < 0.2
    # Honest students who differ a little from the crowd (like a 10 among 9s)
    # still count far more than the bomber.
    assert all(weights[f"honest{i}"] > 0.5 for i in range(5))
    assert min(weights[f"honest{i}"] for i in range(5)) > 3 * weights["bomber"]


def test_weights_stay_in_range():
    reviews = honest_reviews() + [review(e, "bomber", 1) for e in (1, 2, 3)]
    _, weights = rank_events(reviews)
    assert all(0.1 <= w <= 1.0 for w in weights.values())


def test_sole_reviewer_is_not_punished():
    scores, weights = rank_events([review(1, "a", 9)])
    assert weights["a"] == 1.0
    assert scores[1] == event_score([9])


def test_empty_and_bad_data_are_safe():
    assert rank_events([]) == ({}, {})
    messy = [review(1, "a", "not a number"), {"event_id": 1}, review(1, "b", 15), review(1, "c", 0)]
    scores, _ = rank_events(messy)
    assert 1 <= scores[1] <= 10


def test_events_with_no_reviews_are_not_scored():
    scores, _ = rank_events([review(1, "a", 8), review(1, "b", 8)])
    assert set(scores) == {1}


# ---- predicted_score ----

def test_unknown_organizer_and_category_gets_the_default():
    assert predicted_score({"organizer": "X", "category": "Y"}, [{"score": 9, "organizer": "A", "category": "B"}]) == GLOBAL_AVG
    assert predicted_score({"organizer": "X"}, []) == GLOBAL_AVG


def test_strong_organizer_history_raises_the_prediction():
    history = [{"score": 9.0, "organizer": "Coding Club", "category": "Tech"}] * 3
    good = predicted_score({"organizer": "Coding Club", "category": "Tech"}, history)
    assert GLOBAL_AVG < good < 9.0  # pulled up, but not all the way


def test_weak_history_lowers_the_prediction():
    history = [{"score": 4.0, "organizer": "Slow Club", "category": "Cultural"}] * 3
    assert predicted_score({"organizer": "Slow Club", "category": "Cultural"}, history) < GLOBAL_AVG


def test_same_organizer_counts_more_than_same_category():
    scored = [
        {"score": 9.0, "organizer": "Coding Club", "category": "Cultural"},
        {"score": 5.0, "organizer": "Other Club", "category": "Tech"},
    ]
    result = predicted_score({"organizer": "Coding Club", "category": "Tech"}, scored)
    assert result > GLOBAL_AVG  # the organizer's 9.0 outweighs the category's 5.0