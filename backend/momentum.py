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

# Per-symbol price cache: symbol -> (fetched_on, Series of adjusted close).
_CACHE: dict[str, tuple[date, pd.Series]] = {}
_LOOKBACK_YEARS = 6


def _fetch_yahoo(symbol: str) -> pd.Series | None:
    end = datetime.utcnow()
    start = end - timedelta(days=365 * _LOOKBACK_YEARS)
    try:
        r = httpx.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"period1": int(start.timestamp()), "period2": int(end.timestamp()),
                    "interval": "1d"}, headers=_H, timeout=25,
        )
        d = r.json()["chart"]["result"][0]
        ts = pd.to_datetime(d["timestamp"], unit="s").normalize()
        s = pd.Series(d["indicators"]["adjclose"][0]["adjclose"], index=ts, name=symbol).dropna()
        return s[~s.index.duplicated()]
    except Exception as exc:
        logger.warning("momentum fetch failed symbol=%s err=%r", symbol, repr(exc)[:80])
        return None


def get_prices(symbols: list[str]) -> pd.DataFrame:
    """Cached price panel (adjusted close), artifact-cleaned. Always includes SPY+GLD."""
    today = datetime.utcnow().date()
    want = list(dict.fromkeys([s.upper() for s in symbols] + [BENCH, SAFE]))
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


def rank_universe(symbols: list[str]) -> list[dict]:
    """Current residual-momentum ranking: trend, mkt_adj, score per name (desc)."""
    px = get_prices(symbols)
    bench = px[BENCH]
    stocks = [c for c in px.columns if c not in (BENCH, SAFE)]
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


def backtest(symbols: list[str], start: str, end: str, cost_bps: float = 10.0) -> dict:
    """Weekly residual-momentum backtest over the given universe vs SPY."""
    px = get_prices(symbols)
    bench, safe = px[BENCH], px[SAFE]
    stocks = [c for c in px.columns if c not in (BENCH, SAFE)]
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
        keep = sorted([h for h in holdings if rk.get(h, 1e9) <= BUFFER], key=lambda x: rk[x])[:N_HOLD]
        new = list(keep)
        for s in order:
            if len(new) >= N_HOLD:
                break
            if s not in new:
                new.append(s)
        turnover = len(set(new) ^ set(holdings)) / 2 / N_HOLD if holdings else 1.0
        holdings = new
        if not holdings:
            continue
        wk = (px.loc[nxt, holdings] / px.loc[dt, holdings] - 1).dropna()
        basket = float(wk.clip(-0.6, 0.6).mean()) if len(wk) else 0.0
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
