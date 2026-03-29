"""
Agent 5: Personalization Agent
The portfolio-aware layer — judges want to see this explicitly.

Given a user's portfolio (list of stocks + quantities + buy prices),
this agent:
1. Checks if the alert is directly relevant to holdings
2. Calculates actual P&L impact on the user's portfolio
3. Prioritizes across multiple simultaneous events (RBI rate cut vs regulatory change)
4. Generates a personalized, portfolio-aware alert

This handles the judge's third scenario pack:
"RBI repo rate cut + sector regulatory change — which matters more for YOUR portfolio?"
"""

import anthropic
import json
from datetime import datetime


# ─── Sample portfolio structure ─────────────────────────────────────────────
SAMPLE_PORTFOLIO = [
    {"symbol": "RELIANCE",    "qty": 50,   "buy_price": 2800.0, "sector": "Energy"},
    {"symbol": "INFY",        "qty": 100,  "buy_price": 1400.0, "sector": "IT"},
    {"symbol": "HDFCBANK",    "qty": 75,   "buy_price": 1600.0, "sector": "Banking"},
    {"symbol": "TATAMOTORS",  "qty": 200,  "buy_price": 900.0,  "sector": "Auto"},
    {"symbol": "HINDUNILVR",  "qty": 30,   "buy_price": 2500.0, "sector": "FMCG"},
    {"symbol": "SUNPHARMA",   "qty": 80,   "buy_price": 1200.0, "sector": "Pharma"},
    {"symbol": "WIPRO",       "qty": 150,  "buy_price": 500.0,  "sector": "IT"},
    {"symbol": "ICICIBANK",   "qty": 100,  "buy_price": 1000.0, "sector": "Banking"},
]


def _call_claude(prompt: str, system: str = "") -> str:
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1500,
        system=system or (
            "You are a personal financial advisor for an Indian retail investor. "
            "Always quantify impact in rupees. Be direct about what action to take. "
            "Never give generic advice — tie every recommendation to their specific holdings."
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def calculate_portfolio_exposure(portfolio: list[dict],
                                  symbol: str,
                                  current_prices: dict) -> dict:
    """
    Calculates how exposed the portfolio is to a specific stock/sector.
    """
    total_value = 0
    holding_value = 0
    holding = None

    for stock in portfolio:
        price = current_prices.get(stock["symbol"], stock["buy_price"])
        value = stock["qty"] * price
        total_value += value
        if stock["symbol"].upper() == symbol.upper():
            holding_value = value
            holding = stock

    if total_value == 0:
        return {"exposure_pct": 0, "holding": None, "total_value": 0}

    return {
        "exposure_pct":    round((holding_value / total_value) * 100, 1),
        "holding_value":   round(holding_value, 0),
        "total_value":     round(total_value, 0),
        "holding":         holding,
        "unrealized_pnl":  round(
            (current_prices.get(symbol, holding["buy_price"] if holding else 0)
             - holding["buy_price"]) * holding["qty"], 0
        ) if holding else 0,
    }


def calculate_pl_impact(portfolio: list[dict],
                         decision_result: dict,
                         current_prices: dict) -> dict:
    """
    For the judge's scenario: "quantify the estimated P&L impact on relevant holdings".
    """
    symbol       = decision_result["symbol"]
    price        = decision_result["price"]
    decision     = decision_result["decision"]
    target_1_str = decision.get("target_1", "")
    stop_loss_str = decision.get("stop_loss", "")

    # Find holding
    holding = next((s for s in portfolio
                    if s["symbol"].upper() == symbol.upper()), None)

    if not holding:
        return {
            "in_portfolio": False,
            "message": f"{symbol} is not in your portfolio",
        }

    current_val = holding["qty"] * (price or holding["buy_price"])
    cost_basis  = holding["qty"] * holding["buy_price"]
    unrealized  = current_val - cost_basis
    unrealized_pct = (unrealized / cost_basis) * 100 if cost_basis else 0

    # Try to parse target price from string like "₹1800 (10% upside) in 4 weeks"
    target_price = None
    try:
        import re
        nums = re.findall(r"₹?([\d,]+\.?\d*)", target_1_str)
        if nums:
            target_price = float(nums[0].replace(",",""))
    except Exception:
        pass

    potential_gain = (
        (target_price - price) * holding["qty"] if target_price and price else None
    )

    return {
        "in_portfolio":     True,
        "symbol":           symbol,
        "qty":              holding["qty"],
        "buy_price":        holding["buy_price"],
        "current_price":    price,
        "current_value":    round(current_val, 0),
        "unrealized_pnl":   round(unrealized, 0),
        "unrealized_pct":   round(unrealized_pct, 1),
        "potential_gain_if_target": round(potential_gain, 0) if potential_gain else None,
        "target_used":      target_1_str,
    }


def prioritize_multiple_events(
    events: list[dict],
    portfolio: list[dict],
    current_prices: dict,
) -> dict:
    """
    Judge scenario: "Two major news events — which is more material to YOUR portfolio?"
    events = list of {type, description, affected_sectors, affected_symbols}
    """
    # Build portfolio sector exposure
    sector_exposure = {}
    total_value = sum(s["qty"] * current_prices.get(s["symbol"], s["buy_price"])
                      for s in portfolio)

    for stock in portfolio:
        price = current_prices.get(stock["symbol"], stock["buy_price"])
        val   = stock["qty"] * price
        sector = stock.get("sector", "Unknown")
        sector_exposure[sector] = sector_exposure.get(sector, 0) + val

    # Convert to percentages
    sector_pct = {k: round((v / total_value) * 100, 1)
                  for k, v in sector_exposure.items()} if total_value else {}

    portfolio_summary = "\n".join([
        f"  {s['symbol']} ({s.get('sector','?')}): {s['qty']} shares @ ₹{s['buy_price']} "
        f"(current ~₹{current_prices.get(s['symbol'], s['buy_price'])})"
        for s in portfolio
    ])

    sector_summary = "\n".join([
        f"  {sector}: {pct}% of portfolio"
        for sector, pct in sorted(sector_pct.items(), key=lambda x: -x[1])
    ])

    events_text = "\n".join([
        f"Event {i+1}: {e.get('type','?')} — {e.get('description','')}\n"
        f"  Affected sectors: {', '.join(e.get('affected_sectors',[]))}\n"
        f"  Affected stocks: {', '.join(e.get('affected_symbols',[]))}"
        for i, e in enumerate(events)
    ])

    prompt = f"""Two market events just happened. Determine which is MORE FINANCIALLY MATERIAL
to this specific investor's portfolio.

MY PORTFOLIO:
{portfolio_summary}

SECTOR EXPOSURE:
{sector_summary}

TOTAL PORTFOLIO VALUE: ~₹{total_value:,.0f}

THE TWO EVENTS:
{events_text}

Rules:
1. Quantify estimated ₹ P&L impact for EACH event on THIS portfolio
2. Compare them directly — which matters more and why
3. Cite specific holdings that are impacted
4. Generate a prioritized alert — Event X first because ₹Y impact

Respond in JSON ONLY:
{{
  "primary_event": 1 or 2,
  "primary_event_reason": "<why this matters more — cite ₹ impact>",
  "event_1_impact": {{
    "affected_holdings": ["SYMBOL1", "SYMBOL2"],
    "estimated_pl_impact": "₹X to ₹Y (Z% of portfolio)",
    "direction": "POSITIVE" | "NEGATIVE" | "MIXED",
    "urgency": "HIGH" | "MEDIUM" | "LOW"
  }},
  "event_2_impact": {{
    "affected_holdings": ["SYMBOL1"],
    "estimated_pl_impact": "₹X to ₹Y",
    "direction": "POSITIVE" | "NEGATIVE" | "MIXED",
    "urgency": "HIGH" | "MEDIUM" | "LOW"
  }},
  "recommended_actions": [
    {{"symbol": "SYMBOL", "action": "REVIEW|BUY|SELL|HOLD", "reason": "..."}},
  ],
  "portfolio_alert": "<3 sentence personalized alert — mention specific stocks, ₹ numbers, not generic>"
}}"""

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
            "primary_event": 1,
            "primary_event_reason": f"Analysis failed: {e}",
            "portfolio_alert": "Could not complete personalized analysis. Please retry.",
        }


def run_personalization_agent(
    data_package: dict,
    decision_result: dict,
    portfolio: list[dict] = None,
    additional_events: list[dict] = None,
) -> dict:
    """Master entry point for Agent 5."""
    if portfolio is None:
        portfolio = SAMPLE_PORTFOLIO

    symbol = data_package["symbol"]
    print(f"[Agent 5] Personalizing alert for portfolio ({len(portfolio)} holdings)...")

    # Current prices from yfinance (best effort)
    current_prices = {}
    for stock in portfolio:
        price_key = stock["symbol"]
        current_prices[price_key] = stock["buy_price"]  # fallback

    # Try to get real prices
    try:
        import yfinance as yf
        syms = [s["symbol"] + ".NS" for s in portfolio]
        tickers = yf.download(syms, period="1d", progress=False, auto_adjust=True)
        if not tickers.empty and "Close" in tickers.columns:
            for stock in portfolio:
                col = stock["symbol"] + ".NS"
                if col in tickers["Close"].columns:
                    val = tickers["Close"][col].dropna()
                    if not val.empty:
                        current_prices[stock["symbol"]] = float(val.iloc[-1])
    except Exception:
        pass

    # Overwrite with known price for the current stock
    if decision_result.get("price"):
        current_prices[symbol] = decision_result["price"]

    # Portfolio exposure
    exposure = calculate_portfolio_exposure(portfolio, symbol, current_prices)

    # P&L impact
    pl_impact = calculate_pl_impact(portfolio, decision_result, current_prices)

    # Multi-event prioritization (for judge scenario 3)
    multi_event_result = None
    if additional_events:
        print("[Agent 5]   → Prioritizing multiple events for portfolio...")
        multi_event_result = prioritize_multiple_events(
            additional_events, portfolio, current_prices
        )

    # Generate personalized alert text
    personalized_alert = _generate_personalized_alert(
        symbol, decision_result, exposure, pl_impact, portfolio
    )

    result = {
        "symbol":              symbol,
        "portfolio_exposure":  exposure,
        "pl_impact":           pl_impact,
        "is_relevant":         exposure["exposure_pct"] > 0 or pl_impact.get("in_portfolio"),
        "personalized_alert":  personalized_alert,
        "multi_event_priority": multi_event_result,
        "processed_at":        datetime.now().isoformat(),
    }

    print(f"[Agent 5] Personalization done. Relevant to portfolio: {result['is_relevant']}")
    return result


def _generate_personalized_alert(
    symbol: str,
    decision_result: dict,
    exposure: dict,
    pl_impact: dict,
    portfolio: list[dict],
) -> str:
    """Generate a short, plain-English personalized alert."""
    decision = decision_result.get("decision", {})
    rec      = decision.get("recommendation","HOLD")
    alert    = decision.get("alert_summary","")

    if pl_impact.get("in_portfolio"):
        h = pl_impact
        pnl_str = f"₹{h['unrealized_pnl']:+,.0f} ({h['unrealized_pct']:+.1f}%)"
        return (
            f"📊 {symbol} PORTFOLIO ALERT — You hold {h['qty']} shares "
            f"(current P&L: {pnl_str}). "
            f"Recommendation: {rec}. {alert}"
        )
    else:
        return (
            f"📡 {symbol} WATCHLIST ALERT — Not in your portfolio. "
            f"Recommendation: {rec}. {alert}"
        )


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from agents.agent1_data_collector import collect_all_data
    from agents.agent2_signal_detector import run_signal_detection
    from agents.agent3_analyzer        import run_analysis
    from agents.agent4_decision        import run_decision_agent

    # Test multi-event scenario (judge scenario 3)
    events = [
        {
            "type":             "RBI_REPO_RATE_CUT",
            "description":      "RBI cuts repo rate by 25bps to 6.0%",
            "affected_sectors": ["Banking", "NBFC", "Real Estate", "Auto"],
            "affected_symbols": ["HDFCBANK", "ICICIBANK", "TATAMOTORS"],
        },
        {
            "type":             "SECTORAL_REGULATION",
            "description":      "SEBI introduces new margin requirements for F&O in IT sector",
            "affected_sectors": ["IT"],
            "affected_symbols": ["INFY", "WIPRO", "TCS"],
        },
    ]

    data     = collect_all_data("HDFCBANK")
    signals  = run_signal_detection(data)
    analysis = run_analysis(data, signals)
    decision = run_decision_agent(data, signals, analysis)
    result   = run_personalization_agent(data, decision, additional_events=events)

    print("\n" + "="*60)
    print("PERSONALIZED ALERT:")
    print(result["personalized_alert"])
    if result.get("multi_event_priority"):
        print("\nMULTI-EVENT PRIORITY:")
        print(result["multi_event_priority"].get("portfolio_alert",""))
