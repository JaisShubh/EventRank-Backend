from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity 

def get_tf_idf_recommendations(user_interests: list[str], events: list[dict], top_n: int = 5) -> list[dict]:
    """
    Ranks events based on TF-IDF cosine similarity against user interest keywords.
    
    Parameters:
      - user_interests: List of user topic tags (e.g., ["hackathon", "coding", "ai", "music"])
      - events: List of event dicts containing 'id', 'title', 'description', and 'category'
      - top_n: Maximum number of recommended events to return
    """
    if not events:
        return []
        
    if not user_interests:
        # Return events as-is if user has specified no interests
        return events[:top_n]

    # Combine title, description, and category into a single text document per event
    event_documents = []
    for ev in events:
        doc = f"{ev.get('title', '')} {ev.get('category', '')} {ev.get('description', '')}"
        event_documents.append(doc.lower())

    # Create the user profile query string
    user_query = " ".join(user_interests).lower()
    
    # Corpus: User query + all event documents
    corpus = [user_query] + event_documents
    
    # Compute TF-IDF matrix
    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(corpus)
    
    # Cosine similarity between user query (index 0) and all event vectors (indices 1..)
    user_vector = tfidf_matrix[0]
    event_vectors = tfidf_matrix[1:]
    
    similarities = cosine_similarity(user_vector, event_vectors).flatten()
    
    # Attach similarity scores to events and sort
    scored_events = []
    for idx, score in enumerate(similarities):
        event_copy = events[idx].copy()
        event_copy['match_score'] = round(float(score), 3)
        scored_events.append(event_copy)
        
    # Sort descending by match score
    scored_events.sort(key=lambda x: x['match_score'], reverse=True)
    return scored_events[:top_n] 