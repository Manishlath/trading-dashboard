"""
FastAPI backend for trading dashboard.

Run locally:
    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ibkr_client import IBKRClient
from models import (
    AccountSummary,
    Fundamentals,
    OptionChain,
    Position,
    PriceHistory,
    StrategyRequest,
    StrategyResult,
)
from options_math import Leg, breakeven_points, greeks, strategy_pnl_at_expiry
from stock_analysis_scraper import StockAnalysisClient

load_dotenv()

ibkr: IBKRClient | None = None
stockanalysis: StockAnalysisClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise clients on startup, tear down on shutdown."""
    global ibkr, stockanalysis
    ibkr = IBKRClient(
        host=os.getenv("IBKR_HOST", "127.0.0.1"),
        port=int(os.getenv("IBKR_PORT", "4002")),
        client_id=int(os.getenv("IBKR_CLIENT_ID", "1")),
    )
    stockanalysis = StockAnalysisClient(
        email=os.getenv("STOCKANALYSIS_EMAIL"),
        password=os.getenv("STOCKANALYSIS_PASSWORD"),
        session_cookie=os.getenv("STOCKANALYSIS_SESSION_COOKIE"),
    )
    # Don't auto-connect; let endpoints connect lazily
    yield
    if ibkr:
        await ibkr.disconnect()


app = FastAPI(title="Trading Dashboard API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

@app.get("/api/portfolio", response_model=list[Position])
async def get_portfolio() -> list[Position]:
    if not ibkr:
        raise HTTPException(503, "IBKR client not initialised")
    return await ibkr.get_positions()


@app.get("/api/account", response_model=AccountSummary)
async def get_account() -> AccountSummary:
    if not ibkr:
        raise HTTPException(503, "IBKR client not initialised")
    return await ibkr.get_account_summary()


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

@app.get("/api/quote/{symbol}")
async def get_quote(symbol: str) -> dict:
    if not ibkr:
        raise HTTPException(503, "IBKR client not initialised")
    return await ibkr.get_quote(symbol)


@app.get("/api/history/{symbol}", response_model=PriceHistory)
async def get_history(symbol: str, timeframe: str = "1d", lookback_days: int = 365) -> PriceHistory:
    if not ibkr:
        raise HTTPException(503, "IBKR client not initialised")
    return await ibkr.get_price_history(symbol, timeframe, lookback_days)


@app.get("/api/chain/{symbol}", response_model=OptionChain)
async def get_chain(symbol: str, expiry: str | None = None) -> OptionChain:
    if not ibkr:
        raise HTTPException(503, "IBKR client not initialised")
    return await ibkr.get_option_chain(symbol, expiry)


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

@app.get("/api/fundamentals/{symbol}", response_model=Fundamentals)
async def get_fundamentals(symbol: str) -> Fundamentals:
    if not stockanalysis:
        raise HTTPException(503, "StockAnalysis client not initialised")
    return await stockanalysis.get_fundamentals(symbol)


# ---------------------------------------------------------------------------
# Strategy P&L
# ---------------------------------------------------------------------------

@app.post("/api/strategy/evaluate", response_model=StrategyResult)
async def evaluate_strategy(req: StrategyRequest) -> StrategyResult:
    """Compute P&L profile for a multi-leg strategy."""
    # Convert expiry string to T (years) — assume daily resolution
    today = datetime.utcnow().date()
    legs = []
    for sl in req.legs:
        expiry_date = datetime.strptime(sl.expiry, "%Y-%m-%d").date()
        T = max((expiry_date - today).days / 365.0, 1e-6)
        legs.append(Leg(qty=sl.qty, opt=sl.opt_type, strike=sl.strike, expiry_T=T, iv=0.30))

    # Get underlying price for centring the range
    if not ibkr:
        raise HTTPException(503, "IBKR client not initialised")
    quote = await ibkr.get_quote(req.underlying)
    spot = quote.get("last", 100.0)

    S_range = np.linspace(spot * 0.5, spot * 1.5, 200)
    pnl = strategy_pnl_at_expiry(legs, S_range, req.net_debit)
    breakevens = breakeven_points(legs, req.net_debit, S_range)

    return StrategyResult(
        max_profit=float(pnl.max()),
        max_loss=float(pnl.min()),
        breakevens=breakevens,
        pnl_curve=[(float(s), float(p)) for s, p in zip(S_range, pnl)],
    )


# ---------------------------------------------------------------------------
# Greeks helper
# ---------------------------------------------------------------------------

@app.get("/api/greeks")
async def compute_greeks(
    S: float, K: float, T: float, r: float, sigma: float,
    opt: str = "call", q: float = 0.0,
) -> dict:
    """On-demand Greeks calculation. T in years."""
    if opt not in ("call", "put"):
        raise HTTPException(400, "opt must be 'call' or 'put'")
    g = greeks(S, K, T, r, sigma, q, opt)  # type: ignore[arg-type]
    return {
        "price": g.price,
        "delta": g.delta,
        "gamma": g.gamma,
        "theta": g.theta,
        "vega": g.vega,
        "rho": g.rho,
    }
