"""
Agent 3: Analyzer
Uses Claude API (free tier via Anthropic) to:
- Analyze news sentiment
- Interpret technical signals in context
- Cross-reference earnings trends
- Assess whether a bulk deal is distress selling or routine

Claude API is free to start — you get $5 credit, enough for hundreds of analyses.
"""

import anthropic
import json
from datetime import datetime


def _call_claude(prompt: str, system: str = "") -> str:
    """Call Claude API. Model: claude-haiku-3-5 (cheapest, fastest)."""
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=system or (
            "You are an expert Indian equity market analyst. "
            "Be concise, data-driven, and cite specific numbers from the data provided. "
            "Focus on actionable insights for retail investors."
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def analyze_news_sentiment(news: list[dict], symbol: str) -> dict:
    """
    Use Claude to analyze news sentiment for the stock.
    Returns: sentiment score (-1 to 1), key themes, red flags.
    """
    if not news:
        return {"sentiment": "NEUTRAL", "score": 0, "summary": "No news available."}

    news_text = "\n".join([
        f"- [{n.get('source','')}] {n.get('title','')} — {n.get('summary','')[:150]}"
        for n in news[:8]
    ])

    prompt = f"""Analyze these recent news items for {symbol}:

{news_text}

Respond in JSON format exactly like this:
{{
  "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL" | "MIXED",
  "score": <float from -1.0 (very bearish) to 1.0 (very bullish)>,
  "key_themes": ["theme1", "theme2", "theme3"],
  "red_flags": ["flag1"] or [],
  "positive_catalysts": ["catalyst1"] or [],
  "summary": "<2 sentence summary>"
}}

Return ONLY the JSON, no other text."""

    try:
        response = _call_claude(prompt)
        # Clean up JSON if needed
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        return json.loads(response)
    except Exception as e:
        return {
            "sentiment": "NEUTRAL",
            "score": 0,
            "key_themes": [],
            "red_flags": [],
            "positive_catalysts": [],
            "summary": f"Could not analyze sentiment: {str(e)}",
        }


def analyze_bulk_deal_context(deal: dict, stock_data: dict,
                               filings: list, news: list) -> dict:
    """
    Specific analysis for the judge's scenario:
    "Is this promoter bulk sale distress selling or routine block?"
    """
    prompt = f"""A promoter bulk deal just occurred. Assess if this is DISTRESS SELLING or ROUTINE:

DEAL DETAILS:
- Company: {deal.get('company', stock_data.get('symbol'))}
- Transaction: {deal.get('buy_sell','SELL')} — {deal.get('quantity',0):,} shares
- Price: ₹{deal.get('trade_price',0)} ({deal.get('remarks','')})

STOCK CONTEXT:
- Current price: ₹{stock_data.get('current_price')}
- Price change today: {stock_data.get('price_change_pct',0):+.1f}%
- 52w high: ₹{stock_data.get('high_52w')} | 52w low: ₹{stock_data.get('low_52w')}
- Sector: {stock_data.get('info',{}).get('sector','N/A')}

RECENT FILINGS SUMMARY:
{chr(10).join([f.get('summary','')[:200] for f in filings[:2]])}

RECENT NEWS HEADLINES:
{chr(10).join([n.get('title','') for n in news[:4]])}

Respond in JSON:
{{
  "classification": "DISTRESS_SELLING" | "ROUTINE_BLOCK" | "UNCERTAIN",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "distress_indicators": ["indicator1"] or [],
  "routine_indicators": ["indicator1"] or [],
  "recommended_action_retail": "<specific action for retail investor>",
  "reasoning": "<2-3 sentence explanation citing the data above>"
}}

Return ONLY the JSON."""

    try:
        response = _call_claude(prompt)
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        return json.loads(response)
    except Exception as e:
        return {
            "classification": "UNCERTAIN",
            "confidence": "LOW",
            "distress_indicators": [],
            "routine_indicators": [],
            "recommended_action_retail": "Monitor closely and wait for more clarity.",
            "reasoning": f"Analysis failed: {str(e)}",
        }


def analyze_technical_context(signals: list[dict], stock_data: dict) -> dict:
    """
    Judge scenario: "Technical breakout with conflicting signals"
    RSI overbought + FII reducing + 52w breakout → balanced recommendation.
    """
    signals_text = "\n".join([
        f"- [{s['severity']}] {s['type']}: {s['message']}"
        for s in signals[:8]
    ])

    prompt = f"""Analyze these technical signals for {stock_data.get('symbol')} and give a BALANCED view:

CURRENT PRICE: ₹{stock_data.get('current_price')} ({stock_data.get('price_change_pct',0):+.1f}% today)
52W RANGE: ₹{stock_data.get('low_52w')} – ₹{stock_data.get('high_52w')}
VOLUME RATIO: {stock_data.get('volume_ratio','N/A')}x average

DETECTED SIGNALS:
{signals_text}

Rules:
1. Do NOT give a binary BUY/SELL — give a nuanced view
2. Cite specific conflicting signals
3. Quantify historical success rates if you know them (e.g. "52w breakouts on high volume succeed ~65% of the time")
4. Consider the RSI and volume together

Respond in JSON:
{{
  "bullish_case": ["point1", "point2"],
  "bearish_case": ["point1", "point2"],
  "conflicting_signals": ["signal1", "signal2"],
  "historical_context": "<pattern success rate or base rate if known>",
  "overall_bias": "BULLISH" | "BEARISH" | "NEUTRAL" | "CONFLICTED",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "key_levels_to_watch": {{
    "support": "<price level>",
    "resistance": "<price level>"
  }},
  "analyst_note": "<2 sentences — honest, balanced, cites conflicting data>"
}}

Return ONLY the JSON."""

    try:
        response = _call_claude(prompt)
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        return json.loads(response)
    except Exception as e:
        return {
            "bullish_case": [],
            "bearish_case": [],
            "conflicting_signals": [],
            "overall_bias": "NEUTRAL",
            "confidence": "LOW",
            "analyst_note": f"Analysis failed: {str(e)}",
        }


def run_analysis(data_package: dict, signal_result: dict) -> dict:
    """
    Master analyzer — runs all analysis and returns enriched context
    for Agent 4 (Decision Agent).
    """
    symbol     = data_package["symbol"]
    stock_data = data_package["stock_data"]
    news       = data_package.get("news", [])
    filings    = data_package.get("filings", [])
    bulk_deals = data_package.get("bulk_deals", [])
    signals    = signal_result.get("signals", [])

    print(f"[Agent 3] Analyzing {symbol}...")

    # 1. News sentiment
    print("[Agent 3]   → Running news sentiment analysis...")
    sentiment = analyze_news_sentiment(news, symbol)

    # 2. Bulk deal analysis (if applicable)
    bulk_analysis = None
    if signal_result.get("has_bulk_deal") and bulk_deals:
        print("[Agent 3]   → Analyzing bulk deal context...")
        bulk_analysis = analyze_bulk_deal_context(
            bulk_deals[0], stock_data, filings, news
        )

    # 3. Technical analysis
    technical_analysis = None
    if signal_result.get("has_technical") or signals:
        print("[Agent 3]   → Interpreting technical signals...")
        technical_analysis = analyze_technical_context(signals, stock_data)

    result = {
        "symbol":              symbol,
        "news_sentiment":      sentiment,
        "bulk_deal_analysis":  bulk_analysis,
        "technical_analysis":  technical_analysis,
        "earnings_trend":      _extract_earnings_trend(filings),
        "analyzed_at":         datetime.now().isoformat(),
    }

    print(f"[Agent 3] Analysis complete. Sentiment: {sentiment.get('sentiment')}")
    return result


def _extract_earnings_trend(filings: list[dict]) -> dict:
    """Simple keyword-based earnings trend from filing summaries."""
    if not filings:
        return {"trend": "UNKNOWN", "notes": "No filings available"}

    text = " ".join([f.get("summary","") + f.get("title","") for f in filings]).lower()

    positive_words = ["profit", "revenue up", "growth", "beat", "record",
                      "increase", "expansion", "strong", "upgrade"]
    negative_words = ["loss", "decline", "miss", "weak", "downgrade",
                      "caution", "concern", "decrease", "pressure"]

    pos_count = sum(1 for w in positive_words if w in text)
    neg_count = sum(1 for w in negative_words if w in text)

    if pos_count > neg_count + 1:
        trend = "POSITIVE"
    elif neg_count > pos_count + 1:
        trend = "NEGATIVE"
    else:
        trend = "MIXED"

    return {
        "trend":      trend,
        "pos_signals": pos_count,
        "neg_signals": neg_count,
        "notes":      f"Based on {len(filings)} recent filings",
    }


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from agents.agent1_data_collector import collect_all_data
    from agents.agent2_signal_detector import run_signal_detection

    data    = collect_all_data("INFY")
    signals = run_signal_detection(data)
    analysis = run_analysis(data, signals)
    print(json.dumps({k: v for k, v in analysis.items()
                      if k != "history_df"}, indent=2, default=str))
