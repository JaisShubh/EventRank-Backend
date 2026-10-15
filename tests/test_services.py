from services.ranking import calculate_event_rank
from services.sentiments import analyze_review_sentiment, is_spam_review, generate_pros_and_cons
from services.recommendations import get_tf_idf_recommendations

def test_services():
    print("--- 1. Testing Ranking Service ---")
    score = calculate_event_rank(
        avg_rating=4.5,
        num_reviews=25,
        actual_turnout=120,
        capacity=150,
        organizer_avg_rating=4.8,
        days_until_event=2.0
    )
    print(f"Calculated EventRank Score: {score}/100")
    assert 0 <= score <= 100, "Score out of range!"

    print("\n--- 2. Testing Sentiment Service ---")
    sample_reviews = [
        "Great hackathon! Excellent organization, amazing food, and helpful mentors.",
        "The sound system was terrible and the event started 2 hours late.",
        "FREE MONEY CLICK HERE http://spam.com",
        "Overall fine, nothing special."
    ]
    
    print("Spam Check:", [is_spam_review(r) for r in sample_reviews])
    print("Sentiment Analysis:", analyze_review_sentiment(sample_reviews[0]))
    summary = generate_pros_and_cons(sample_reviews)
    print("Pros & Cons Summary:", summary)

    print("\n--- 3. Testing Recommendation Service ---")
    sample_events = [
        {"id": 1, "title": "Hack Night 2026", "category": "Coding", "description": "24-hour hackathon with AI and Python challenges."},
        {"id": 2, "title": "Open Mic Night", "category": "Music", "description": "Acoustic performances and standup comedy."},
        {"id": 3, "title": "Career Talk: Data Science", "category": "Tech", "description": "Industry speaker session on Machine Learning."}
    ]
    user_interests = ["coding", "python", "ai"]
    recs = get_tf_idf_recommendations(user_interests, sample_events, top_n=2)
    print("Top Recommendations:")
    for r in recs:
        print(f" - {r['title']} (Match Score: {r['match_score']})")

    print("\n✅ All services passed testing cleanly!")

if __name__ == "__main__":
    test_services()