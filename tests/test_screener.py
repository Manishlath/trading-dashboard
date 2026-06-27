"""Tests for the screener — IBKR + StockAnalysis are mocked, no live connection."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from models import Fundamentals, PriceBar, PriceHistory  # noqa: E402
from screener import screen_universe  # noqa: E402


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _history(symbol: str, closes: list[float]) -> PriceHistory:
    base = datetime(2025, 1, 1)
    bars = [
        PriceBar(timestamp=base + timedelta(days=i), open=c, high=c * 1.01,
                 low=c * 0.99, close=c, volume=1_000_000)
        for i, c in enumerate(closes)
    ]
    return PriceHistory(symbol=symbol, timeframe="1d", bars=bars)


def _fundamentals(symbol: str, *, peg: float, net_margin: float, roe: float) -> Fundamentals:
    return Fundamentals(
        symbol=symbol, fetched_at=datetime(2026, 6, 26),
        peg_ratio=peg, net_margin=net_margin, roe=roe,
        pe_ratio=30.0, forward_pe=20.0,
    )


class TestScreenUniverse:
    def _mocks(self):
        # GOODCO: strong uptrend + cheap PEG + fat margins  -> high bullish score.
        # WEAKCO: downtrend + stretched PEG                 -> bearish score.
        # FLATCO: sideways, neutral fundamentals            -> low score.
        hist = {
            "GOODCO": _history("GOODCO", [100 + i for i in range(150)]),
            "WEAKCO": _history("WEAKCO", [300 - i for i in range(150)]),
            "FLATCO": _history("FLATCO", [100 + (i % 4) for i in range(150)]),
        }
        funds = {
            "GOODCO": _fundamentals("GOODCO", peg=0.5, net_margin=0.30, roe=0.25),
            "WEAKCO": _fundamentals("WEAKCO", peg=4.0, net_margin=0.05, roe=0.05),
            "FLATCO": _fundamentals("FLATCO", peg=2.0, net_margin=0.10, roe=0.10),
        }
        ibkr = AsyncMock()
        ibkr.get_price_history.side_effect = lambda s, **k: hist[s]
        sa = AsyncMock()
        sa.get_fundamentals.side_effect = lambda s: funds[s]
        return ibkr, sa

    def test_ranks_and_returns_all(self):
        ibkr, sa = self._mocks()
        result = run(screen_universe(ibkr, sa, ["FLATCO", "GOODCO", "WEAKCO"]))
        assert len(result.candidates) == 3
        assert {c.symbol for c in result.candidates} == {"GOODCO", "WEAKCO", "FLATCO"}

    def test_ranked_by_absolute_conviction_descending(self):
        ibkr, sa = self._mocks()
        result = run(screen_universe(ibkr, sa, ["FLATCO", "GOODCO", "WEAKCO"]))
        # Contract: candidates are ordered by |score| descending.
        convictions = [abs(c.score) for c in result.candidates]
        assert convictions == sorted(convictions, reverse=True)
        # A strong-signal name leads, not the neutral one.
        assert result.candidates[0].symbol in {"GOODCO", "WEAKCO"}

    def test_bias_direction_matches_signals(self):
        ibkr, sa = self._mocks()
        result = run(screen_universe(ibkr, sa, ["GOODCO", "WEAKCO"]))
        by = {c.symbol: c for c in result.candidates}
        assert by["GOODCO"].bias == "bullish" and by["GOODCO"].score > 0
        assert by["WEAKCO"].bias == "bearish" and by["WEAKCO"].score < 0

    def test_failed_symbol_is_skipped_not_fatal(self):
        ibkr, sa = self._mocks()

        async def _hist(s, **k):
            if s == "BADCO":
                raise RuntimeError("no data")
            return _history(s, [100 + i for i in range(150)])

        ibkr.get_price_history.side_effect = _hist
        sa.get_fundamentals.side_effect = lambda s: _fundamentals(s, peg=0.5, net_margin=0.3, roe=0.25)
        result = run(screen_universe(ibkr, sa, ["GOODCO", "BADCO"]))
        assert {c.symbol for c in result.candidates} == {"GOODCO"}

    def test_works_without_fundamentals_source(self):
        ibkr, _ = self._mocks()
        result = run(screen_universe(ibkr, None, ["GOODCO"]))
        assert len(result.candidates) == 1
        assert result.candidates[0].peg_ratio is None  # no fundamentals supplied
