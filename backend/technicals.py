"""
Technical indicators computed from OHLCV history.

Pure pandas/numpy over a ``PriceHistory`` — no live connection required, so the
logic is fully unit-testable. Produces the ``Technicals`` model: moving
averages, RSI, MACD, Bollinger Bands, ATR, swing support/resistance, plus a
coarse trend/momentum classification used by the trade-idea engine.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from models import PriceHistory, Technicals

logger = logging.getLogger(__name__)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # When there are no losses in the window RSI is 100 (no gains → 0; flat → 50).
    rsi = rsi.mask((loss == 0) & (gain > 0), 100.0)
    rsi = rsi.mask((loss == 0) & (gain == 0), 50.0)
    return rsi


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _last(series: pd.Series) -> float | None:
    """Last finite value of a series, or None."""
    s = series.dropna()
    return round(float(s.iloc[-1]), 4) if not s.empty else None


def realized_vol_rank(history: PriceHistory, window: int = 30) -> tuple[float, float]:
    """Annualised 30-day realised vol and its rank within the series' 52w range.

    Pure helper so the screener can derive premium-richness from the same
    history it uses for indicators, without a second IBKR round trip.
    Returns ``(current_hv, hv_rank_0_100)``; ``(0.0, 0.0)`` if too short.
    """
    closes = np.array([b.close for b in history.bars], dtype=float)
    if len(closes) < window + 2:
        return 0.0, 0.0
    log_rets = np.log(closes[1:] / closes[:-1])
    hv_series = np.array(
        [log_rets[i - window:i].std() * (252 ** 0.5) for i in range(window, len(log_rets) + 1)]
    )
    current = float(hv_series[-1])
    lo, hi = float(hv_series.min()), float(hv_series.max())
    rank = ((current - lo) / (hi - lo) * 100) if hi > lo else 0.0
    return current, rank


def compute_technicals(history: PriceHistory) -> Technicals:
    """Compute indicators from a price history. Gracefully degrades when the
    series is too short for a given lookback (longer SMAs come back as None)."""
    bars = history.bars
    last_price = round(float(bars[-1].close), 2) if bars else 0.0
    if len(bars) < 2:
        return Technicals(
            symbol=history.symbol,
            as_of=bars[-1].timestamp if bars else __import__("datetime").datetime.utcnow(),
            last_price=last_price,
        )

    df = pd.DataFrame(
        {
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
        }
    )
    close = df["close"]

    sma20 = _last(close.rolling(20).mean())
    sma50 = _last(close.rolling(50).mean())
    sma200 = _last(close.rolling(200).mean())
    rsi14 = _last(_rsi(close))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd = _last(macd_line)
    macd_signal = _last(signal_line)
    macd_hist = (
        round(macd - macd_signal, 4) if macd is not None and macd_signal is not None else None
    )

    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    bb_mid = _last(mid)
    bb_upper = _last(mid + 2 * std)
    bb_lower = _last(mid - 2 * std)
    atr14 = _last(_atr(df))

    # Swing support/resistance from the recent window (last ~60 bars).
    window = df.tail(60)
    support = round(float(window["low"].min()), 2) if not window.empty else None
    resistance = round(float(window["high"].max()), 2) if not window.empty else None

    # Trend: price vs 50/200 SMA. Momentum: RSI extremes.
    trend = "sideways"
    if sma50 is not None:
        if last_price > sma50 and (sma200 is None or sma50 >= sma200):
            trend = "uptrend"
        elif last_price < sma50 and (sma200 is None or sma50 <= sma200):
            trend = "downtrend"

    momentum = "neutral"
    if rsi14 is not None:
        if rsi14 >= 70:
            momentum = "overbought"
        elif rsi14 <= 30:
            momentum = "oversold"

    tech = Technicals(
        symbol=history.symbol,
        as_of=bars[-1].timestamp,
        last_price=last_price,
        sma20=sma20, sma50=sma50, sma200=sma200,
        rsi14=rsi14,
        macd=macd, macd_signal=macd_signal, macd_hist=macd_hist,
        bb_upper=bb_upper, bb_mid=bb_mid, bb_lower=bb_lower,
        atr14=atr14,
        support=support, resistance=resistance,
        trend=trend, momentum=momentum,
    )
    logger.info(
        "technicals symbol=%s last=%.2f trend=%s momentum=%s rsi=%s",
        history.symbol, last_price, trend, momentum, rsi14,
    )
    return tech
