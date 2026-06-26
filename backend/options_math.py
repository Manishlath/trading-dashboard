"""
Options pricing and Greeks.

Black-Scholes-Merton model with continuous dividend yield. All functions accept
scalar or numpy array inputs and broadcast naturally.

Conventions
-----------
S    : spot price
K    : strike
T    : time to expiry, in years (use trading days / 252 or calendar days / 365)
r    : risk-free rate, annualized continuous (e.g. 0.045 for 4.5%)
q    : continuous dividend yield, annualized (default 0)
sigma: volatility, annualized (e.g. 0.30 for 30%)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

OptionType = Literal["call", "put"]


# ---------------------------------------------------------------------------
# Core Black-Scholes-Merton
# ---------------------------------------------------------------------------

def _d1_d2(S, K, T, r, sigma, q=0.0):
    """Standard Black-Scholes d1, d2 helpers."""
    S, K, T, r, sigma, q = map(np.asarray, (S, K, T, r, sigma, q))
    # Guard against T=0 and sigma=0 producing nan
    T_safe = np.where(T <= 0, 1e-12, T)
    sig_safe = np.where(sigma <= 0, 1e-12, sigma)
    d1 = (np.log(S / K) + (r - q + 0.5 * sig_safe ** 2) * T_safe) / (sig_safe * np.sqrt(T_safe))
    d2 = d1 - sig_safe * np.sqrt(T_safe)
    return d1, d2


def bs_price(S, K, T, r, sigma, q=0.0, opt: OptionType = "call"):
    """Black-Scholes-Merton fair value."""
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    if opt == "call":
        price = S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    elif opt == "put":
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)
    else:
        raise ValueError(f"opt must be 'call' or 'put', got {opt!r}")
    # Intrinsic floor when T<=0
    if np.any(np.asarray(T) <= 0):
        intrinsic = np.maximum(S - K, 0) if opt == "call" else np.maximum(K - S, 0)
        price = np.where(np.asarray(T) <= 0, intrinsic, price)
    return price


# ---------------------------------------------------------------------------
# Greeks
# ---------------------------------------------------------------------------

@dataclass
class Greeks:
    """All five Greeks plus the price.

    delta : ∂P/∂S            (per $1 move in spot)
    gamma : ∂²P/∂S²          (∂delta per $1 move)
    theta : ∂P/∂t            (per CALENDAR DAY — divided by 365)
    vega  : ∂P/∂sigma        (per 1 percentage-point change in IV, i.e. /100)
    rho   : ∂P/∂r            (per 1 percentage-point change in rates, i.e. /100)
    """
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


def greeks(S, K, T, r, sigma, q=0.0, opt: OptionType = "call") -> Greeks:
    """All Greeks at once. Returns per-share values; multiply by 100 for per-contract."""
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    sqrtT = np.sqrt(T)
    pdf_d1 = norm.pdf(d1)

    price = bs_price(S, K, T, r, sigma, q, opt)

    if opt == "call":
        delta = np.exp(-q * T) * norm.cdf(d1)
        theta = (
            -(S * np.exp(-q * T) * pdf_d1 * sigma) / (2 * sqrtT)
            - r * K * np.exp(-r * T) * norm.cdf(d2)
            + q * S * np.exp(-q * T) * norm.cdf(d1)
        )
        rho = K * T * np.exp(-r * T) * norm.cdf(d2)
    else:
        delta = -np.exp(-q * T) * norm.cdf(-d1)
        theta = (
            -(S * np.exp(-q * T) * pdf_d1 * sigma) / (2 * sqrtT)
            + r * K * np.exp(-r * T) * norm.cdf(-d2)
            - q * S * np.exp(-q * T) * norm.cdf(-d1)
        )
        rho = -K * T * np.exp(-r * T) * norm.cdf(-d2)

    gamma = (np.exp(-q * T) * pdf_d1) / (S * sigma * sqrtT)
    vega = S * np.exp(-q * T) * pdf_d1 * sqrtT

    return Greeks(
        price=float(price),
        delta=float(delta),
        gamma=float(gamma),
        theta=float(theta / 365.0),      # per calendar day
        vega=float(vega / 100.0),         # per vol point
        rho=float(rho / 100.0),           # per rate point
    )


# ---------------------------------------------------------------------------
# Implied volatility solver
# ---------------------------------------------------------------------------

def implied_vol(
    market_price: float,
    S: float, K: float, T: float, r: float,
    q: float = 0.0, opt: OptionType = "call",
    tol: float = 1e-6, max_iter: int = 100,
) -> float:
    """Solve for sigma such that BS price == market_price.

    Uses Brent's method on a wide bracket. Returns NaN if no solution exists
    (e.g. market price below intrinsic or above max).
    """
    intrinsic = max(S - K, 0) if opt == "call" else max(K - S, 0)
    if market_price < intrinsic - 1e-6:
        return float("nan")

    def f(sig: float) -> float:
        return float(bs_price(S, K, T, r, sig, q, opt)) - market_price

    try:
        return float(brentq(f, 1e-6, 5.0, xtol=tol, maxiter=max_iter))
    except (ValueError, RuntimeError):
        return float("nan")


# ---------------------------------------------------------------------------
# IV rank and percentile
# ---------------------------------------------------------------------------

def iv_rank(current_iv: float, iv_series: np.ndarray) -> float:
    """IV rank: where current IV sits between 1Y min and 1Y max, in [0, 100]."""
    arr = np.asarray(iv_series)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return float("nan")
    lo, hi = arr.min(), arr.max()
    if hi <= lo:
        return 50.0
    return float(100 * (current_iv - lo) / (hi - lo))


def iv_percentile(current_iv: float, iv_series: np.ndarray) -> float:
    """IV percentile: % of historical observations below current IV, in [0, 100]."""
    arr = np.asarray(iv_series)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return float("nan")
    return float(100 * np.sum(arr < current_iv) / arr.size)


# ---------------------------------------------------------------------------
# Strategy P&L
# ---------------------------------------------------------------------------

@dataclass
class Leg:
    """One leg of an options structure."""
    qty: int                 # positive=long, negative=short
    opt: OptionType
    strike: float
    expiry_T: float          # years to expiry
    iv: float                # used for time-value pricing before expiry


def strategy_pnl_at_expiry(legs: list[Leg], S_range: np.ndarray, net_debit: float) -> np.ndarray:
    """P&L at expiry across a range of underlying prices.

    net_debit is what was paid (positive) or received (negative) to open.
    """
    pnl = np.full_like(S_range, -net_debit, dtype=float)
    for leg in legs:
        if leg.opt == "call":
            intrinsic = np.maximum(S_range - leg.strike, 0)
        else:
            intrinsic = np.maximum(leg.strike - S_range, 0)
        pnl += leg.qty * intrinsic * 100  # 100 multiplier per contract
    return pnl


def breakeven_points(legs: list[Leg], net_debit: float, S_range: np.ndarray) -> list[float]:
    """Find prices where P&L at expiry crosses zero. Useful for spread analysis."""
    pnl = strategy_pnl_at_expiry(legs, S_range, net_debit)
    sign_changes = np.where(np.diff(np.sign(pnl)) != 0)[0]
    breakevens = []
    for i in sign_changes:
        # Linear interpolation between S_range[i] and S_range[i+1]
        x1, x2 = S_range[i], S_range[i + 1]
        y1, y2 = pnl[i], pnl[i + 1]
        if y2 - y1 != 0:
            be = x1 - y1 * (x2 - x1) / (y2 - y1)
            breakevens.append(float(be))
    return breakevens
