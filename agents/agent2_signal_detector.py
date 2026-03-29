"""
Agent 2: Signal Detector
Scans the collected data for meaningful signals:
- Unusual volume (volume spike > 2x average)
- 52-week high breakout
- Bulk/block deal flags
- Promoter selling signals
- RSI overbought/oversold
- MACD crossovers
- Support/Resistance breaks

Output: structured list of signals with severity scores
"""

import pandas as pd
import numpy as np
from datetime import datetime
import ta  # Technical Analysis library (free, no API key)


# ─── Signal severity levels ────────────────────────────────────────────────
SEVERITY = {
    "CRITICAL": 5,   # Promoter bulk sell, major insider trade
    "HIGH":     4,   # 52w breakout + volume spike together
    "MEDIUM":   3,   # Single technical signal
    "LOW":      2,   # Minor anomaly
    "INFO":     1,   # Informational only
}


def detect_volume_spike(stock_data: dict) -> dict | None:
    """Detects if today's volume is unusually high vs 30-day average."""
    vol_ratio = stock_data.get("volume_ratio")
    if vol_ratio is None:
        return None

    if vol_ratio >= 3.0:
        return {
            "type":     "VOLUME_SPIKE",
            "severity": "CRITICAL",
            "score":    SEVERITY["CRITICAL"],
            "message":  f"Volume is {vol_ratio:.1f}x the 30-day average — extreme unusual activity",
            "value":    vol_ratio,
        }
    elif vol_ratio >= 2.0:
        return {
            "type":     "VOLUME_SPIKE",
            "severity": "HIGH",
            "score":    SEVERITY["HIGH"],
            "message":  f"Volume is {vol_ratio:.1f}x the 30-day average — significant spike",
            "value":    vol_ratio,
        }
    elif vol_ratio >= 1.5:
        return {
            "type":     "VOLUME_SPIKE",
            "severity": "MEDIUM",
            "score":    SEVERITY["MEDIUM"],
            "message":  f"Volume is {vol_ratio:.1f}x the 30-day average — moderate increase",
            "value":    vol_ratio,
        }
    return None


def detect_52w_breakout(stock_data: dict) -> dict | None:
    """Detects if stock is at or near its 52-week high — potential breakout."""
    price    = stock_data.get("current_price")
    high_52w = stock_data.get("high_52w")
    low_52w  = stock_data.get("low_52w")

    if not price or not high_52w or not low_52w:
        return None

    pct_from_high = ((price - high_52w) / high_52w) * 100
    pct_from_low  = ((price - low_52w)  / low_52w)  * 100

    if pct_from_high >= 0:
        return {
            "type":     "52W_HIGH_BREAKOUT",
            "severity": "HIGH",
            "score":    SEVERITY["HIGH"],
            "message":  f"Stock hit a NEW 52-week high at ₹{price} (above ₹{high_52w})",
            "value":    pct_from_high,
        }
    elif pct_from_high >= -2:
        return {
            "type":     "NEAR_52W_HIGH",
            "severity": "MEDIUM",
            "score":    SEVERITY["MEDIUM"],
            "message":  f"Stock is within 2% of 52-week high (₹{price} vs ₹{high_52w})",
            "value":    pct_from_high,
        }
    elif pct_from_low <= 5:
        return {
            "type":     "NEAR_52W_LOW",
            "severity": "MEDIUM",
            "score":    SEVERITY["MEDIUM"],
            "message":  f"Stock is near 52-week LOW — potential distress (₹{price} vs low ₹{low_52w})",
            "value":    pct_from_low,
        }
    return None


def detect_bulk_deal_signals(bulk_deals: list, symbol: str) -> list[dict]:
    """Analyzes bulk/block deals for promoter selling patterns."""
    signals = []
    for deal in bulk_deals:
        if deal.get("symbol","").upper() != symbol.upper():
            continue

        is_sell = deal.get("buy_sell","").upper() in ("S", "SELL")
        client  = deal.get("client_name","").upper()
        qty     = deal.get("quantity", 0)
        price   = deal.get("trade_price", 0)
        value_cr = round((qty * price) / 1e7, 1)

        is_promoter = any(kw in client for kw in
                          ["PROMOTER","FOUNDER","DIRECTOR","CMD","MD","CEO"])

        if is_promoter and is_sell:
            signals.append({
                "type":     "PROMOTER_BULK_SELL",
                "severity": "CRITICAL",
                "score":    SEVERITY["CRITICAL"],
                "message":  f"ALERT: Promoter selling {qty:,} shares (₹{value_cr} Cr) "
                            f"via bulk deal — potential distress signal",
                "deal":     deal,
                "value":    value_cr,
            })
        elif is_sell and qty > 500_000:
            signals.append({
                "type":     "LARGE_BULK_SELL",
                "severity": "HIGH",
                "score":    SEVERITY["HIGH"],
                "message":  f"Large bulk sell: {qty:,} shares worth ₹{value_cr} Cr "
                            f"by {deal.get('client_name','')}",
                "deal":     deal,
                "value":    value_cr,
            })
        elif not is_sell:
            signals.append({
                "type":     "BULK_BUY",
                "severity": "MEDIUM",
                "score":    SEVERITY["MEDIUM"],
                "message":  f"Bulk BUY: {qty:,} shares worth ₹{value_cr} Cr — positive interest",
                "deal":     deal,
                "value":    value_cr,
            })
    return signals


def detect_insider_signals(insider_trades: list, symbol: str) -> list[dict]:
    """Detects insider trading patterns."""
    signals = []
    for trade in insider_trades:
        if trade.get("symbol","").upper() != symbol.upper():
            continue

        is_sell  = "sell" in trade.get("transaction","").lower()
        category = trade.get("category","")
        value    = trade.get("value_cr", 0)

        if is_sell and "promoter" in category.lower():
            signals.append({
                "type":     "INSIDER_PROMOTER_SELL",
                "severity": "HIGH",
                "score":    SEVERITY["HIGH"],
                "message":  f"Promoter insider sale of ₹{value} Cr — watch for distress pattern",
                "value":    value,
            })
    return signals


def compute_technical_signals(history_df: pd.DataFrame) -> list[dict]:
    """
    Runs TA indicators on price history.
    Uses the `ta` library (pip install ta) — completely free.
    """
    if history_df is None or len(history_df) < 30:
        return []

    df      = history_df.copy()
    signals = []

    # ── RSI ──────────────────────────────────────────────────────────────────
    df["rsi"] = ta.momentum.RSIIndicator(df["Close"], window=14).rsi()
    latest_rsi = df["rsi"].iloc[-1]

    if not pd.isna(latest_rsi):
        if latest_rsi >= 75:
            signals.append({
                "type":     "RSI_OVERBOUGHT",
                "severity": "HIGH",
                "score":    SEVERITY["HIGH"],
                "message":  f"RSI at {latest_rsi:.1f} — strongly overbought, "
                            f"high risk of pullback",
                "value":    latest_rsi,
            })
        elif latest_rsi >= 70:
            signals.append({
                "type":     "RSI_OVERBOUGHT",
                "severity": "MEDIUM",
                "score":    SEVERITY["MEDIUM"],
                "message":  f"RSI at {latest_rsi:.1f} — overbought territory",
                "value":    latest_rsi,
            })
        elif latest_rsi <= 30:
            signals.append({
                "type":     "RSI_OVERSOLD",
                "severity": "MEDIUM",
                "score":    SEVERITY["MEDIUM"],
                "message":  f"RSI at {latest_rsi:.1f} — oversold, potential reversal",
                "value":    latest_rsi,
            })

    # ── MACD ─────────────────────────────────────────────────────────────────
    macd_ind   = ta.trend.MACD(df["Close"])
    df["macd"] = macd_ind.macd()
    df["macd_signal"] = macd_ind.macd_signal()
    df["macd_hist"]   = macd_ind.macd_diff()

    if len(df) >= 2:
        prev_hist   = df["macd_hist"].iloc[-2]
        latest_hist = df["macd_hist"].iloc[-1]
        if not pd.isna(prev_hist) and not pd.isna(latest_hist):
            if prev_hist < 0 and latest_hist > 0:
                signals.append({
                    "type":     "MACD_BULLISH_CROSSOVER",
                    "severity": "MEDIUM",
                    "score":    SEVERITY["MEDIUM"],
                    "message":  "MACD bullish crossover — momentum turning positive",
                    "value":    latest_hist,
                })
            elif prev_hist > 0 and latest_hist < 0:
                signals.append({
                    "type":     "MACD_BEARISH_CROSSOVER",
                    "severity": "MEDIUM",
                    "score":    SEVERITY["MEDIUM"],
                    "message":  "MACD bearish crossover — momentum turning negative",
                    "value":    latest_hist,
                })

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb       = ta.volatility.BollingerBands(df["Close"])
    upper_bb = bb.bollinger_hband().iloc[-1]
    lower_bb = bb.bollinger_lband().iloc[-1]
    price    = df["Close"].iloc[-1]

    if not pd.isna(upper_bb) and price >= upper_bb:
        signals.append({
            "type":     "BB_UPPER_BREAK",
            "severity": "MEDIUM",
            "score":    SEVERITY["MEDIUM"],
            "message":  f"Price broke above Bollinger upper band (₹{upper_bb:.1f}) — "
                        f"strong momentum or overbought",
            "value":    price,
        })
    elif not pd.isna(lower_bb) and price <= lower_bb:
        signals.append({
            "type":     "BB_LOWER_BREAK",
            "severity": "MEDIUM",
            "score":    SEVERITY["MEDIUM"],
            "message":  f"Price broke below Bollinger lower band (₹{lower_bb:.1f}) — "
                        f"strong selling or oversold",
            "value":    price,
        })

    # ── EMA trend ─────────────────────────────────────────────────────────────
    df["ema20"] = ta.trend.EMAIndicator(df["Close"], window=20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["Close"], window=50).ema_indicator()
    e20 = df["ema20"].iloc[-1]
    e50 = df["ema50"].iloc[-1]

    if not pd.isna(e20) and not pd.isna(e50):
        if e20 > e50 and df["ema20"].iloc[-2] <= df["ema50"].iloc[-2]:
            signals.append({
                "type":     "EMA_GOLDEN_CROSS",
                "severity": "HIGH",
                "score":    SEVERITY["HIGH"],
                "message":  "EMA20 crossed above EMA50 — golden cross, bullish trend signal",
                "value":    e20,
            })
        elif e20 < e50 and df["ema20"].iloc[-2] >= df["ema50"].iloc[-2]:
            signals.append({
                "type":     "EMA_DEATH_CROSS",
                "severity": "HIGH",
                "score":    SEVERITY["HIGH"],
                "message":  "EMA20 crossed below EMA50 — death cross, bearish trend signal",
                "value":    e20,
            })

    return signals


def run_signal_detection(data_package: dict) -> dict:
    """
    Master signal detector — runs all checks and returns
    a scored, sorted list of signals.
    """
    symbol = data_package["symbol"]
    stock  = data_package["stock_data"]
    print(f"[Agent 2] Running signal detection for {symbol}...")

    signals = []

    # 1. Volume
    vol_sig = detect_volume_spike(stock)
    if vol_sig:
        signals.append(vol_sig)

    # 2. 52-week breakout
    breakout_sig = detect_52w_breakout(stock)
    if breakout_sig:
        signals.append(breakout_sig)

    # 3. Bulk deals
    signals += detect_bulk_deal_signals(data_package.get("bulk_deals", []), symbol)

    # 4. Insider trades
    signals += detect_insider_signals(data_package.get("insider_trades", []), symbol)

    # 5. Technical indicators (RSI, MACD, BB, EMA)
    history_df = stock.get("history_df")
    if history_df is not None:
        signals += compute_technical_signals(history_df)

    # Sort by severity score descending
    signals.sort(key=lambda x: x["score"], reverse=True)

    # Compute overall alert level
    max_score = signals[0]["score"] if signals else 0
    if max_score >= 5:
        alert_level = "🔴 CRITICAL"
    elif max_score >= 4:
        alert_level = "🟠 HIGH"
    elif max_score >= 3:
        alert_level = "🟡 MEDIUM"
    else:
        alert_level = "🟢 LOW"

    result = {
        "symbol":           symbol,
        "alert_level":      alert_level,
        "total_signals":    len(signals),
        "signals":          signals,
        "has_bulk_deal":    any(s["type"] in ("PROMOTER_BULK_SELL","LARGE_BULK_SELL","BULK_BUY")
                                for s in signals),
        "has_technical":    any("RSI" in s["type"] or "MACD" in s["type"] or
                                "BB_" in s["type"] or "EMA" in s["type"]
                                for s in signals),
        "top_signal":       signals[0]["message"] if signals else "No significant signals detected",
        "detected_at":      datetime.now().isoformat(),
    }

    print(f"[Agent 2] Found {len(signals)} signals. Alert level: {alert_level}")
    return result


if __name__ == "__main__":
    # Quick test with mock data
    from agent1_data_collector import collect_all_data
    data    = collect_all_data("INFY")
    signals = run_signal_detection(data)
    for s in signals["signals"]:
        print(f"  [{s['severity']}] {s['type']}: {s['message']}")
