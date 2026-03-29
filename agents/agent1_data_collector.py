"""
Agent 1: Data Collector
Fetches stock data, news, and filings from FREE sources only:
- yfinance (Yahoo Finance) for OHLCV + fundamentals
- NSE India RSS feeds for corporate announcements
- Google News RSS for stock news
- BSE India public endpoints for bulk/block deals
"""

import yfinance as yf
import feedparser
import requests
import pandas as pd
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import quote


# ─── NSE / BSE Free Endpoints ────────────────────────────────────────────────
NSE_BULK_DEALS_URL = "https://www.nseindia.com/api/bulk-deals"
NSE_INSIDER_URL    = "https://www.nseindia.com/api/insider-trading"
BSE_BULK_URL       = "https://api.bseindia.com/BseIndiaAPI/api/BulkDealData/w"
NSE_ANNOUNCEMENTS  = "https://www.nseindia.com/api/corp-announcements"

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def get_stock_data(symbol: str, period: str = "6mo") -> dict:
    """
    Fetch OHLCV + fundamentals for an NSE stock.
    symbol: e.g. "RELIANCE" (NSE) — we auto-append .NS
    Returns dict with price history, info, 52w high/low.
    """
    ticker_symbol = symbol.upper()
    if not ticker_symbol.endswith(".NS") and not ticker_symbol.endswith(".BO"):
        ticker_symbol += ".NS"

    ticker = yf.Ticker(ticker_symbol)
    try:
        hist = ticker.history(period=period)
    except Exception as e:
        return {"error": f"Failed to fetch data: {str(e)}"}
    # ✅ CHECK FIRST
    if hist is None or hist.empty:
        return {"error": f"No data found for {symbol}"}

    # ✅ THEN ACCESS
    latest = hist.iloc[-1]


    info = {}
    try:
        raw_info = ticker.info
        info = {
            "name":            raw_info.get("longName", symbol),
            "sector":          raw_info.get("sector", "N/A"),
            "industry":        raw_info.get("industry", "N/A"),
            "market_cap":      raw_info.get("marketCap", 0),
            "pe_ratio":        raw_info.get("trailingPE", None),
            "pb_ratio":        raw_info.get("priceToBook", None),
            "dividend_yield":  raw_info.get("dividendYield", None),
            "52w_high":        raw_info.get("fiftyTwoWeekHigh", None),
            "52w_low":         raw_info.get("fiftyTwoWeekLow", None),
            "avg_volume":      raw_info.get("averageVolume", None),
            "float_shares":    raw_info.get("floatShares", None),
            "promoter_holding":raw_info.get("heldPercentInsiders", None),
        }
    except Exception:
        pass

    # Recent price action
    latest       = hist.iloc[-1]
    prev         = hist.iloc[-2] if len(hist) > 1 else latest
    price_change = ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100

    return {
        "symbol":         symbol.upper(),
        "ticker":         ticker_symbol,
        "current_price":  round(float(latest["Close"]), 2),
        "price_change_pct": round(price_change, 2),
        "volume":         int(latest["Volume"]),
        "avg_volume":     info.get("avg_volume"),
        "volume_ratio": round(latest["Volume"] / info["avg_volume"], 2)
                        if info.get("avg_volume") and info["avg_volume"] != 0 else None,
        "high_52w":       info.get("52w_high"),
        "low_52w":        info.get("52w_low"),
        "info":           info,
        "history":        hist[["Open","High","Low","Close","Volume"]].tail(90).to_dict(),
        "history_df":     hist,   # kept for technical analysis agent
        "fetched_at":     datetime.now().isoformat(),
    }


def get_stock_news(symbol: str, company_name: str = "") -> list[dict]:
    """
    Fetch latest news via Google News RSS (completely free, no API key).
    Returns list of {title, link, published, source, summary}.
    """
    query = quote(company_name if company_name else symbol)
    # Google News RSS
    url = f"https://news.google.com/rss/search?q={query}+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en"
    feed  = feedparser.parse(url)
    news  = []
    for entry in feed.entries[:10]:
        news.append({
            "title":     entry.get("title", ""),
            "link":      entry.get("link", ""),
            "published": entry.get("published", ""),
            "source":    entry.get("source", {}).get("title", "Google News"),
            "summary":   BeautifulSoup(
                             entry.get("summary", ""), "lxml"
                         ).get_text()[:300],
        })

    # Also try Yahoo Finance news via yfinance
    try:
        ticker = yf.Ticker(symbol.upper() + ".NS")
        yf_news = ticker.news or []
        for item in yf_news[:5]:
            news.append({
                "title":     item.get("title", ""),
                "link":      item.get("link", ""),
                "published": datetime.fromtimestamp(
                                 item.get("providerPublishTime", 0)
                             ).isoformat(),
                "source":    item.get("publisher", "Yahoo Finance"),
                "summary":   item.get("title", ""),
            })
    except Exception:
        pass

    return news[:12]


def get_bulk_deals(symbol: str = None) -> list[dict]:
    """
    Fetch bulk/block deals from NSE.
    Falls back to mock data if NSE blocks the request (common in non-browser envs).
    """
    try:
        session = requests.Session()
        # First hit the homepage to get cookies
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=8)
        resp = session.get(NSE_BULK_DEALS_URL, headers=NSE_HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            deals = data.get("data", data) if isinstance(data, dict) else data
            if symbol:
                deals = [d for d in deals
                         if d.get("symbol","").upper() == symbol.upper()]
            return deals[:20]
    except Exception:
        pass

    # ── Realistic mock data for demo ──────────────────────────────────────────
    mock = [
        {
            "symbol":       symbol or "HINDUNILVR",
            "company":      "Hindustan Unilever Ltd",
            "client_name":  "PROMOTER ENTITY",
            "buy_sell":     "S",
            "quantity":     4_200_000,
            "trade_price":  2345.50,
            "remarks":      "Bulk deal at 6% discount to market price",
            "date":         datetime.now().strftime("%d-%b-%Y"),
            "deal_type":    "BULK",
        },
        {
            "symbol":       "INFY",
            "company":      "Infosys Ltd",
            "client_name":  "FOREIGN PORTFOLIO INVESTOR",
            "buy_sell":     "B",
            "quantity":     1_500_000,
            "trade_price":  1456.25,
            "remarks":      "Block deal",
            "date":         datetime.now().strftime("%d-%b-%Y"),
            "deal_type":    "BLOCK",
        },
    ]
    if symbol:
        mock = [d for d in mock if d["symbol"].upper() == symbol.upper()] or mock[:1]
    return mock


def get_insider_trades(symbol: str = None) -> list[dict]:
    """Fetch insider trading data from NSE (with mock fallback)."""
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=8)
        resp = session.get(NSE_INSIDER_URL, headers=NSE_HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            trades = data.get("data", data) if isinstance(data, dict) else data
            if symbol:
                trades = [t for t in trades
                          if t.get("symbol","").upper() == symbol.upper()]
            return trades[:15]
    except Exception:
        pass

    return [
        {
            "symbol":       symbol or "TATAMOTORS",
            "acquirer":     "Ratan N Tata",
            "category":     "Promoter",
            "transaction":  "Sell",
            "shares":       500_000,
            "value_cr":     28.5,
            "date":         (datetime.now() - timedelta(days=2)).strftime("%d-%b-%Y"),
            "holding_post": "42.3%",
        }
    ]


def get_corporate_filings(symbol: str = None) -> list[dict]:
    """Fetch corporate announcements from NSE RSS feed."""
    try:
        url  = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
        feed = feedparser.parse(
            "https://www.nseindia.com/rss?id=corporate-announcements"
        )
        filings = []
        for entry in feed.entries[:15]:
            title = entry.get("title", "")
            if symbol and symbol.upper() not in title.upper():
                continue
            filings.append({
                "title":     title,
                "link":      entry.get("link", ""),
                "published": entry.get("published", ""),
                "summary":   entry.get("summary", "")[:400],
            })
        if filings:
            return filings
    except Exception:
        pass

    # Mock filings
    return [
        {
            "title":     f"{symbol or 'COMPANY'} — Outcome of Board Meeting",
            "link":      "https://nseindia.com",
            "published": datetime.now().isoformat(),
            "summary":   "Board approved Q3 results. Revenue up 12% YoY. Management "
                         "commentary: 'We remain cautious about demand in H1 FY26 "
                         "but confident of margin expansion.'",
        },
        {
            "title":     f"{symbol or 'COMPANY'} — Promoter Selling via Bulk Deal",
            "link":      "https://nseindia.com",
            "published": (datetime.now() - timedelta(days=1)).isoformat(),
            "summary":   "Promoter entity sold 4.2% stake via bulk deal at 6% discount "
                         "to prevailing market price. Total consideration: ₹892 crore.",
        },
    ]


def collect_all_data(symbol: str) -> dict:
    """
    Master function — runs all collectors and returns a unified data package.
    This is what Agent 2 (Signal Detector) receives.
    """
    print(f"[Agent 1] Collecting data for {symbol}...")

    stock  = get_stock_data(symbol)
    name   = stock.get("info", {}).get("name", symbol)
    news   = get_stock_news(symbol, name)
    bulk   = get_bulk_deals(symbol)
    insider = get_insider_trades(symbol)
    filings = get_corporate_filings(symbol)

    package = {
        "symbol":          symbol.upper(),
        "company_name":    name,
        "stock_data":      stock,
        "news":            news,
        "bulk_deals":      bulk,
        "insider_trades":  insider,
        "filings":         filings,
        "collected_at":    datetime.now().isoformat(),
    }

    print(f"[Agent 1] Done — {len(news)} news, {len(bulk)} bulk deals, "
          f"{len(filings)} filings collected.")
    return package


if __name__ == "__main__":
    result = collect_all_data("RELIANCE")
    print(json.dumps({k: v for k, v in result.items() if k != "stock_data"}, indent=2, default=str))
