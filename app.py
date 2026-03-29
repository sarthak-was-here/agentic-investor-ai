"""
Streamlit Dashboard — AI for the Indian Investor
Full UI with portfolio input, live analysis, charts, and alerts.
Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import yfinance as yf
import sys, os, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from orchestrator import run_full_pipeline
from agents.agent5_personalization import SAMPLE_PORTFOLIO

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI for the Indian Investor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
.big-rec { font-size: 2.5rem; font-weight: 700; text-align: center; padding: 1rem; border-radius: 12px; }
.rec-buy  { background: #d4edda; color: #155724; }
.rec-watch{ background: #fff3cd; color: #856404; }
.rec-hold { background: #cce5ff; color: #004085; }
.rec-avoid{ background: #f8d7da; color: #721c24; }
.signal-card { padding: 0.6rem 1rem; border-radius: 8px; margin: 0.3rem 0; font-size: 0.9rem; }
.sig-critical { background: #f8d7da; border-left: 4px solid #dc3545; }
.sig-high     { background: #fff3cd; border-left: 4px solid #fd7e14; }
.sig-medium   { background: #d1ecf1; border-left: 4px solid #17a2b8; }
.alert-box { background: #e8f4fd; border: 1px solid #bee5eb; border-radius: 10px; padding: 1rem; margin: 0.5rem 0; }
.metric-label { font-size: 0.8rem; color: #6c757d; }
.portfolio-alert { background: linear-gradient(135deg, #667eea11, #764ba211); border: 1px solid #667eea33; border-radius: 10px; padding: 1rem; }
</style>
""", unsafe_allow_html=True)


# ─── Sidebar: Portfolio Input ────────────────────────────────────────────────
st.sidebar.title("🗂 My Portfolio")
st.sidebar.markdown("Enter your holdings:")

default_portfolio_str = """RELIANCE,50,2800
INFY,100,1400
HDFCBANK,75,1600
TATAMOTORS,200,900
HINDUNILVR,30,2500
SUNPHARMA,80,1200
WIPRO,150,500
ICICIBANK,100,1000"""

portfolio_input = st.sidebar.text_area(
    "Symbol, Qty, Buy Price (one per line)",
    value=default_portfolio_str,
    height=200,
)

def parse_portfolio(text: str) -> list[dict]:
    portfolio = []
    sector_map = {
        "RELIANCE": "Energy", "INFY": "IT", "TCS": "IT", "WIPRO": "IT",
        "HDFCBANK": "Banking", "ICICIBANK": "Banking", "KOTAKBANK": "Banking",
        "TATAMOTORS": "Auto", "MARUTI": "Auto", "BAJAJ-AUTO": "Auto",
        "HINDUNILVR": "FMCG", "NESTLEINDIA": "FMCG", "BRITANNIA": "FMCG",
        "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma",
    }
    for line in text.strip().split("\n"):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            try:
                sym = parts[0].upper()
                portfolio.append({
                    "symbol":    sym,
                    "qty":       int(parts[1]),
                    "buy_price": float(parts[2]),
                    "sector":    sector_map.get(sym, "Other"),
                })
            except Exception:
                pass
    return portfolio

portfolio = parse_portfolio(portfolio_input)
st.sidebar.success(f" {len(portfolio)} stocks loaded")

# ─── Sidebar: Multi-event scenario ───────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader(" Simultaneous Events")
enable_events = st.sidebar.checkbox("Simulate multi-event scenario", value=True)

event_1 = event_2 = None
if enable_events:
    event_1 = {
        "type": "RBI_REPO_RATE_CUT",
        "description": "RBI cuts repo rate by 25bps to 6.0%",
        "affected_sectors": ["Banking", "NBFC", "Real Estate", "Auto"],
        "affected_symbols": ["HDFCBANK", "ICICIBANK", "TATAMOTORS"],
    }
    event_2 = {
        "type": "FMCG_REGULATION",
        "description": "FSSAI new labelling requirements — 2% revenue compliance cost",
        "affected_sectors": ["FMCG"],
        "affected_symbols": ["HINDUNILVR", "NESTLEINDIA"],
    }
    st.sidebar.info("📡 Event 1: RBI repo rate cut 25bps\n\n📡 Event 2: FMCG regulation change")

# ─── Main area ───────────────────────────────────────────────────────────────
st.title(" AI for the Indian Investor")
st.markdown("*Multi-agent system: Data Collection → Signal Detection → Analysis → Decision → Personalization*")

col_input, col_run = st.columns([3, 1])
with col_input:
    symbol = st.text_input(
        "🔍 Enter NSE stock symbol",
        value="HINDUNILVR",
        placeholder="e.g. RELIANCE, INFY, TATAMOTORS",
    ).upper().strip()
with col_run:
    st.markdown("<br>", unsafe_allow_html=True)
    run_btn = st.button(" Run Analysis", type="primary", use_container_width=True)

# ─── Run pipeline ────────────────────────────────────────────────────────────
if run_btn and symbol:
    additional_events = [event_1, event_2] if enable_events else None

    with st.spinner(f"Running 5-agent pipeline for {symbol}... (30-60 seconds)"):
        result = run_full_pipeline(
            symbol,
            portfolio=portfolio,
            additional_events=additional_events,
            verbose=False,
        )

    if "error" in result:
        st.error(f"❌ {result['error']}")
        st.stop()

    st.session_state["result"] = result
    st.session_state["symbol"] = symbol

# ─── Display results ─────────────────────────────────────────────────────────
if "result" in st.session_state:
    result = st.session_state["result"]
    sym    = st.session_state["symbol"]

    decision = result.get("decision", {})

    rec   = decision.get("recommendation", "HOLD")
    conf  = decision.get("confidence", "?")
    score = decision.get("conviction_score", 5)
    price = result.get("price", 0)
    chg   = result.get("price_change", 0)

    # ── Top row: price + recommendation ─────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Current Price", f"₹{price:,.2f}", f"{chg:+.2f}%")
    with col2:
        st.metric("Alert Level", result.get("alert_level","?"))
    with col3:
        st.metric("News Sentiment", result.get("news_sentiment","?"))
    with col4:
        st.metric("Earnings Trend", result.get("earnings_trend","?"))

    # ── Recommendation banner ─────────────────────────────────────────────────
    rec_class = {"BUY":"rec-buy","WATCH":"rec-watch","HOLD":"rec-hold","AVOID":"rec-avoid"}.get(rec,"rec-hold")
    emoji = {"BUY":"🟢","WATCH":"🟡","HOLD":"🔵","AVOID":"🔴"}.get(rec,"⚪")
    st.markdown(
        f'<div class="big-rec {rec_class}">{emoji} {rec} — {conf} CONFIDENCE ({score}/10)</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"**Time horizon:** {decision.get('time_horizon','?')}")

    # ── Price targets ─────────────────────────────────────────────────────────
    t_col1, t_col2, t_col3 = st.columns(3)
    with t_col1:
        st.info(f"📥 Entry: {decision.get('entry_range','N/A')}")
    with t_col2:
        st.success(f"🎯 Target 1: {decision.get('target_1','N/A')}")
    with t_col3:
        st.warning(f"🛡 Stop-loss: {decision.get('stop_loss','N/A')}")

    # ── Alert summary ─────────────────────────────────────────────────────────
    st.markdown("### 📣 Alert Summary")
    st.markdown(
        f'<div class="alert-box">{result.get("alert_summary","")}</div>',
        unsafe_allow_html=True,
    )

    # ── Personalized portfolio alert ──────────────────────────────────────────
    st.markdown("### 👤 Your Portfolio Alert")
    st.markdown(
    f'<div class="portfolio-alert">{result.get("personalized_alert","")}</div>',
    unsafe_allow_html=True,)
    # ── Multi-event priority ──────────────────────────────────────────────────
    if result.get("multi_event_priority"):
        st.markdown("### 🔀 Multi-Event Prioritization")
        mep = result["multi_event_priority"]
        primary = mep.get("primary_event", 1)
        st.markdown(f"**Priority: Event {primary}** — {mep.get('primary_event_reason','')}")
        col_e1, col_e2 = st.columns(2)
        for col, key, label in [(col_e1, "event_1_impact", "Event 1: RBI Rate Cut"),
                                  (col_e2, "event_2_impact", "Event 2: FMCG Regulation")]:
            with col:
                ev = mep.get(key, {})
                direction_emoji = {"POSITIVE":"📈","NEGATIVE":"📉","MIXED":"↔️"}.get(ev.get("direction",""),"?")
                st.markdown(f"**{label}** {direction_emoji}")
                st.markdown(f"Impact: **{ev.get('estimated_pl_impact','?')}**")
                st.markdown(f"Affected: {', '.join(ev.get('affected_holdings',[]))}")
                st.markdown(f"Urgency: {ev.get('urgency','?')}")
        st.markdown(
            f'<div class="alert-box">{mep.get("portfolio_alert","")}</div>',
            unsafe_allow_html=True,
        )

    # ── Two-column: signals + reasoning ──────────────────────────────────────
    left, right = st.columns(2)

    with left:
        st.markdown("### 🔎 Detected Signals")
        for sig in result.get("top_signals", []):
            severity = "sig-high"  # default
            if "CRITICAL" in sig or "PROMOTER" in sig:
                severity = "sig-critical"
            elif "RSI" in sig or "52" in sig:
                severity = "sig-medium"
            st.markdown(
                f'<div class="signal-card {severity}">• {sig}</div>',
                unsafe_allow_html=True,
            )

    with right:
        st.markdown("### 💡 Reasoning (cited)")
        if decision.get("primary_reason"):
            st.markdown(f"**Primary:** {result['primary_reason']}")
        for reason in decision.get("supporting_reasons", []):
            st.markdown(f"• {reason}")
        if result.get("conflicting_signals"):
            st.warning(f"⚡ {result['conflicting_signals']}")

    # ── Risk factors ──────────────────────────────────────────────────────────
    st.markdown("### ⚠️ Key Risks")
    risk_cols = st.columns(len(decision.get("key_risks", [])) or 1)
    for i, risk in enumerate(decision.get("key_risks", [])):
        with risk_cols[i]:
            st.error(f"⚠ {risk}")

    # ── Price chart ───────────────────────────────────────────────────────────
    st.markdown("### 📊 Price Chart (6 months)")
    try:
        ticker = yf.Ticker(sym + ".NS")
        hist   = ticker.history(period="6mo")
        if not hist.empty:
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=hist.index,
                open=hist["Open"], high=hist["High"],
                low=hist["Low"],  close=hist["Close"],
                name=sym,
            ))
            fig.add_trace(go.Bar(
                x=hist.index, y=hist["Volume"],
                name="Volume", yaxis="y2",
                marker_color="rgba(100,100,200,0.3)",
            ))
            fig.update_layout(
                yaxis2=dict(overlaying="y", side="right", showgrid=False),
                height=400, margin=dict(l=0, r=0, t=30, b=0),
                xaxis_rangeslider_visible=False,
            )
            st.plotly_chart(fig, use_container_width=True)
    except Exception:
        st.info("Chart unavailable — check internet connection")

    # ── Portfolio breakdown ───────────────────────────────────────────────────
    st.markdown("### 🗂 Portfolio Sector Breakdown")
    if portfolio:
        sector_df = pd.DataFrame(portfolio)
        sector_agg = sector_df.groupby("sector").apply(
            lambda x: (x["qty"] * x["buy_price"]).sum()
        ).reset_index()
        sector_agg.columns = ["sector", "value"]
        fig_pie = px.pie(sector_agg, values="value", names="sector",
                         title="Portfolio by Sector (cost basis)")
        fig_pie.update_layout(height=350, margin=dict(l=0,r=0,t=40,b=0))
        st.plotly_chart(fig_pie, use_container_width=True)

    # ── P&L impact detail ─────────────────────────────────────────────────────
    pi = result.get("portfolio_impact", {})
    if pi.get("in_portfolio"):
        st.markdown("### 💰 P&L Impact Detail")
        pi_cols = st.columns(4)
        pi_cols[0].metric("Holdings", f"{pi['qty']} shares")
        pi_cols[1].metric("Cost Basis", f"₹{pi['buy_price']}")
        pi_cols[2].metric("Current Value", f"₹{pi.get('current_value',0):,.0f}")
        color = "normal" if pi.get("unrealized_pnl",0) >= 0 else "inverse"
        pi_cols[3].metric(
            "Unrealized P&L",
            f"₹{pi.get('unrealized_pnl',0):+,.0f}",
            f"{pi.get('unrealized_pct',0):+.1f}%",
        )

    # ── Pipeline metadata ─────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(
        f"⚡ Pipeline: 5 agents | Time: {result.get('pipeline_time_sec','?')}s | "
        f"Generated: {result.get('generated_at','')[:19]} | "
        f"Free APIs: yfinance + Google News RSS + Claude Haiku"
    )

else:
    # Welcome screen
    st.markdown("""
    ## Welcome to AI for the Indian Investor 🇮🇳

    This multi-agent system runs a **5-step autonomous pipeline** to turn raw market data 
    into actionable investment alerts — all using **free APIs**.

    ### How it works:
    | Agent | Role | Free Tools Used |
    |-------|------|-----------------|
    | 🟢 Agent 1: Data Collector | Fetches stock data, news, filings | yfinance, Google News RSS, NSE API |
    | 🔵 Agent 2: Signal Detector | Finds breakouts, volume spikes, bulk deals | `ta` library (RSI, MACD, Bollinger) |
    | 🟡 Agent 3: Analyzer | Sentiment, technical context, earnings trend | Claude Haiku API |
    | 🔴 Agent 4: Decision Agent | BUY/HOLD/WATCH/AVOID with cited reasoning | Claude Haiku API |
    | 🟣 Agent 5: Personalization | Portfolio-aware P&L impact alert | Claude Haiku API |

    ### Handles all 3 judge scenarios:
    - ✅ **Bulk deal signal** — Promoter selling: distress or routine?
    - ✅ **Technical breakout with conflicting signals** — RSI + FII + breakout balanced view
    - ✅ **Portfolio-aware news prioritization** — RBI rate cut vs FMCG regulation: which matters to YOUR portfolio?

    ---
    **Enter a stock symbol above and click Run Analysis to start.**
    """)
