import os
import json
import requests
from typing import List, Dict, Any

# Simple rule-based keyword lexicon for fallback news sentiment
BULLISH_WORDS = {
    'buy', 'bullish', 'growth', 'profit', 'outperform', 'gain', 'increase', 'rise', 
    'beat', 'upgrade', 'dividend', 'revenue', 'expansion', 'optimism', 'high', 
    'positive', 'success', 'recovery', 'strong', 'soar', 'surpass', 'bull'
}

BEARISH_WORDS = {
    'sell', 'bearish', 'loss', 'decline', 'decrease', 'drop', 'fall', 'miss', 
    'downgrade', 'debt', 'risk', 'warning', 'bankruptcy', 'pessimism', 'low', 
    'negative', 'failure', 'slump', 'weak', 'layoff', 'recession', 'bear'
}

def analyze_sentiment_lexicon(text: str) -> float:
    """
    Computes a sentiment score between -1.0 and +1.0 using a basic keyword search.
    """
    text_lower = text.lower()
    
    # Simple tokenization by splitting on whitespace/punctuation
    words = []
    for token in text_lower.split():
        # Strip punctuation
        cleaned = ''.join(c for c in token if c.isalnum())
        if cleaned:
            words.append(cleaned)
            
    if not words:
        return 0.0
        
    bullish_count = sum(1 for w in words if w in BULLISH_WORDS)
    bearish_count = sum(1 for w in words if w in BEARISH_WORDS)
    
    total = bullish_count + bearish_count
    if total == 0:
        return 0.0
        
    # Return difference normalized between -1.0 and +1.0
    return float(bullish_count - bearish_count) / total

def analyze_sentiment_llm(text: str, api_key: str) -> float:
    """
    Analyzes sentiment of the news text using the Gemini REST API.
    Returns a score between -1.0 and +1.0, or None if the request fails.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    prompt = (
        "You are a professional financial analyst. Analyze the market sentiment of the following financial news. "
        "Respond ONLY with a single floating-point number between -1.0 (extremely bearish) and 1.0 (extremely bullish). "
        "Do not include any explanation or additional characters. Just output the number.\n\n"
        f"News Content:\n{text}"
    )
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.1
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=8)
        if response.status_code == 200:
            res_data = response.json()
            text_response = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
            # Try to convert to float
            score = float(text_response)
            # Clip between -1.0 and 1.0
            return max(-1.0, min(1.0, score))
    except Exception:
        # Fall back to lexicon if API fails or returns invalid format
        pass
    return None

def get_news_sentiment(news_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregates sentiment across a list of news items.
    Returns:
    - 'score': Average sentiment score between -1.0 and +1.0
    - 'article_count': Number of articles analyzed
    - 'details': List of articles and their individual scores
    """
    if not news_items:
        return {'score': 0.0, 'article_count': 0, 'details': []}
        
    api_key = os.getenv("GEMINI_API_KEY")
    
    total_score = 0.0
    scored_items = []
    
    for item in news_items:
        title = item.get('title', '')
        summary = item.get('summary', '')
        text_to_analyze = f"{title}. {summary}"
        
        score = None
        if api_key:
            score = analyze_sentiment_llm(text_to_analyze, api_key)
            
        if score is None:
            # Fallback to lexicon analysis
            score = analyze_sentiment_lexicon(text_to_analyze)
            
        total_score += score
        scored_items.append({
            'title': title,
            'url': item.get('url', ''),
            'sentiment_score': round(score, 2)
        })
        
    avg_score = total_score / len(news_items)
    
    return {
        'score': round(avg_score, 2),
        'article_count': len(news_items),
        'details': scored_items
    }
