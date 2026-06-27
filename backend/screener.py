"""
Fundamentals + technicals screener.

Scores a universe of symbols with the *same* combined assessment the trade-idea
engine uses, ranks them, and returns the leaders. The orchestrator then asks for
full option strategies (OTM credit spreads) on the top names via
``/api/trade-idea/{symbol}``.

Per-symbol work (one fundamentals HTTP call + one IBKR history pull) is run
concurrently with ``asyncio.gather`` so a 10-name screen stays responsive.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from models import ScreenCandidate, ScreenResult
from strategy_engine import assess_symbol
from technicals import compute_technicals, realized_vol_rank

logger = logging.getLogger(__name__)

# Default universe: liquid, optionable large caps. Override via the endpoint.
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "AVGO", "AMD", "TSLA", "NFLX",
]

# A single ib_insync connection is not safe for concurrent requests — responses
# interleave and stall (and corrupt the decoder). Serialise IBKR access; the
# per-symbol work is only ~2-3s so a 10-name screen is still well under a minute.
_MAX_CONCURRENCY = 1
# Brief gap between historical requests to stay clear of IB's pacing limit
# (~60 historical requests / 10 min). Cheap insurance against a throttle.
_PACING_DELAY = 0.4


async def _score_one(ibkr, stockanalysis, symbol: str) -> ScreenCandidate | None:
    """Fetch data for one symbol and produce a ranked candidate (or None on error)."""
    try:
        history = await asyncio.wait_for(
            ibkr.get_price_history(symbol, timeframe="1d", lookback_days=365), timeout=30
        )
    except (Exception, asyncio.TimeoutError) as exc:
        logger.warning("screen skip symbol=%s history error=%r", symbol, exc)
        return None

    technicals = compute_technicals(history)
    _hv, hv_rank = realized_vol_rank(history)

    fundamentals = None
    if stockanalysis:
        try:
            fundamentals = await stockanalysis.get_fundamentals(symbol)
        except Exception as exc:
            logger.warning("screen fundamentals miss symbol=%s err=%s", symbol, exc)

    bias, signals, score = assess_symbol(technicals.last_price, fundamentals, technicals)
    return ScreenCandidate(
        symbol=symbol,
        score=score,
        bias=bias,
        last_price=technicals.last_price,
        trend=technicals.trend,
        momentum=technicals.momentum,
        rsi14=technicals.rsi14,
        pe_ratio=fundamentals.pe_ratio if fundamentals else None,
        forward_pe=fundamentals.forward_pe if fundamentals else None,
        peg_ratio=fundamentals.peg_ratio if fundamentals else None,
        net_margin=fundamentals.net_margin if fundamentals else None,
        roe=fundamentals.roe if fundamentals else None,
        hv_rank=round(hv_rank, 1),
        signals=signals,
    )


async def screen_universe(ibkr, stockanalysis, symbols: list[str]) -> ScreenResult:
    """Score and rank a universe by conviction (|score|, strongest signals first)."""
    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _bounded(sym: str):
        async with sem:
            candidate = await _score_one(ibkr, stockanalysis, sym.upper())
            await asyncio.sleep(_PACING_DELAY)
            return candidate

    results = await asyncio.gather(*(_bounded(s) for s in symbols))
    candidates = [c for c in results if c is not None]
    # Rank by absolute conviction: a strong bearish read is as tradeable as a
    # strong bullish one (bear call vs bull put). Tie-break on richer premium.
    candidates.sort(key=lambda c: (abs(c.score), c.hv_rank or 0), reverse=True)
    logger.info("screen universe=%d ranked=%d top=%s",
                len(symbols), len(candidates),
                candidates[0].symbol if candidates else "-")
    return ScreenResult(
        generated_at=datetime.utcnow(),
        universe=[s.upper() for s in symbols],
        candidates=candidates,
    )
