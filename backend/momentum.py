"""
Residual (market-adjusted) momentum engine for the dashboard.

Reproduces the validated backtest: rank a universe by blended 12-1 / 6-1 price
momentum *minus* beta×SPY momentum (the "Mkt Adj"), hold the top 10 equal weight
with a top-20 buffer and a SPY-200-day safety overlay (100% / 50-50 GLD).

Data comes from Yahoo's public chart API (no auth) and is cached per-symbol for
the day, so editing the universe in the UI recalculates fast. Daily returns are
clipped at ±30% to neutralise split/spinoff artifacts.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BENCH, SAFE = "SPY", "GLD"
N_HOLD, BUFFER = 10, 20

# NIFTY 50 constituents (Yahoo NSE tickers). Benchmark = NIFTY 50 index,
# safe asset = Nippon Gold BeES ETF.
NIFTY_UNIVERSE = sorted(set([
    "ADANIENT.NS","ADANIPORTS.NS","APOLLOHOSP.NS","ASIANPAINT.NS","AXISBANK.NS","BAJAJ-AUTO.NS",
    "BAJFINANCE.NS","BAJAJFINSV.NS","BEL.NS","BHARTIARTL.NS","CIPLA.NS","COALINDIA.NS",
    "DRREDDY.NS","EICHERMOT.NS","GRASIM.NS","HCLTECH.NS","HDFCBANK.NS","HDFCLIFE.NS",
    "HEROMOTOCO.NS","HINDALCO.NS","HINDUNILVR.NS","ICICIBANK.NS","INDUSINDBK.NS","INFY.NS",
    "ITC.NS","JSWSTEEL.NS","KOTAKBANK.NS","LT.NS","M&M.NS","MARUTI.NS","NESTLEIND.NS","NTPC.NS",
    "ONGC.NS","POWERGRID.NS","RELIANCE.NS","SBILIFE.NS","SBIN.NS","SHRIRAMFIN.NS","SUNPHARMA.NS",
    "TATACONSUM.NS","TATAMOTORS.NS","TATASTEEL.NS","TCS.NS","TECHM.NS","TITAN.NS","TRENT.NS",
    "ULTRACEMCO.NS","WIPRO.NS",
]))

# Market configs: universe + benchmark + defensive asset per market.
MARKETS: dict[str, dict] = {
    "us": {"universe": None, "bench": "SPY", "safe": "GLD"},          # universe set below
    "india": {"universe": NIFTY_UNIVERSE, "bench": "^NSEI", "safe": "GOLDBEES.NS"},
}
_H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Default broad large/mid-cap universe (editable from the UI).
DEFAULT_UNIVERSE = sorted(set([
    "AAPL","ABBV","ABT","ACN","ADBE","ADI","AIG","AMAT","AMD","AMGN","AMT","AMZN","ANET","AVGO",
    "AXP","BA","BAC","BK","BKNG","BLK","BMY","C","CAT","CDNS","CHTR","CI","CL","CMCSA","CMG","COF",
    "COP","COST","CRM","CSCO","CSX","CVS","CVX","DE","DHR","DIS","DOW","DUK","ELV","EMR","EOG",
    "ETN","F","FDX","FTNT","GD","GE","GILD","GLW","GM","GOOGL","GS","HD","HON","HPQ","HUM","IBM",
    "INTC","INTU","ISRG","ITW","JNJ","JPM","KLAC","KO","LIN","LLY","LMT","LOW","LRCX","MA","MCD",
    "MCHP","MDLZ","MDT","MET","META","MMM","MO","MPC","MRK","MRVL","MS","MSFT","MU","NEE","NFLX",
    "NKE","NSC","NVDA","NXPI","ON","ORCL","ORLY","OXY","PANW","PEP","PFE","PG","PM","PNC","PSX",
    "QCOM","REGN","ROST","RTX","SBUX","SCHW","SLB","SNPS","SO","STX","T","TGT","TJX","TMO",
    "TMUS","TXN","UNH","UNP","UPS","USB","V","VLO","VRTX","VZ","WDC","WFC","WMT","XOM",
]))

MARKETS["us"]["universe"] = DEFAULT_UNIVERSE

# Sector map for risk caps. "tech_hw" is the semis/AI-hardware sleeve used by
# the SMH circuit breaker. Names not listed fall into "other" (never capped).
SECTOR: dict[str, str] = {}
for _sec, _names in {
    "tech_hw": ["AMD","AMAT","ADI","AVGO","CDNS","GLW","INTC","KLAC","LRCX","MCHP","MRVL","MU",
                "NVDA","NXPI","ON","QCOM","SNPS","STX","TXN","WDC","ANET","HPQ"],
    "tech_soft": ["AAPL","MSFT","GOOGL","META","ADBE","CRM","INTU","NFLX","ORCL","PANW","FTNT",
                  "IBM","ACN","PYPL"],
    "financials": ["AXP","BAC","BK","BLK","C","COF","GS","JPM","MA","MET","MS","PNC","SCHW",
                   "USB","V","WFC","AIG"],
    "energy": ["COP","CVX","EOG","MPC","OXY","PSX","SLB","VLO","XOM"],
    "healthcare": ["ABBV","ABT","AMGN","BMY","CI","CVS","DHR","ELV","GILD","HUM","ISRG","JNJ",
                   "LLY","MDT","MRK","PFE","REGN","TMO","UNH","VRTX"],
    "consumer": ["AMZN","BKNG","CMG","COST","HD","KO","LOW","MCD","MDLZ","MO","NKE","ORLY","PEP",
                 "PG","PM","ROST","SBUX","TGT","TJX","WMT","F","GM","CL","DIS"],
    "industrials": ["BA","CAT","CSX","DE","EMR","ETN","FDX","GD","GE","HON","ITW","LMT","MMM",
                    "NSC","RTX","UNP","UPS"],
    "util_telecom": ["AMT","DUK","NEE","SO","T","TMUS","VZ","CMCSA","CHTR"],
    "materials": ["DOW","LIN"],
}.items():
    for _n in _names:
        SECTOR[_n] = _sec

SEMI_ETF = "SMH"   # sector circuit-breaker reference for the tech_hw sleeve

# Per-symbol price cache: symbol -> (fetched_on, Series of adjusted close).
_CACHE: dict[str, tuple[date, pd.Series]] = {}
_LOOKBACK_YEARS = 9


class MomentumDataError(RuntimeError):
    """Raised when required price data (a benchmark or too many names) is missing."""


def _fetch_yahoo(symbol: str, attempts: int = 3) -> pd.Series | None:
    """Fetch daily adjusted close from Yahoo, retrying transient failures.

    Yahoo intermittently drops requests (rate limiting, brief 5xx, host
    hiccups). Retrying with a short backoff — and failing over to the query2
    host — turns most one-off failures into successes, which matters most for
    the benchmark/safe symbols whose absence would break the whole ranking.
    """
    from urllib.parse import quote
    end = datetime.utcnow()
    start = end - timedelta(days=365 * _LOOKBACK_YEARS)
    enc = quote(symbol, safe="")
    for attempt in range(1, attempts + 1):
        host = "query1" if attempt % 2 else "query2"
        try:
            r = httpx.get(
                f"https://{host}.finance.yahoo.com/v8/finance/chart/{enc}",
                params={"period1": int(start.timestamp()), "period2": int(end.timestamp()),
                        "interval": "1d"}, headers=_H, timeout=25,
            )
            d = r.json()["chart"]["result"][0]
            ts = pd.to_datetime(d["timestamp"], unit="s").normalize()
            s = pd.Series(d["indicators"]["adjclose"][0]["adjclose"], index=ts, name=symbol).dropna()
            return s[~s.index.duplicated()]
        except Exception as exc:
            if attempt == attempts:
                logger.warning("momentum fetch failed symbol=%s err=%r", symbol, repr(exc)[:80])
            else:
                time.sleep(0.4 * attempt)
    return None


def get_prices(symbols: list[str], bench: str = BENCH, safe: str = SAFE) -> pd.DataFrame:
    """Cached price panel (adjusted close), artifact-cleaned. Includes bench + safe assets."""
    today = datetime.utcnow().date()
    want = list(dict.fromkeys([s.upper() for s in symbols] + [bench, safe]))
    series: dict[str, pd.Series] = {}
    for s in want:
        hit = _CACHE.get(s)
        if hit and hit[0] == today:
            series[s] = hit[1]
            continue
        v = _fetch_yahoo(s)
        if v is not None and len(v) > 300:
            _CACHE[s] = (today, v)
            series[s] = v
        time.sleep(0.05)

    # The benchmark and safe asset are load-bearing — without them the score /
    # backtest can't be computed. Fail with a clear, actionable message instead
    # of a KeyError → opaque 500 downstream.
    missing = [s for s in (bench, safe) if s not in series]
    if missing:
        raise MomentumDataError(
            f"could not fetch required data for {', '.join(missing)} from Yahoo "
            "(transient rate-limit or outage) — please retry in a moment."
        )
    stock_cols = [c for c in series if c not in (bench, safe)]
    if len(stock_cols) < 12:
        raise MomentumDataError(
            f"only {len(stock_cols)} of the requested symbols returned data — "
            "too few to rank; retry in a moment or check the tickers."
        )

    px = pd.DataFrame(series).sort_index().ffill()
    # Clip daily log-returns at ±30% to remove split/spinoff artifacts.
    px = np.exp(np.log(px).diff().clip(-0.30, 0.30).cumsum())
    return px


# Weight on the low-beta (market-adjustment) tilt relative to momentum strength.
_BETA_WEIGHT = 0.5


def _zrows(panel: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score: standardise each date across the universe."""
    return panel.sub(panel.mean(axis=1), axis=0).div(panel.std(axis=1).replace(0, np.nan), axis=0)


def _score_panels(px: pd.DataFrame, bench: pd.Series):
    """Standardised residual momentum.

    trend = z-scored blended 12-1 / 6-1 momentum (strength vs the universe).
    mkt_adj = -beta_weight * z-scored beta (penalise high market sensitivity).
    score = trend + mkt_adj.
    """
    m12_1 = px.shift(21) / px.shift(252) - 1
    m6_1 = px.shift(21) / px.shift(126) - 1
    trend = _zrows(0.5 * m12_1 + 0.5 * m6_1)
    spy_d = bench.pct_change()
    beta = px.pct_change().rolling(126).cov(spy_d).div(spy_d.rolling(126).var(), axis=0)
    mkt_adj = -_BETA_WEIGHT * _zrows(beta)
    return trend, mkt_adj, trend + mkt_adj


def rank_universe(symbols: list[str], market: str = "us") -> list[dict]:
    """Current residual-momentum ranking: trend, mkt_adj, score per name (desc)."""
    cfg = MARKETS.get(market, MARKETS["us"])
    b, sf = cfg["bench"], cfg["safe"]
    px = get_prices(symbols, b, sf)
    bench = px[b]
    stocks = [c for c in px.columns if c not in (b, sf)]
    trend, mkt_adj, score = _score_panels(px[stocks], bench)
    dt = px.index[-1]
    sc = score.loc[dt].dropna().sort_values(ascending=False)
    out = []
    for r, (sym, val) in enumerate(sc.items(), start=1):
        out.append({
            "ticker": sym, "rank": r,
            "trend": round(float(trend.loc[dt, sym]), 3),
            "mkt_adj": round(float(mkt_adj.loc[dt, sym]), 3),
            "score": round(float(val), 3),
            "selected": r <= N_HOLD,
        })
    return out


def backtest(symbols: list[str], start: str, end: str, cost_bps: float = 10.0,
             market: str = "us", sector_cap: int = 0, semi_breaker: bool = False) -> dict:
    """Weekly residual-momentum backtest over the given universe vs its benchmark.

    Risk controls (opt-in):
      sector_cap   — max holdings per known sector (0 = off; "other" never capped).
      semi_breaker — when SMH < its 200-day SMA, halve the tech_hw sleeve's
                     weight (freed weight sits in cash for the week).
    """
    cfg = MARKETS.get(market, MARKETS["us"])
    bsym, sfsym = cfg["bench"], cfg["safe"]
    extra = [SEMI_ETF] if semi_breaker else []
    px = get_prices(symbols + extra, bsym, sfsym)
    bench, safe = px[bsym], px[sfsym]
    smh = px[SEMI_ETF] if semi_breaker and SEMI_ETF in px.columns else None
    smh_sma = smh.rolling(200).mean() if smh is not None else None
    stocks = [c for c in px.columns if c not in (bsym, sfsym, SEMI_ETF)]
    _, _, score = _score_panels(px[stocks], bench)        # standardised residual

    a, b = pd.Timestamp(start), pd.Timestamp(end)
    test = px.index[(px.index >= a) & (px.index <= b)]
    if len(test) < 30:
        return {"error": "window too short or no data"}
    first: dict = {}
    for d in test:
        iso = d.isocalendar()
        first.setdefault((iso.year, iso.week), d)
    rebal = sorted(first.values())
    spy_sma = bench.rolling(200).mean()

    holdings: list[str] = []
    eq, eqb, rets, curve, holds_last = 1.0, 1.0, [], [], []
    for i, dt in enumerate(rebal):
        nxt = rebal[i + 1] if i + 1 < len(rebal) else test[-1]
        rk = score.loc[dt].dropna().rank(ascending=False)
        order = rk.sort_values().index

        def _fits(cand: str, chosen: list[str]) -> bool:
            if not sector_cap:
                return True
            sec = SECTOR.get(cand)
            if sec is None:
                return True                      # unknown sector: never capped
            return sum(1 for c in chosen if SECTOR.get(c) == sec) < sector_cap

        keep = []
        for h in sorted([h for h in holdings if rk.get(h, 1e9) <= BUFFER], key=lambda x: rk[x]):
            if len(keep) < N_HOLD and _fits(h, keep):
                keep.append(h)
        new = list(keep)
        for s in order:
            if len(new) >= N_HOLD:
                break
            if s not in new and _fits(s, new):
                new.append(s)
        turnover = len(set(new) ^ set(holdings)) / 2 / N_HOLD if holdings else 1.0
        holdings = new
        if not holdings:
            continue
        wk = (px.loc[nxt, holdings] / px.loc[dt, holdings] - 1).dropna().clip(-0.6, 0.6)
        # Sector circuit breaker: SMH below its 200DMA -> tech_hw names run at
        # half weight, freed weight sits in cash (earns 0) for the week.
        if smh is not None and smh.asof(dt) < smh_sma.asof(dt):
            w = pd.Series({h: (0.5 if SECTOR.get(h) == "tech_hw" else 1.0) for h in wk.index})
            basket = float((wk * w).sum() / N_HOLD)
        else:
            basket = float(wk.mean()) if len(wk) else 0.0
        if bench.asof(dt) < spy_sma.asof(dt):
            basket = 0.5 * basket + 0.5 * float(safe.asof(nxt) / safe.asof(dt) - 1)
        basket -= turnover * cost_bps / 10000.0
        eq *= 1 + basket
        eqb *= 1 + float(bench.asof(nxt) / bench.asof(dt) - 1)
        rets.append((dt, basket))
        curve.append({"date": dt.strftime("%Y-%m-%d"), "strategy": round((eq - 1) * 100, 2),
                      "spy": round((eqb - 1) * 100, 2)})
        holds_last = holdings

    rdf = pd.DataFrame([(d.year, r) for d, r in rets], columns=["yr", "r"])
    yearly = []
    eqb_y = {}
    for yr, g in rdf.groupby("yr"):
        yearly.append({"year": int(yr), "strategy": round((np.prod(1 + g.r) - 1) * 100, 2)})
    days = max((test[-1] - test[0]).days, 1)
    eqcurve = np.cumprod([1.0] + [1.0 + r for _, r in rets])
    dd = float((eqcurve / np.maximum.accumulate(eqcurve) - 1).min() * 100)
    return {
        "start": str(test[0].date()), "end": str(test[-1].date()),
        "rebalances": len(rets),
        "total_return": round((eq - 1) * 100, 2),
        "cagr": round((eq ** (365 / days) - 1) * 100, 2),
        "max_drawdown": round(dd, 2),
        "spy_total": round((eqb - 1) * 100, 2),
        "excess_vs_spy": round((eq - eqb) * 100, 2),
        "curve": curve,
        "yearly": yearly,
        "current_holdings": holds_last,
    }
