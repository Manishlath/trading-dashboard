"""
Final trade-idea generation.

Combines the options-engine output (live chain + IV rank from IBKR) with the
local Black-Scholes/Greeks math, the technicals module (chart context) and the
StockAnalysis fundamentals (valuation context) to produce one concrete,
defined-risk, profit-seeking option structure for a symbol.

Strategy selection is directional, driven by a combined valuation + technical
score:
  * bullish / neutral  -> **bull put credit spread**  (sell ~30Δ put, buy a wing below)
  * bearish            -> **bear call credit spread** (sell ~30Δ call, buy a wing above)

Both collect premium (helped by elevated IV rank) with defined risk. No order
placement happens here — this module only *describes* a trade. Order entry stays
behind an explicit UI confirm gate per the project safety rules.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import numpy as np

from config import (
    DEFAULT_SPREADS,
    MAX_SPREAD_PCT,
    MIN_OPEN_INTEREST,
    MIN_VOLUME,
    RISK_FREE_RATE,
    TARGET_SHORT_DELTA,
)
from models import Fundamentals, OptionContract, Technicals, TradeIdea, TradeLeg
from options_math import Leg, breakeven_points, greeks, strategy_pnl_at_expiry

logger = logging.getLogger(__name__)


class TradeIdeaError(ValueError):
    """Raised when a symbol has insufficient data to build a trade."""


# ---------------------------------------------------------------------------
# Signal assessment — valuation + chart context
# ---------------------------------------------------------------------------

def _assess(
    spot: float,
    fundamentals: Optional[Fundamentals],
    technicals: Optional[Technicals],
) -> tuple[str, list[str], float]:
    """Combine fundamentals + technicals into a directional bias and rationale.

    Returns ``(bias, signals, score)`` where bias is "bullish" | "bearish" |
    "neutral" and score is the signed composite (positive = bullish).
    """
    score = 0.0
    signals: list[str] = []

    t = technicals
    if t:
        if t.trend == "uptrend":
            score += 1
            signals.append(f"Uptrend — price ${spot:,.2f} above 50-day SMA ${t.sma50:,.2f}"
                           if t.sma50 else "Uptrend — price above 50-day SMA")
        elif t.trend == "downtrend":
            score -= 1
            signals.append(f"Downtrend — price ${spot:,.2f} below 50-day SMA ${t.sma50:,.2f}"
                           if t.sma50 else "Downtrend — price below 50-day SMA")
        if t.momentum == "overbought":
            score -= 1
            signals.append(f"Overbought — RSI {t.rsi14:.0f}" if t.rsi14 else "Overbought (RSI ≥ 70)")
        elif t.momentum == "oversold":
            score += 1
            signals.append(f"Oversold — RSI {t.rsi14:.0f}" if t.rsi14 else "Oversold (RSI ≤ 30)")
        if t.macd_hist is not None:
            if t.macd_hist > 0:
                score += 0.5
                signals.append("MACD above signal (bullish momentum)")
            elif t.macd_hist < 0:
                score -= 0.5
                signals.append("MACD below signal (bearish momentum)")

    f = fundamentals
    if f:
        if f.peg_ratio is not None and 0 < f.peg_ratio <= 1.5:
            score += 1
            signals.append(f"Attractive valuation — PEG {f.peg_ratio:.2f}")
        elif f.peg_ratio is not None and f.peg_ratio >= 3:
            score -= 1
            signals.append(f"Stretched valuation — PEG {f.peg_ratio:.2f}")
        if f.forward_pe is not None and f.pe_ratio is not None and f.forward_pe < f.pe_ratio:
            score += 0.5
            signals.append(f"Earnings growth priced in — forward PE {f.forward_pe:.1f} < trailing {f.pe_ratio:.1f}")
        if f.net_margin is not None and f.net_margin >= 0.20:
            score += 0.5
            signals.append(f"High profitability — net margin {f.net_margin * 100:.0f}%")
        if f.roe is not None and f.roe >= 0.15:
            score += 0.5
            signals.append(f"Strong returns — ROE {f.roe * 100:.0f}%")
        if f.debt_to_equity is not None and f.debt_to_equity > 2:
            score -= 0.5
            signals.append(f"Leveraged balance sheet — D/E {f.debt_to_equity:.1f}")

    if score >= 1:
        bias = "bullish"
    elif score <= -1:
        bias = "bearish"
    else:
        bias = "neutral"
    if not signals:
        signals.append("No strong valuation or technical signal — premium-collection trade.")
    return bias, signals, round(score, 2)


def assess_symbol(
    spot: float,
    fundamentals: Optional[Fundamentals],
    technicals: Optional[Technicals],
) -> tuple[str, list[str], float]:
    """Public wrapper around the combined fundamental + technical assessment.

    Used by the screener to rank a universe with the *same* scoring the
    trade-idea engine uses, so the screen and the resulting trade agree.
    """
    return _assess(spot, fundamentals, technicals)


# ---------------------------------------------------------------------------
# Credit-spread construction
# ---------------------------------------------------------------------------

def _has_live_quote(c: OptionContract) -> bool:
    return c.bid is not None and c.ask is not None and c.bid > 0 and c.ask > 0


def _live_mid(c: OptionContract) -> float:
    return round((c.bid + c.ask) / 2, 2)  # type: ignore[operator]


def _spread_pct(c: OptionContract) -> Optional[float]:
    """Relative bid-ask spread (ask-bid)/mid, or None without a live two-sided quote."""
    if not _has_live_quote(c):
        return None
    mid = (c.bid + c.ask) / 2  # type: ignore[operator]
    return round((c.ask - c.bid) / mid, 4) if mid > 0 else None  # type: ignore[operator]


def _is_liquid(c: OptionContract) -> bool:
    """True when a strike is tradeable without excessive bid/offer leakage.

    Requires a live two-sided market and a tight spread; rejects on thin open
    interest only when OI is actually reported (paper feeds often omit it).
    """
    sp = _spread_pct(c)
    if sp is None or sp > MAX_SPREAD_PCT:
        return False
    if c.open_interest is not None and c.open_interest < MIN_OPEN_INTEREST:
        return False
    return True


def _leg_liquidity_warnings(c: OptionContract, label: str) -> list[str]:
    """Human-readable liquidity flags for one chosen leg."""
    warnings: list[str] = []
    sp = _spread_pct(c)
    if sp is None:
        warnings.append(f"{label} ${c.strike:g} has no live two-sided market — liquidity unknown")
    elif sp > MAX_SPREAD_PCT:
        warnings.append(f"{label} ${c.strike:g} spread is wide ({sp * 100:.0f}% of mid)")
    if c.open_interest is not None and c.open_interest < MIN_OPEN_INTEREST:
        warnings.append(f"{label} ${c.strike:g} open interest is thin ({c.open_interest})")
    if c.volume is not None and c.volume < MIN_VOLUME:
        warnings.append(f"{label} ${c.strike:g} traded light today (vol {c.volume})")
    return warnings


def _build_credit_spread(
    *,
    side: str,                 # "put" (bull put) or "call" (bear call)
    symbol: str,
    spot: float,
    T: float,
    sigma: float,
    contracts_list: list[OptionContract],
    contracts: int,
):
    """Select short ~30Δ option + protective wing, price the spread, return metrics.

    For ``put`` the wing is one strike *below* the short (bull put); for ``call``
    one strike *above* (bear call).
    """
    bullish = side == "put"
    # OTM candidates: puts below spot / calls above spot, nearest-money first.
    if bullish:
        otm = sorted((c for c in contracts_list if c.strike < spot), key=lambda c: spot - c.strike)
    else:
        otm = sorted((c for c in contracts_list if c.strike > spot), key=lambda c: c.strike - spot)
    if len(otm) < 2:
        raise TradeIdeaError(f"not enough OTM {side} strikes for {symbol}")

    def model_delta(strike: float) -> float:
        return greeks(spot, strike, T, RISK_FREE_RATE, sigma, opt=side).delta

    # Prefer liquid strikes near the target delta; only fall back to the full set
    # (flagged later) when nothing tradeable is available.
    liquid = [c for c in otm if _is_liquid(c)]
    short_pool = liquid if liquid else otm
    short = min(short_pool, key=lambda c: abs(abs(model_delta(c.strike)) - TARGET_SHORT_DELTA))

    if bullish:
        wing = [c for c in otm if c.strike < short.strike]
    else:
        wing = [c for c in otm if c.strike > short.strike]
    if not wing:
        raise TradeIdeaError(f"no protective {side} wing beyond short for {symbol}")
    # Closest wing to the short, preferring a liquid one to cap leakage on both legs.
    liquid_wing = [c for c in wing if _is_liquid(c)]
    wing_pool = liquid_wing if liquid_wing else wing
    long_opt = (
        max(wing_pool, key=lambda c: c.strike) if bullish
        else min(wing_pool, key=lambda c: c.strike)
    )

    short_delta = model_delta(short.strike)
    long_delta = model_delta(long_opt.strike)

    # Price both legs from the SAME source to avoid an inverted credit.
    if _has_live_quote(short) and _has_live_quote(long_opt):
        short_mid, long_mid, pricing = _live_mid(short), _live_mid(long_opt), "live mid"
    else:
        short_mid = round(greeks(spot, short.strike, T, RISK_FREE_RATE, sigma, opt=side).price, 2)
        long_mid = round(greeks(spot, long_opt.strike, T, RISK_FREE_RATE, sigma, opt=side).price, 2)
        pricing = "model (HV30)"

    width = abs(short.strike - long_opt.strike)
    credit = round(short_mid - long_mid, 2)
    if credit <= 0:
        raise TradeIdeaError(f"{side} spread priced at a debit for {symbol}; no edge")

    # Liquidity assessment — what you'd lose crossing the spreads, plus warnings.
    liquidity_warnings = (
        _leg_liquidity_warnings(short, "Short") + _leg_liquidity_warnings(long_opt, "Long")
    )
    liquidity_ok = _is_liquid(short) and _is_liquid(long_opt)
    # Entry slippage = half-spread per leg crossed from mid (dollars, ×100 ×contracts).
    half_spreads = sum(
        (c.ask - c.bid) / 2 for c in (short, long_opt) if _has_live_quote(c)
    )
    est_slippage = round(half_spreads * 100 * contracts, 2)

    return {
        "side": side, "short": short, "long": long_opt,
        "short_delta": short_delta, "long_delta": long_delta,
        "short_mid": short_mid, "long_mid": long_mid,
        "short_spread_pct": _spread_pct(short), "long_spread_pct": _spread_pct(long_opt),
        "width": width, "credit": credit, "pricing": pricing,
        "liquidity_ok": liquidity_ok, "liquidity_warnings": liquidity_warnings,
        "est_slippage": est_slippage,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_trade_idea(
    *,
    symbol: str,
    spot: float,
    expiry: str,
    days_to_expiry: int,
    put_contracts: list[OptionContract],
    call_contracts: Optional[list[OptionContract]] = None,
    hv30: float,
    iv_rank: float,
    fundamentals: Optional[Fundamentals] = None,
    technicals: Optional[Technicals] = None,
    contracts: int = DEFAULT_SPREADS,
) -> TradeIdea:
    """Build a directional, defined-risk credit spread for ``symbol``.

    Pure over its inputs (chain slices + signals are pre-fetched by the caller),
    so it's testable without a live connection.
    """
    if spot <= 0:
        raise TradeIdeaError(f"no spot price for {symbol}")

    T = max(days_to_expiry / 365.0, 1e-4)
    sigma = hv30 if hv30 and hv30 > 0 else 0.30

    bias, signals, _score = _assess(spot, fundamentals, technicals)

    # Bearish → bear call spread (needs call strikes). Otherwise bull put spread.
    if bias == "bearish" and call_contracts and len([c for c in call_contracts if c.strike > spot]) >= 2:
        spread = _build_credit_spread(
            side="call", symbol=symbol, spot=spot, T=T, sigma=sigma,
            contracts_list=call_contracts, contracts=contracts,
        )
        strategy_name, direction = "Bear call credit spread", "neutral-bearish"
    else:
        spread = _build_credit_spread(
            side="put", symbol=symbol, spot=spot, T=T, sigma=sigma,
            contracts_list=put_contracts, contracts=contracts,
        )
        strategy_name, direction = "Bull put credit spread", "neutral-bullish"

    side = spread["side"]
    short, long_opt = spread["short"], spread["long"]
    credit, width = spread["credit"], spread["width"]
    short_delta = spread["short_delta"]

    net_credit = round(credit * 100, 2)
    max_loss = round((width - credit) * 100, 2)
    max_profit = net_credit
    prob_of_profit = round((1 - abs(short_delta)) * 100, 1)
    return_on_risk = round(max_profit / max_loss, 3) if max_loss > 0 else 0.0
    breakeven = round(
        short.strike - credit if side == "put" else short.strike + credit, 2
    )

    legs = [
        Leg(qty=-contracts, opt=side, strike=short.strike, expiry_T=T, iv=sigma),
        Leg(qty=contracts, opt=side, strike=long_opt.strike, expiry_T=T, iv=sigma),
    ]
    total_net_debit = -net_credit * contracts        # received credit → negative debit
    s_range = np.linspace(spot * 0.75, spot * 1.25, 120)
    pnl = strategy_pnl_at_expiry(legs, s_range, net_debit=total_net_debit)
    breakevens = breakeven_points(legs, net_debit=total_net_debit, S_range=s_range)
    pnl_curve = [(round(float(s), 2), round(float(p), 2)) for s, p in zip(s_range, pnl)]

    iv_note = (
        "Elevated IV rank means premium is rich — favourable for selling."
        if iv_rank >= 50 else "IV rank is moderate; premium is fair rather than rich."
    )
    if side == "put":
        hold_clause = f"profiting if {symbol} holds above ${breakeven:,.2f} at expiry"
        dist_pct = (1 - short.strike / spot) * 100
        loc = f"~{dist_pct:.0f}% below spot"
    else:
        hold_clause = f"profiting if {symbol} stays below ${breakeven:,.2f} at expiry"
        dist_pct = (short.strike / spot - 1) * 100
        loc = f"~{dist_pct:.0f}% above spot"

    # Liquidity note: quantify bid/offer leakage against the premium collected.
    est_slippage = spread["est_slippage"]
    if spread["liquidity_ok"]:
        liq_note = (
            f"Liquidity is good (spreads tight); ~${est_slippage:,.0f} to cross on entry, "
            f"~{(est_slippage / net_credit * 100):.0f}% of the credit."
            if net_credit else "Liquidity is good (spreads tight)."
        )
    else:
        liq_note = (
            f"Caution: liquidity is marginal — crossing the spreads costs ~${est_slippage:,.0f} "
            f"(~{(est_slippage / net_credit * 100):.0f}% of the credit), so use a limit order near mid."
            if net_credit and est_slippage else
            "Caution: liquidity is marginal — work a limit order near mid to avoid leakage."
        )

    thesis = (
        f"Signals read {bias}. {strategy_name}: sell the ${short.strike:g} {side} and buy the "
        f"${long_opt.strike:g} {side} expiring {expiry} ({days_to_expiry}d). The short strike sits "
        f"{loc} at ~{abs(short_delta):.2f} delta, a ~{prob_of_profit:.0f}% probability of profit. "
        f"{iv_note} You collect ${net_credit:,.0f} per spread and risk ${max_loss:,.0f}, {hold_clause}. "
        f"{liq_note} Pricing basis: {spread['pricing']}."
    )

    idea = TradeIdea(
        symbol=symbol,
        generated_at=datetime.utcnow(),
        strategy=strategy_name,
        direction=direction,
        thesis=thesis,
        underlying_price=round(spot, 2),
        expiry=expiry,
        days_to_expiry=days_to_expiry,
        legs=[
            TradeLeg(action="sell", opt_type=side, strike=short.strike, expiry=expiry,
                     quantity=contracts, mid_price=spread["short_mid"], delta=round(short_delta, 3),
                     bid=short.bid, ask=short.ask, spread_pct=spread["short_spread_pct"],
                     open_interest=short.open_interest, volume=short.volume),
            TradeLeg(action="buy", opt_type=side, strike=long_opt.strike, expiry=expiry,
                     quantity=contracts, mid_price=spread["long_mid"], delta=round(spread["long_delta"], 3),
                     bid=long_opt.bid, ask=long_opt.ask, spread_pct=spread["long_spread_pct"],
                     open_interest=long_opt.open_interest, volume=long_opt.volume),
        ],
        contracts=contracts,
        net_credit=net_credit,
        max_profit=max_profit,
        max_loss=max_loss,
        breakevens=breakevens or [breakeven],
        prob_of_profit=prob_of_profit,
        return_on_risk=return_on_risk,
        iv_rank=round(iv_rank, 1),
        hv30=round(sigma, 4),
        pnl_curve=pnl_curve,
        signals=signals,
        liquidity_ok=spread["liquidity_ok"],
        liquidity_warnings=spread["liquidity_warnings"],
        est_slippage=est_slippage,
    )
    logger.info(
        "trade_idea symbol=%s bias=%s strat=%s short=%.1f long=%.1f credit=%.0f maxL=%.0f pop=%.0f "
        "liquidity_ok=%s slippage=%.0f",
        symbol, bias, strategy_name, short.strike, long_opt.strike, net_credit,
        max_loss, prob_of_profit, spread["liquidity_ok"], est_slippage,
    )
    return idea
