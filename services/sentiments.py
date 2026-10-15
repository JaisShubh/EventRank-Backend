import re

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

try:
    nltk.data.find("sentiment/vader_lexicon.zip")
except LookupError:
    if not nltk.download("vader_lexicon", quiet=True):
        raise RuntimeError("Could not download the NLTK VADER sentiment lexicon")

analyzer = SentimentIntensityAnalyzer()


SPAM_KEYWORDS = {'click here', 'free money', 'whatsapp', 'buy now', 'telegram', 'crypto', 'http', 'https'}

def analyze_review_sentiment(text: str) -> dict:
    """
    Analyzes review text using VADER and returns compound sentiment scores.
    """
    if not text or not text.strip():
        return {"compound": 0.0, "pos": 0.0, "neu": 1.0, "neg": 0.0, "label": "neutral"}
    
    scores = analyzer.polarity_scores(text)
    compound = scores['compound']
    
    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"
        
    return {
        "compound": round(compound, 3),
        "pos": round(scores['pos'], 3),
        "neu": round(scores['neu'], 3),
        "neg": round(scores['neg'], 3),
        "label": label
    }

def is_spam_review(text: str) -> bool:
    """
    Checks if a review is likely spam or low effort.
    """
    if not text or len(text.strip()) < 5:
        return True
    
    cleaned = text.lower()
    
    # Check spam keywords
    if any(keyword in cleaned for keyword in SPAM_KEYWORDS):
        return True
    
    # Check excessive character repetition (e.g., "goooooood")
    if re.search(r'(.)\1{4,}', cleaned):
        return True
        
    return False

def generate_pros_and_cons(reviews: list[str]) -> dict:
    """
    Extracts key positive bullet points (pros) and negative bullet points (cons)
    from a collection of event reviews.
    """
    pros, cons = [], []
    
    for review in reviews:
        if is_spam_review(review):
            continue
            
        sentiment = analyze_review_sentiment(review)
        # Separate sentences or short snippets
        sentences = [s.strip() for s in re.split(r'[.!?]', review) if s.strip()]
        
        for sentence in sentences:
            s_scores = analyzer.polarity_scores(sentence)
            if s_scores['compound'] >= 0.4 and len(sentence) > 10:
                if sentence not in pros and len(pros) < 4:
                    pros.append(sentence)
            elif s_scores['compound'] <= -0.3 and len(sentence) > 10:
                if sentence not in cons and len(cons) < 4:
                    cons.append(sentence)

    return {
        "pros": pros if pros else ["Good overall experience"],
        "cons": cons if cons else ["No major complaints reported"]
    }