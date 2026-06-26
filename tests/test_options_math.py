"""Tests for backend.options_math.

Sanity checks against known Black-Scholes values and Greek relationships.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from options_math import (  # noqa: E402
    Leg,
    bs_price,
    breakeven_points,
    greeks,
    implied_vol,
    iv_percentile,
    iv_rank,
    strategy_pnl_at_expiry,
)


# Standard test case: ATM 1Y option, no dividends, 5% rate, 20% vol
S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.05, 0.20


def test_atm_call_price():
    # Known BS value ≈ 10.4506
    price = bs_price(S, K, T, r, sigma, opt="call")
    assert math.isclose(float(price), 10.4506, abs_tol=1e-3)


def test_atm_put_price():
    # Known BS value ≈ 5.5735
    price = bs_price(S, K, T, r, sigma, opt="put")
    assert math.isclose(float(price), 5.5735, abs_tol=1e-3)


def test_put_call_parity():
    """C - P = S - K * exp(-r*T) for European options."""
    c = float(bs_price(S, K, T, r, sigma, opt="call"))
    p = float(bs_price(S, K, T, r, sigma, opt="put"))
    parity = S - K * math.exp(-r * T)
    assert math.isclose(c - p, parity, abs_tol=1e-6)


def test_atm_call_delta_around_06():
    g = greeks(S, K, T, r, sigma, opt="call")
    # ATM call delta ≈ 0.6368 for these params
    assert 0.60 < g.delta < 0.70


def test_atm_put_delta_negative_and_under_half():
    """With positive interest rates, ATM put delta is between -0.5 and 0."""
    g = greeks(S, K, T, r, sigma, opt="put")
    assert -0.5 < g.delta < 0
    # Put delta = call delta - 1 (BS identity, no dividends)
    gc = greeks(S, K, T, r, sigma, opt="call")
    assert math.isclose(g.delta, gc.delta - 1, abs_tol=1e-10)


def test_gamma_same_for_call_and_put():
    """Call and put gamma are identical at same strike/expiry."""
    gc = greeks(S, K, T, r, sigma, opt="call")
    gp = greeks(S, K, T, r, sigma, opt="put")
    assert math.isclose(gc.gamma, gp.gamma, abs_tol=1e-10)


def test_vega_positive_and_same_for_call_put():
    gc = greeks(S, K, T, r, sigma, opt="call")
    gp = greeks(S, K, T, r, sigma, opt="put")
    assert gc.vega > 0
    assert math.isclose(gc.vega, gp.vega, abs_tol=1e-10)


def test_theta_negative_for_long():
    """Long options decay over time."""
    gc = greeks(S, K, T, r, sigma, opt="call")
    gp = greeks(S, K, T, r, sigma, opt="put")
    assert gc.theta < 0
    assert gp.theta < 0


def test_implied_vol_recovers_input():
    market = float(bs_price(S, K, T, r, sigma, opt="call"))
    iv = implied_vol(market, S, K, T, r, opt="call")
    assert math.isclose(iv, sigma, abs_tol=1e-4)


def test_iv_rank_and_percentile():
    series = np.array([0.20, 0.25, 0.30, 0.35, 0.40])
    assert math.isclose(iv_rank(0.30, series), 50.0, abs_tol=1e-9)
    assert math.isclose(iv_rank(0.40, series), 100.0, abs_tol=1e-9)
    assert math.isclose(iv_rank(0.20, series), 0.0, abs_tol=1e-9)
    assert math.isclose(iv_percentile(0.31, series), 60.0, abs_tol=1e-9)


def test_bull_call_spread_pnl():
    """Long 95C, short 105C: max profit = $10 spread - debit."""
    legs = [
        Leg(qty=1, opt="call", strike=95, expiry_T=0.25, iv=0.30),
        Leg(qty=-1, opt="call", strike=105, expiry_T=0.25, iv=0.30),
    ]
    debit_per_contract = 4.0  # paid $4 per share = $400 total
    S_range = np.linspace(80, 120, 100)
    pnl = strategy_pnl_at_expiry(legs, S_range, net_debit=debit_per_contract * 100)
    # Max profit at expiry above 105: ($10 spread - $4 debit) * 100 = $600
    assert math.isclose(pnl.max(), 600.0, abs_tol=1.0)
    # Max loss at expiry below 95: -$400
    assert math.isclose(pnl.min(), -400.0, abs_tol=1.0)


def test_breakeven_finds_one_point_for_long_call():
    """A naked long call has a single breakeven at strike + premium."""
    legs = [Leg(qty=1, opt="call", strike=100, expiry_T=0.25, iv=0.30)]
    premium = 5.0
    S_range = np.linspace(80, 120, 200)
    be = breakeven_points(legs, premium * 100, S_range)
    assert len(be) == 1
    assert math.isclose(be[0], 105.0, abs_tol=0.5)
