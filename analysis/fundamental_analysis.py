from typing import Dict, Any

def score_pe_ratio(pe: float) -> float:
    """Scores P/E ratio: lower positive is value; high or negative is higher risk."""
    if pe is None:
        return 0.0
    if pe < 0:
        return -0.4  # Company losing money
    elif 0 < pe <= 15:
        return 0.8   # High value / undervalued
    elif 15 < pe <= 25:
        return 0.5   # Fair value
    elif 25 < pe <= 40:
        return 0.1   # Moderately expensive
    else:
        return -0.2  # Highly speculative valuation

def score_debt_to_equity(de: float) -> float:
    """Scores Debt-to-Equity percentage: lower debt is safer."""
    if de is None:
        return 0.0
    if de <= 50:
        return 0.8   # Very conservative debt structure
    elif 50 < de <= 100:
        return 0.5   # Moderate debt
    elif 100 < de <= 200:
        return -0.1  # Highly leveraged
    else:
        return -0.6  # Dangerous debt levels

def score_growth(growth: float) -> float:
    """Scores revenue/earnings growth rate."""
    if growth is None:
        return 0.0
    if growth > 0.20:
        return 0.8   # High growth (>20%)
    elif 0.05 <= growth <= 0.20:
        return 0.5   # Steady growth
    elif -0.05 < growth < 0.05:
        return 0.0   # Flat
    else:
        return -0.6  # Declining business

def score_margins(margins: float) -> float:
    """Scores profit/operating margins."""
    if margins is None:
        return 0.0
    if margins > 0.20:
        return 0.8   # High profitability (>20%)
    elif 0.08 <= margins <= 0.20:
        return 0.4   # Good profitability
    elif 0 < margins < 0.08:
        return 0.1   # Razor thin margins
    else:
        return -0.6  # Unprofitable operations

def evaluate_fundamentals(fundamentals: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates fundamental metrics and returns a score and summary details.
    Returns:
    - 'score': Float between -1.0 and +1.0
    - 'evaluation': Summary details mapping
    """
    if not fundamentals:
        return {'score': 0.0, 'metrics': {}}
        
    scores = []
    
    # 1. Valuation (P/E Ratio)
    pe = fundamentals.get('pe_ratio')
    pe_score = score_pe_ratio(pe)
    scores.append(pe_score)
    
    # 2. Financial Leverage (Debt-to-Equity)
    de = fundamentals.get('debt_to_equity')
    de_score = score_debt_to_equity(de)
    scores.append(de_score)
    
    # 3. Growth Profile
    growth = fundamentals.get('revenue_growth')
    growth_score = score_growth(growth)
    scores.append(growth_score)
    
    # 4. Profitability
    margins = fundamentals.get('profit_margins')
    margins_score = score_margins(margins)
    scores.append(margins_score)
    
    # Average the fundamental scores
    avg_score = sum(scores) / len(scores) if scores else 0.0
    
    # Generate a descriptive evaluation
    eval_text = "Neutral"
    if avg_score >= 0.4:
        eval_text = "Strong Buy" if avg_score >= 0.6 else "Buy"
    elif avg_score <= -0.4:
        eval_text = "Strong Sell" if avg_score <= -0.6 else "Sell"
        
    return {
        'score': round(avg_score, 2),
        'evaluation': eval_text,
        'metrics': {
            'pe_ratio': pe,
            'debt_to_equity': de,
            'revenue_growth': growth,
            'profit_margins': margins,
            'dividend_yield': fundamentals.get('dividend_yield')
        }
    }
