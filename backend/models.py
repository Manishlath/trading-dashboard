"""API request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Position(BaseModel):
    """A single position in the portfolio."""
    contract_id: int
    symbol: str
    asset_class: Literal["STK", "OPT", "FOP", "BOND", "CASH", "FUT"]
    description: str
    quantity: float
    market_price: float
    market_value: float
    average_price: float
    unrealized_pnl: float
    daily_pnl: float
    currency: str = "USD"


class AccountSummary(BaseModel):
    """Account-level metrics."""
    net_liquidation: float
    equity_with_loan_value: float
    buying_power: float
    gross_position_value: float
    total_cash_value: float
    available_funds: float
    initial_margin: float
    maintenance_margin: float
    excess_liquidity: float
    leverage: float
    currency: str = "USD"


class OptionContract(BaseModel):
    """A single option contract in a chain."""
    symbol: str
    expiry: str                    # YYYY-MM-DD
    strike: float
    opt_type: Literal["call", "put"]
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None


class OptionChain(BaseModel):
    """Full chain for one expiry."""
    underlying: str
    underlying_price: float
    expiry: str
    days_to_expiry: int
    contracts: list[OptionContract]
    available_expiries: list[str] = []  # YYYY-MM-DD list for the dropdown


class IVRank(BaseModel):
    """IV rank and percentile for a symbol over the trailing year."""
    symbol: str
    current_hv30: float        # 30-day realised vol, annualised (fraction)
    hv_rank_52w: float         # where current HV sits in 52w min–max (0–100)
    hv_pct_52w: float          # fraction of 52w days below current HV (0–100)
    iv_current: Optional[float] = None   # current implied vol from IB if available
    iv_rank_52w: Optional[float] = None  # IV rank if IB provides historical IV


class Technicals(BaseModel):
    """Computed technical indicators for a symbol from OHLCV history."""
    symbol: str
    as_of: datetime
    last_price: float
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    rsi14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_mid: Optional[float] = None
    bb_lower: Optional[float] = None
    atr14: Optional[float] = None
    support: Optional[float] = None
    resistance: Optional[float] = None
    trend: str = "sideways"        # "uptrend" | "downtrend" | "sideways"
    momentum: str = "neutral"      # "overbought" | "oversold" | "neutral"


class ScreenCandidate(BaseModel):
    """One ranked symbol from the fundamentals + technicals screen."""
    symbol: str
    score: float                   # signed composite (positive = bullish)
    bias: str                      # "bullish" | "bearish" | "neutral"
    last_price: float
    trend: str
    momentum: str
    rsi14: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    net_margin: Optional[float] = None
    roe: Optional[float] = None
    hv_rank: Optional[float] = None
    signals: list[str] = []


class ScreenResult(BaseModel):
    """Ranked screen output across a universe."""
    generated_at: datetime
    universe: list[str]
    candidates: list[ScreenCandidate]   # ranked by |score| desc


class TradeLeg(BaseModel):
    """One leg of a generated trade idea."""
    action: Literal["buy", "sell"]
    opt_type: Literal["call", "put"]
    strike: float
    expiry: str                    # YYYY-MM-DD
    quantity: int
    mid_price: float               # per share
    delta: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread_pct: Optional[float] = None   # (ask-bid)/mid, None if no live market
    open_interest: Optional[int] = None
    volume: Optional[int] = None


class TradeIdea(BaseModel):
    """A concrete, profit-seeking option trade produced by the strategy engine."""
    symbol: str
    generated_at: datetime
    strategy: str                  # e.g. "Bull put credit spread"
    direction: str                 # "bullish" | "neutral-bullish" | ...
    thesis: str
    underlying_price: float
    expiry: str
    days_to_expiry: int
    legs: list[TradeLeg]
    contracts: int                 # number of spreads suggested
    net_credit: float              # dollars per spread (positive = credit received)
    max_profit: float              # dollars per spread
    max_loss: float                # dollars per spread (positive number)
    breakevens: list[float]
    prob_of_profit: float          # 0–100
    return_on_risk: float          # fraction (max_profit / max_loss)
    iv_rank: float                 # HV rank 0–100
    hv30: float                    # annualised 30-day realised vol (fraction)
    pnl_curve: list[tuple[float, float]]  # (underlying price, P&L per spread)
    signals: list[str] = []        # valuation + technical rationale bullets
    liquidity_ok: bool = True      # both legs pass the liquidity gate
    liquidity_warnings: list[str] = []   # bid/offer-leakage flags
    est_slippage: float = 0.0      # $ to cross the spreads on entry (per position)


class Fundamentals(BaseModel):
    """Snapshot of fundamental data, sourced from StockAnalysis.com."""
    symbol: str
    fetched_at: datetime
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    peg_ratio: Optional[float] = None
    price_to_sales: Optional[float] = None
    price_to_book: Optional[float] = None
    eps_ttm: Optional[float] = None
    eps_growth_yoy: Optional[float] = None
    revenue_growth_yoy: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    roe: Optional[float] = None
    debt_to_equity: Optional[float] = None
    dividend_yield: Optional[float] = None
    next_earnings_date: Optional[str] = None


class PriceBar(BaseModel):
    """OHLCV bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class PriceHistory(BaseModel):
    symbol: str
    timeframe: str = Field(description="e.g. '1d', '1h', '5m'")
    bars: list[PriceBar]


class StrategyLeg(BaseModel):
    """One leg of a strategy."""
    qty: int = Field(description="positive=long, negative=short")
    opt_type: Literal["call", "put"]
    strike: float
    expiry: str                    # YYYY-MM-DD


class StrategyRequest(BaseModel):
    """Request to evaluate a multi-leg strategy."""
    underlying: str
    legs: list[StrategyLeg]
    net_debit: float = Field(description="positive=paid, negative=received")


class StrategyResult(BaseModel):
    """P&L profile across underlying price range."""
    max_profit: Optional[float]
    max_loss: Optional[float]
    breakevens: list[float]
    pnl_curve: list[tuple[float, float]]  # (S, P&L) pairs
