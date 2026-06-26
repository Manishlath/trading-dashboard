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
