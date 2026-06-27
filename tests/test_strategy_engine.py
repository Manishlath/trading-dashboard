"""Tests for the final trade-idea generation engine (pure functions, no TWS)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from datetime import datetime  # noqa: E402

from models import OptionContract, Technicals  # noqa: E402
from strategy_engine import TradeIdeaError, generate_trade_idea  # noqa: E402


def _put(strike: float, bid: float, ask: float, *, oi=500, vol=100) -> OptionContract:
    return OptionContract(
        symbol="TST", expiry="2026-07-10", strike=strike, opt_type="put",
        bid=bid, ask=ask, last=(bid + ask) / 2, open_interest=oi, volume=vol,
    )


def _call(strike: float, bid: float, ask: float) -> OptionContract:
    return OptionContract(
        symbol="TST", expiry="2026-07-10", strike=strike, opt_type="call",
        bid=bid, ask=ask, last=(bid + ask) / 2,
    )


def _calls_above_100() -> list[OptionContract]:
    return [
        _call(102.5, 2.50, 2.60),
        _call(105.0, 1.80, 1.90),
        _call(107.5, 1.25, 1.35),
        _call(110.0, 0.85, 0.95),
    ]


def _bearish_tech() -> Technicals:
    return Technicals(
        symbol="TST", as_of=datetime(2026, 6, 26), last_price=100.0,
        sma50=110.0, sma200=115.0, rsi14=74.0, macd_hist=-0.5,
        trend="downtrend", momentum="overbought",
    )


def _chain_puts() -> list[OptionContract]:
    # Monotonic OTM puts below a 100 spot.
    return [
        _put(97.5, 2.50, 2.60),
        _put(95.0, 1.80, 1.90),
        _put(92.5, 1.25, 1.35),
        _put(90.0, 0.85, 0.95),
    ]


class TestGenerateTradeIdea:
    def test_builds_bull_put_credit_spread(self):
        idea = generate_trade_idea(
            symbol="TST", spot=100.0, expiry="2026-07-10", days_to_expiry=14,
            put_contracts=_chain_puts(), hv30=0.40, iv_rank=60.0,
        )
        assert idea.strategy == "Bull put credit spread"
        assert len(idea.legs) == 2
        sell = next(l for l in idea.legs if l.action == "sell")
        buy = next(l for l in idea.legs if l.action == "buy")
        # Short strike must be above the long (protective) strike.
        assert sell.strike > buy.strike
        assert sell.opt_type == "put" and buy.opt_type == "put"

    def test_credit_and_risk_are_consistent(self):
        idea = generate_trade_idea(
            symbol="TST", spot=100.0, expiry="2026-07-10", days_to_expiry=14,
            put_contracts=_chain_puts(), hv30=0.40, iv_rank=60.0,
        )
        sell = next(l for l in idea.legs if l.action == "sell")
        buy = next(l for l in idea.legs if l.action == "buy")
        width = (sell.strike - buy.strike) * 100
        # Credit positive, and max profit + max loss == spread width (×100).
        assert idea.net_credit > 0
        assert idea.max_profit == idea.net_credit
        assert idea.max_loss > 0
        assert idea.max_profit + idea.max_loss == pytest.approx(width, abs=1.0)
        assert 0 < idea.prob_of_profit < 100

    def test_breakeven_below_short_strike(self):
        idea = generate_trade_idea(
            symbol="TST", spot=100.0, expiry="2026-07-10", days_to_expiry=14,
            put_contracts=_chain_puts(), hv30=0.40, iv_rank=60.0,
        )
        sell = next(l for l in idea.legs if l.action == "sell")
        assert idea.breakevens[0] < sell.strike

    def test_falls_back_to_model_when_quotes_missing(self):
        # No bid/ask → engine must model both legs and still produce a credit.
        puts = [
            OptionContract(symbol="TST", expiry="2026-07-10", strike=k, opt_type="put")
            for k in (97.5, 95.0, 92.5, 90.0)
        ]
        idea = generate_trade_idea(
            symbol="TST", spot=100.0, expiry="2026-07-10", days_to_expiry=14,
            put_contracts=puts, hv30=0.40, iv_rank=20.0,
        )
        assert idea.net_credit > 0
        assert "model" in idea.thesis.lower()

    def test_bearish_signals_pick_bear_call_spread(self):
        idea = generate_trade_idea(
            symbol="TST", spot=100.0, expiry="2026-07-10", days_to_expiry=14,
            put_contracts=_chain_puts(), call_contracts=_calls_above_100(),
            hv30=0.40, iv_rank=60.0, technicals=_bearish_tech(),
        )
        assert idea.strategy == "Bear call credit spread"
        assert idea.direction == "neutral-bearish"
        sell = next(l for l in idea.legs if l.action == "sell")
        buy = next(l for l in idea.legs if l.action == "buy")
        # Call spread: both calls above spot, long strike above short, BE above short.
        assert sell.opt_type == "call" and buy.opt_type == "call"
        assert buy.strike > sell.strike
        assert idea.breakevens[0] > sell.strike
        assert idea.net_credit > 0
        assert any("downtrend" in s.lower() for s in idea.signals)

    def test_signals_populated_from_technicals(self):
        idea = generate_trade_idea(
            symbol="TST", spot=100.0, expiry="2026-07-10", days_to_expiry=14,
            put_contracts=_chain_puts(), hv30=0.40, iv_rank=60.0,
        )
        assert isinstance(idea.signals, list) and len(idea.signals) >= 1

    def test_liquid_chain_passes_gate_and_reports_slippage(self):
        idea = generate_trade_idea(
            symbol="TST", spot=100.0, expiry="2026-07-10", days_to_expiry=14,
            put_contracts=_chain_puts(), hv30=0.40, iv_rank=60.0,
        )
        assert idea.liquidity_ok is True
        assert idea.liquidity_warnings == []
        # Tight 0.10-wide spreads on 2 legs → half-spread 0.05 each → $10 entry slippage.
        assert idea.est_slippage == pytest.approx(10.0, abs=0.5)
        # Per-leg liquidity surfaced for the UI.
        assert all(l.spread_pct is not None and l.open_interest for l in idea.legs)

    def test_wide_spreads_flag_illiquid_with_warnings(self):
        wide = [
            _put(97.5, 2.00, 3.00, oi=5),   # ~40% spread, thin OI
            _put(95.0, 1.40, 2.40, oi=5),
            _put(92.5, 1.00, 1.80, oi=5),
            _put(90.0, 0.60, 1.40, oi=5),
        ]
        idea = generate_trade_idea(
            symbol="TST", spot=100.0, expiry="2026-07-10", days_to_expiry=14,
            put_contracts=wide, hv30=0.40, iv_rank=60.0,
        )
        assert idea.liquidity_ok is False
        assert any("spread is wide" in w for w in idea.liquidity_warnings)
        assert any("open interest is thin" in w for w in idea.liquidity_warnings)
        assert "Caution" in idea.thesis

    def test_prefers_liquid_strike_over_closer_delta_illiquid_one(self):
        # 97.5 is nearest the ~30Δ target but has a wide spread; 95 is liquid.
        mixed = [
            _put(97.5, 2.00, 3.20, oi=3),   # illiquid (wide + thin)
            _put(95.0, 1.80, 1.90, oi=800),  # liquid
            _put(92.5, 1.25, 1.35, oi=800),
            _put(90.0, 0.85, 0.95, oi=800),
        ]
        idea = generate_trade_idea(
            symbol="TST", spot=100.0, expiry="2026-07-10", days_to_expiry=14,
            put_contracts=mixed, hv30=0.40, iv_rank=60.0,
        )
        sell = next(l for l in idea.legs if l.action == "sell")
        assert sell.strike != 97.5      # skipped the illiquid near-delta strike
        assert idea.liquidity_ok is True

    def test_raises_without_spot(self):
        with pytest.raises(TradeIdeaError):
            generate_trade_idea(
                symbol="TST", spot=0.0, expiry="2026-07-10", days_to_expiry=14,
                put_contracts=_chain_puts(), hv30=0.40, iv_rank=60.0,
            )

    def test_raises_with_too_few_strikes(self):
        with pytest.raises(TradeIdeaError):
            generate_trade_idea(
                symbol="TST", spot=100.0, expiry="2026-07-10", days_to_expiry=14,
                put_contracts=[_put(97.5, 2.5, 2.6)], hv30=0.40, iv_rank=60.0,
            )
