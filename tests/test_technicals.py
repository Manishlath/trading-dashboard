"""Tests for the technicals module — pure computation, no TWS."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from models import PriceBar, PriceHistory  # noqa: E402
from technicals import compute_technicals  # noqa: E402


def _history(closes: list[float], symbol: str = "TST") -> PriceHistory:
    base = datetime(2025, 1, 1)
    bars = [
        PriceBar(
            timestamp=base + timedelta(days=i),
            open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1_000_000,
        )
        for i, c in enumerate(closes)
    ]
    return PriceHistory(symbol=symbol, timeframe="1d", bars=bars)


class TestComputeTechnicals:
    def test_uptrend_detected_on_rising_series(self):
        closes = [100 + i for i in range(120)]   # steadily rising
        t = compute_technicals(_history(closes))
        assert t.trend == "uptrend"
        assert t.last_price == closes[-1]
        assert t.sma20 is not None and t.sma50 is not None
        assert t.last_price > t.sma50

    def test_downtrend_detected_on_falling_series(self):
        closes = [300 - i for i in range(120)]
        t = compute_technicals(_history(closes))
        assert t.trend == "downtrend"
        assert t.last_price < t.sma50

    def test_rsi_overbought_on_monotonic_rise(self):
        closes = [100 + i for i in range(60)]
        t = compute_technicals(_history(closes))
        assert t.rsi14 is not None and t.rsi14 >= 70
        assert t.momentum == "overbought"

    def test_support_resistance_within_range(self):
        closes = [100 + (i % 10) for i in range(80)]
        t = compute_technicals(_history(closes))
        assert t.support is not None and t.resistance is not None
        assert t.support <= t.last_price <= t.resistance

    def test_short_series_degrades_gracefully(self):
        t = compute_technicals(_history([100, 101, 102]))
        assert t.last_price == 102
        assert t.sma200 is None       # not enough bars
        assert t.macd is not None     # EMA-based, defined from bar 2

    def test_macd_hist_positive_in_uptrend(self):
        closes = [100 + i * 0.5 for i in range(80)]
        t = compute_technicals(_history(closes))
        assert t.macd_hist is not None and t.macd_hist > 0
