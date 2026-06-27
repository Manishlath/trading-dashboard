"""
Tunable parameters for the strategy + liquidity engine.

Centralised here so thresholds can be adjusted without touching engine logic.
Every value can be overridden at runtime via an environment variable of the same
name (e.g. ``MAX_SPREAD_PCT=0.08``), which takes precedence over the default.
"""
from __future__ import annotations

import os


def _f(name: str, default: float) -> float:
    """Float config value, overridable via env."""
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    """Int config value, overridable via env."""
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# --- Strategy selection -----------------------------------------------------
RISK_FREE_RATE = _f("RISK_FREE_RATE", 0.045)        # for Greeks / POP
TARGET_SHORT_DELTA = _f("TARGET_SHORT_DELTA", 0.30)  # sell the ~Δ closest to this
DEFAULT_SPREADS = _i("DEFAULT_SPREADS", 1)           # contracts suggested

# --- Liquidity gates (guard against bid/offer leakage) ----------------------
# A strike is "liquid" with a live two-sided market, a tight relative spread,
# and adequate open interest.
MAX_SPREAD_PCT = _f("MAX_SPREAD_PCT", 0.10)          # (ask-bid)/mid ≤ 10%
MIN_OPEN_INTEREST = _i("MIN_OPEN_INTEREST", 100)     # resting OI per leg (when reported)
MIN_VOLUME = _i("MIN_VOLUME", 10)                    # day's volume per leg (soft)
