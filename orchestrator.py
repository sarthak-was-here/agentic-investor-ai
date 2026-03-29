"""
Orchestrator: The main pipeline
Runs all 5 agents in sequence — this is the "3+ sequential steps without human input"
that the judges require.

Flow:
  User input (symbol + portfolio)
      ↓
  Agent 1: Data Collector  → raw data package
      ↓
  Agent 2: Signal Detector → signals list
      ↓
  Agent 3: Analyzer        → enriched analysis
      ↓
  Agent 4: Decision Agent  → BUY/HOLD/WATCH/AVOID + reasoning
      ↓
  Agent 5: Personalization → portfolio-aware alert
      ↓
  Final unified output
"""

import sys, os, json, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from agents.agent1_data_collector import collect_all_data
from agents.agent2_signal_detector import run_signal_detection
from agents.agent3_analyzer        import run_analysis
from agents.agent4_decision        import run_decision_agent
from agents.agent5_personalization import run_personalization_agent, SAMPLE_PORTFOLIO


def run_full_pipeline(
    symbol: str,
    portfolio: list[dict] = None,
    additional_events: list[dict] = None,
    verbose: bool = True,
) -> dict:
    """
    Execute the full 5-agent pipeline autonomously.
    Returns a unified result dict.
    """
    start_time = time.time()

    if portfolio is None:
        portfolio = SAMPLE_PORTFOLIO

    print(f"\n{'='*60}")
    print(f"  AI FOR THE INDIAN INVESTOR — Multi-Agent Pipeline")
    print(f"  Stock: {symbol.upper()} | {datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"{'='*60}\n")

    # ── Step 1: Data Collection ──────────────────────────────────────────────
    print("STEP 1/5 — Data Collection")
    t1 = time.time()
    data_package = collect_all_data(symbol)
    if "error" in data_package.get("stock_data", {}):
        return {"error": data_package["stock_data"]["error"], "symbol": symbol}
    print(f"  ✓ Done in {time.time()-t1:.1f}s\n")

    # ── Step 2: Signal Detection ─────────────────────────────────────────────
    print("STEP 2/5 — Signal Detection")
    t2 = time.time()
    signal_result = run_signal_detection(data_package)
    print(f"  ✓ Done in {time.time()-t2:.1f}s\n")

    # ── Step 3: Analysis ─────────────────────────────────────────────────────
    print("STEP 3/5 — Analysis (Claude AI)")
    t3 = time.time()
    analysis_result = run_analysis(data_package, signal_result)
    print(f"  ✓ Done in {time.time()-t3:.1f}s\n")

    # ── Step 4: Decision ──────────────────────────────────────────────────────
    print("STEP 4/5 — Decision Generation (Claude AI)")
    t4 = time.time()
    decision_result = run_decision_agent(data_package, signal_result, analysis_result)
    print(f"  ✓ Done in {time.time()-t4:.1f}s\n")

    # ── Step 5: Personalization ───────────────────────────────────────────────
    print("STEP 5/5 — Portfolio Personalization (Claude AI)")
    t5 = time.time()
    personal_result = run_personalization_agent(
        data_package, decision_result,
        portfolio=portfolio,
        additional_events=additional_events,
    )
    print(f"  ✓ Done in {time.time()-t5:.1f}s\n")

    total_time = round(time.time() - start_time, 1)

    # ── Assemble final output ─────────────────────────────────────────────────
    decision = decision_result.get("decision", {})
    final = {
        "symbol":       symbol.upper(),
        "company":      data_package.get("company_name", symbol),
        "price":        data_package["stock_data"].get("current_price"),
        "price_change": data_package["stock_data"].get("price_change_pct"),

        # Core recommendation
        "recommendation":    decision.get("recommendation"),
        "confidence":        decision.get("confidence"),
        "conviction_score":  decision.get("conviction_score"),
        "time_horizon":      decision.get("time_horizon"),
        "entry_range":       decision.get("entry_range"),
        "stop_loss":         decision.get("stop_loss"),
        "target_1":          decision.get("target_1"),
        "target_2":          decision.get("target_2"),

        # Alert text
        "alert_summary":         decision.get("alert_summary"),
        "personalized_alert":    personal_result.get("personalized_alert"),

        # Reasoning (all cited)
        "primary_reason":        decision.get("primary_reason"),
        "supporting_reasons":    decision.get("supporting_reasons", []),
        "conflicting_signals":   decision.get("conflicting_signals_note"),
        "key_risks":             decision.get("key_risks", []),

        # Signals
        "alert_level":   signal_result.get("alert_level"),
        "signals_count": signal_result.get("total_signals"),
        "top_signals":   [s["message"] for s in signal_result.get("signals", [])[:3]],

        # Sentiment
        "news_sentiment":   analysis_result.get("news_sentiment", {}).get("sentiment"),
        "earnings_trend":   analysis_result.get("earnings_trend", {}).get("trend"),

        # Portfolio impact
        "portfolio_impact":      personal_result.get("pl_impact"),
        "in_portfolio":          personal_result.get("is_relevant"),
        "multi_event_priority":  personal_result.get("multi_event_priority"),

        # Meta
        "pipeline_time_sec": total_time,
        "generated_at":      datetime.now().isoformat(),
        "agents_run":        5,
    }

    if verbose:
        _print_summary(final)

    return final


def _print_summary(result: dict):
    """Pretty-print the final result to terminal."""
    rec   = result.get("recommendation","?")
    conf  = result.get("confidence","?")
    score = result.get("conviction_score","?")
    emoji = {"BUY": "🟢", "WATCH": "🟡", "HOLD": "🔵", "AVOID": "🔴"}.get(rec, "⚪")

    print(f"\n{'='*60}")
    print(f"  FINAL ALERT — {result['company']} ({result['symbol']})")
    print(f"{'='*60}")
    print(f"  Price:          ₹{result['price']} ({result['price_change']:+.1f}%)")
    print(f"  Recommendation: {emoji} {rec}  |  Confidence: {conf}  |  Score: {score}/10")
    print(f"  Time horizon:   {result.get('time_horizon','?')}")
    print(f"  Entry range:    {result.get('entry_range','N/A')}")
    print(f"  Stop-loss:      {result.get('stop_loss','N/A')}")
    print(f"  Target 1:       {result.get('target_1','N/A')}")
    print(f"  Target 2:       {result.get('target_2','N/A')}")
    print(f"\n  ALERT SUMMARY:")
    print(f"  {result.get('alert_summary','')}")
    print(f"\n  PORTFOLIO ALERT:")
    print(f"  {result.get('personalized_alert','')}")
    print(f"\n  SIGNALS ({result.get('alert_level','')}):")
    for sig in result.get("top_signals", []):
        print(f"    • {sig}")
    print(f"\n  RISKS:")
    for risk in result.get("key_risks", []):
        print(f"    ⚠ {risk}")
    if result.get("conflicting_signals"):
        print(f"\n  ⚡ CONFLICTING SIGNALS: {result['conflicting_signals']}")
    print(f"\n  Pipeline completed in {result['pipeline_time_sec']}s | "
          f"Agents run: {result['agents_run']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # Default: run HINDUNILVR with the judge's bulk deal scenario
    symbol = sys.argv[1] if len(sys.argv) > 1 else "HINDUNILVR"

    # Judge scenario 3: two events simultaneously
    events = [
        {
            "type":             "RBI_REPO_RATE_CUT",
            "description":      "RBI cuts repo rate by 25bps to 6.0%",
            "affected_sectors": ["Banking", "NBFC", "Real Estate", "Auto"],
            "affected_symbols": ["HDFCBANK", "ICICIBANK", "TATAMOTORS"],
        },
        {
            "type":             "FMCG_REGULATION",
            "description":      "FSSAI introduces new labelling requirements for packaged foods — compliance cost ~2% of revenue",
            "affected_sectors": ["FMCG"],
            "affected_symbols": ["HINDUNILVR", "NESTLEINDIA", "BRITANNIA"],
        },
    ]

    result = run_full_pipeline(symbol, additional_events=events)
