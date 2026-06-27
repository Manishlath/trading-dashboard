"""
IBKR client wrapper using ib_insync.

Connects to TWS or IB Gateway (paper: port 4002, live: port 4001).
Keeps a single persistent connection across FastAPI requests via the lifespan.
Auto-reconnects on disconnect with exponential backoff (1 s → 30 s cap).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

from ib_insync import IB, Option, Stock, util

from models import AccountSummary, IVRank, OptionChain, OptionContract, Position, PriceBar, PriceHistory

# Level configurable via LOG_LEVEL env var (default INFO). Configured once at
# import so the IBKR request logs surface even when uvicorn owns the root logger.
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=_LOG_LEVEL)
logger = logging.getLogger(__name__)
logger.setLevel(_LOG_LEVEL)

# ib_insync event loop integration writes its own noisy logs; silence them.
util.logToConsole(logging.WARNING)

# Fraction of spot to fetch strikes around for a chain (v0.2: ±20% is enough
# and keeps us under IB's concurrent market-data line limit).
_STRIKE_RANGE = 0.20
# Max contracts per reqTickers batch — chunked and gathered to avoid pacing
# violations on wide chains.
_CHAIN_BATCH = 20

_ACCOUNT_TAGS = [
    "NetLiquidation",
    "EquityWithLoanValue",
    "BuyingPower",
    "GrossPositionValue",
    "TotalCashValue",
    "AvailableFunds",
    "InitialMarginReq",
    "MaintMarginReq",
    "ExcessLiquidity",
    "Leverage",
]

_BAR_SIZE: dict[str, str] = {
    "1m": "1 min",
    "5m": "5 mins",
    "15m": "15 mins",
    "30m": "30 mins",
    "1h": "1 hour",
    "1d": "1 day",
}


class IBKRClient:
    """Wraps Interactive Brokers TWS / IB Gateway for the trading dashboard.

    One instance is created at startup and shared across all FastAPI requests.
    Call ``connect()`` once during lifespan; it wires auto-reconnect so the
    handle stays valid across network blips.
    """

    def __init__(self, host: str, port: int, client_id: int) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib = IB()
        self._reconnect_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to TWS/Gateway with exponential backoff and wire reconnect."""
        await self._connect_with_backoff()
        self._ib.disconnectedEvent += self._on_disconnected
        logger.info("ibkr connected host=%s port=%s client_id=%s", self.host, self.port, self.client_id)

    async def disconnect(self) -> None:
        """Tear down cleanly (called from FastAPI lifespan on shutdown)."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._ib.isConnected():
            self._ib.disconnect()
            logger.info("ibkr disconnected")

    # ------------------------------------------------------------------
    # Internal: backoff & auto-reconnect
    # ------------------------------------------------------------------

    async def _connect_with_backoff(self, max_attempts: int = 8) -> None:
        delay = 1.0
        for attempt in range(1, max_attempts + 1):
            try:
                if not self._ib.isConnected():
                    await self._ib.connectAsync(
                        self.host, self.port, clientId=self.client_id, timeout=15
                    )
                return
            except Exception as exc:
                if attempt == max_attempts:
                    logger.error(
                        "ibkr connect failed permanently host=%s port=%s attempts=%d error=%s",
                        self.host, self.port, attempt, exc,
                    )
                    raise
                logger.warning(
                    "ibkr connect attempt=%d/%d host=%s port=%s delay=%.1fs error=%s",
                    attempt, max_attempts, self.host, self.port, delay, exc,
                )
                await asyncio.sleep(delay)
                # Exponential backoff: 1, 2, 4, 8, … capped at 30s.
                delay = min(delay * 2, 30.0)

    def _on_disconnected(self) -> None:
        logger.warning("ibkr disconnected unexpectedly — scheduling reconnect")
        loop = asyncio.get_event_loop()
        if loop.is_running():
            self._reconnect_task = loop.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        await asyncio.sleep(1)  # brief pause before first retry
        try:
            await self._connect_with_backoff()
            logger.info("ibkr reconnected host=%s port=%s", self.host, self.port)
        except Exception as exc:
            logger.error("ibkr reconnect gave up error=%s", exc)

    async def _ensure_connected(self) -> None:
        if not self._ib.isConnected():
            await self._connect_with_backoff()

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    async def get_positions(self) -> list[Position]:
        """Return all open positions with market values and unrealised P&L.

        Uses ``IB.portfolio()`` (PortfolioItem) rather than ``IB.positions()``
        (Position namedtuple) because only PortfolioItem carries marketPrice,
        marketValue, and unrealizedPNL.
        """
        await self._ensure_connected()
        items = self._ib.portfolio()
        result: list[Position] = []
        for item in items:
            c = item.contract
            asset_class = c.secType or "STK"
            # OPT localSymbol is the full OCC ticker; use it as the description.
            description = c.localSymbol or c.symbol
            result.append(
                Position(
                    contract_id=c.conId or 0,
                    symbol=c.symbol,
                    asset_class=asset_class,  # type: ignore[arg-type]
                    description=description,
                    quantity=float(item.position),
                    market_price=_float(item.marketPrice),
                    market_value=_float(item.marketValue),
                    average_price=_float(item.averageCost),
                    unrealized_pnl=_float(item.unrealizedPNL),
                    # dailyPNL requires a separate reqPnLSingle subscription;
                    # left as 0.0 here — the /api/account endpoint has account-level daily P&L.
                    daily_pnl=0.0,
                    currency=c.currency or "USD",
                )
            )
        logger.info("ibkr get_positions count=%d", len(result))
        return result

    async def get_account_summary(self) -> AccountSummary:
        """Return account-level financial metrics.

        ``accountValues()`` is populated automatically after connect for the
        primary account. We read the cached values synchronously.
        """
        await self._ensure_connected()
        raw: dict[str, float] = {}
        for av in self._ib.accountValues():
            if av.tag in _ACCOUNT_TAGS and av.currency in ("USD", "BASE", ""):
                try:
                    raw[av.tag] = float(av.value)
                except (ValueError, TypeError):
                    pass
        logger.info(
            "ibkr get_account_summary nlv=%.2f buying_power=%.2f",
            raw.get("NetLiquidation", 0.0),
            raw.get("BuyingPower", 0.0),
        )
        return AccountSummary(
            net_liquidation=raw.get("NetLiquidation", 0.0),
            equity_with_loan_value=raw.get("EquityWithLoanValue", 0.0),
            buying_power=raw.get("BuyingPower", 0.0),
            gross_position_value=raw.get("GrossPositionValue", 0.0),
            total_cash_value=raw.get("TotalCashValue", 0.0),
            available_funds=raw.get("AvailableFunds", 0.0),
            initial_margin=raw.get("InitialMarginReq", 0.0),
            maintenance_margin=raw.get("MaintMarginReq", 0.0),
            excess_liquidity=raw.get("ExcessLiquidity", 0.0),
            leverage=raw.get("Leverage", 0.0),
        )

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_quote(self, symbol: str) -> dict:
        """Real-time snapshot quote for a US equity."""
        await self._ensure_connected()
        contract = Stock(symbol, "SMART", "USD")
        [contract] = await self._ib.qualifyContractsAsync(contract)
        # reqTickersAsync fires a single-shot snapshot and waits for data.
        [ticker] = await self._ib.reqTickersAsync(contract)
        last = _pos_float(ticker.last) or _pos_float(ticker.close)
        bid = _pos_float(ticker.bid)
        ask = _pos_float(ticker.ask)
        logger.info("ibkr get_quote symbol=%s last=%s bid=%s ask=%s", symbol, last, bid, ask)
        return {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "last": last,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_price_history(
        self, symbol: str, timeframe: str = "1d", lookback_days: int = 365
    ) -> PriceHistory:
        """Historical OHLCV bars from TWS.

        Daily bars (1d) are returned with a ``datetime.date`` object for
        ``BarData.date``; intraday bars use ``datetime.datetime``. Both are
        normalised to ``datetime`` before constructing PriceBar.
        """
        await self._ensure_connected()
        contract = Stock(symbol, "SMART", "USD")
        [contract] = await self._ib.qualifyContractsAsync(contract)
        bar_size = _BAR_SIZE.get(timeframe, "1 day")
        # IB max lookback for daily bars is 365 D; for intraday it varies.
        duration = f"{min(lookback_days, 365)} D"
        raw_bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
        )
        bars = [
            PriceBar(
                timestamp=_to_datetime(b.date),
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume),
            )
            for b in raw_bars
        ]
        logger.info(
            "ibkr get_price_history symbol=%s timeframe=%s bars=%d", symbol, timeframe, len(bars)
        )
        return PriceHistory(symbol=symbol, timeframe=timeframe, bars=bars)

    # ------------------------------------------------------------------
    # Option chain
    # ------------------------------------------------------------------

    async def get_iv_rank(self, symbol: str) -> IVRank:
        """Compute 52-week HV rank from daily price history.

        Uses 30-day realised vol as a proxy for implied vol when IB market-data
        subscriptions don't expose historical IV.  Returns both rank (position in
        min–max range) and percentile (fraction of days below).
        """
        import numpy as np

        history = await self.get_price_history(symbol, timeframe="1d", lookback_days=365)
        closes = np.array([b.close for b in history.bars], dtype=float)
        if len(closes) < 32:
            return IVRank(symbol=symbol, current_hv30=0.0, hv_rank_52w=0.0, hv_pct_52w=0.0)

        log_rets = np.log(closes[1:] / closes[:-1])
        # Rolling 30-day annualised vol
        window = 30
        hv_series = np.array([
            log_rets[i - window:i].std() * (252 ** 0.5)
            for i in range(window, len(log_rets) + 1)
        ])
        current = float(hv_series[-1])
        lo, hi = float(hv_series.min()), float(hv_series.max())
        rank = ((current - lo) / (hi - lo) * 100) if hi > lo else 0.0
        pct = float((hv_series < current).mean() * 100)

        # Try to get current IV from IB market data (generic tick 106)
        iv_current: Optional[float] = None
        try:
            await self._ensure_connected()
            contract = Stock(symbol, "SMART", "USD")
            [contract] = await self._ib.qualifyContractsAsync(contract)
            ticker = self._ib.reqMktData(contract, genericTickList="106", snapshot=True)
            await asyncio.sleep(3)
            self._ib.cancelMktData(contract)
            if ticker.impliedVolatility and ticker.impliedVolatility > 0:
                iv_current = float(ticker.impliedVolatility)
        except Exception:
            pass

        logger.info(
            "ibkr get_iv_rank symbol=%s current_hv30=%.4f rank=%.1f pct=%.1f iv=%s",
            symbol, current, rank, pct, iv_current,
        )
        return IVRank(
            symbol=symbol,
            current_hv30=current,
            hv_rank_52w=rank,
            hv_pct_52w=pct,
            iv_current=iv_current,
        )

    async def get_technicals(self, symbol: str, lookback_days: int = 365):
        """Compute technical indicators from daily price history."""
        from technicals import compute_technicals

        history = await self.get_price_history(symbol, timeframe="1d", lookback_days=lookback_days)
        return compute_technicals(history)

    async def get_trade_idea(self, symbol: str, expiry: Optional[str] = None, fundamentals=None):
        """Generate one concrete, profit-seeking option trade for ``symbol``.

        Orchestration only: pulls the live chain + IV rank + technicals (and
        optional fundamentals supplied by the caller), then delegates structure
        selection and pricing to ``strategy_engine.generate_trade_idea``.
        """
        # Local import avoids a circular dependency (strategy_engine imports models only).
        from strategy_engine import generate_trade_idea

        chain = await self.get_option_chain(symbol, expiry)
        ivr = await self.get_iv_rank(symbol)
        technicals = await self.get_technicals(symbol)
        puts = [c for c in chain.contracts if c.opt_type == "put"]
        calls = [c for c in chain.contracts if c.opt_type == "call"]
        idea = generate_trade_idea(
            symbol=symbol,
            spot=chain.underlying_price,
            expiry=chain.expiry,
            days_to_expiry=chain.days_to_expiry,
            put_contracts=puts,
            call_contracts=calls,
            hv30=ivr.current_hv30,
            iv_rank=ivr.hv_rank_52w,
            fundamentals=fundamentals,
            technicals=technicals,
        )
        return idea

    async def get_option_chain(self, symbol: str, expiry: Optional[str] = None) -> OptionChain:
        """Live option chain for the nearest expiry ≥ 2 weeks out (or the
        supplied ``expiry`` in YYYY-MM-DD format).

        Fetches strikes within ±20% of spot to stay within IB's concurrent
        market-data line limits. Greeks come from IB's model (impliedVol,
        delta, gamma, theta, vega on each Ticker.modelGreeks).
        """
        await self._ensure_connected()
        underlying = Stock(symbol, "SMART", "USD")
        [underlying] = await self._ib.qualifyContractsAsync(underlying)

        # Underlying price via snapshot; fall back to last daily close if data
        # is unavailable (common on paper-trading accounts without live subscriptions).
        [ul_ticker] = await self._ib.reqTickersAsync(underlying)
        spot = _pos_float(ul_ticker.last) or _pos_float(ul_ticker.close)
        if not spot:
            bars = await self._ib.reqHistoricalDataAsync(
                underlying, endDateTime="", durationStr="3 D",
                barSizeSetting="1 day", whatToShow="TRADES", useRTH=True,
            )
            if bars:
                spot = float(bars[-1].close)
        spot = spot or 0.0

        # Chain parameters: available expiries and strikes.
        params = await self._ib.reqSecDefOptParamsAsync(
            symbol, "", underlying.secType, underlying.conId
        )
        chain_params = next((p for p in params if p.exchange == "SMART"), None)
        if not chain_params:
            logger.warning("ibkr get_option_chain no SMART chain for symbol=%s", symbol)
            return OptionChain(
                underlying=symbol, underlying_price=spot,
                expiry="", days_to_expiry=0, contracts=[], available_expiries=[],
            )

        today = datetime.utcnow().date()
        sorted_expiries = sorted(chain_params.expirations)
        # Expose expiries as YYYY-MM-DD for the frontend dropdown
        available_expiries = [
            f"{e[:4]}-{e[4:6]}-{e[6:]}" for e in sorted_expiries
        ]

        if expiry:
            chosen_yyyymmdd = expiry.replace("-", "")
        else:
            two_weeks_out = (today + timedelta(weeks=2)).strftime("%Y%m%d")
            chosen_yyyymmdd = next(
                (e for e in sorted_expiries if e >= two_weeks_out),
                sorted_expiries[0] if sorted_expiries else "",
            )

        if not chosen_yyyymmdd:
            return OptionChain(
                underlying=symbol, underlying_price=spot,
                expiry="", days_to_expiry=0, contracts=[], available_expiries=available_expiries,
            )

        expiry_date = datetime.strptime(chosen_yyyymmdd, "%Y%m%d").date()
        dte = (expiry_date - today).days

        # Strikes within ±20% of spot — enough for v0.2 and well under IB's
        # concurrent market-data line limit. Reuse the resolved underlying's
        # tradingClass so the option qualifies against the same listing.
        lo_k, hi_k = spot * (1 - _STRIKE_RANGE), spot * (1 + _STRIKE_RANGE)
        selected_strikes = [k for k in sorted(chain_params.strikes) if lo_k <= k <= hi_k]
        trading_class = chain_params.tradingClass or symbol

        contracts = [
            Option(symbol, chosen_yyyymmdd, strike, right, "SMART", tradingClass=trading_class)
            for strike in selected_strikes
            for right in ("C", "P")
        ]
        qualified = await self._ib.qualifyContractsAsync(*contracts)

        # Fetch market data in parallel, chunked to avoid pacing violations on
        # wide chains. reqTickersAsync subscribes, waits for a snapshot, cancels.
        chunks = [qualified[i:i + _CHAIN_BATCH] for i in range(0, len(qualified), _CHAIN_BATCH)]
        results = await asyncio.gather(
            *(self._ib.reqTickersAsync(*chunk) for chunk in chunks)
        )
        tickers = [t for batch in results for t in batch]

        option_contracts: list[OptionContract] = []
        for t in tickers:
            c = t.contract
            if not c or not c.strike:
                continue
            right = (c.right or "").upper()
            opt_type = "call" if right == "C" else "put"
            g = t.modelGreeks
            # Volume and OI are split into call/put fields on the underlying's
            # ticker; for individual option contract tickers use the appropriate side.
            vol = t.callVolume if opt_type == "call" else t.putVolume
            oi = t.callOpenInterest if opt_type == "call" else t.putOpenInterest
            option_contracts.append(
                OptionContract(
                    symbol=c.localSymbol or c.symbol,
                    expiry=expiry_date.isoformat(),
                    strike=float(c.strike),
                    opt_type=opt_type,  # type: ignore[arg-type]
                    bid=_pos_float(t.bid),
                    ask=_pos_float(t.ask),
                    last=_pos_float(t.last),
                    volume=int(vol) if vol and vol > 0 else None,
                    open_interest=int(oi) if oi and oi > 0 else None,
                    iv=g.impliedVol if g else None,
                    delta=g.delta if g else None,
                    gamma=g.gamma if g else None,
                    theta=g.theta if g else None,
                    vega=g.vega if g else None,
                )
            )

        option_contracts.sort(key=lambda x: (x.strike, x.opt_type))
        logger.info(
            "ibkr get_option_chain symbol=%s expiry=%s dte=%d contracts=%d",
            symbol, expiry_date.isoformat(), dte, len(option_contracts),
        )
        return OptionChain(
            underlying=symbol,
            underlying_price=float(spot),
            expiry=expiry_date.isoformat(),
            days_to_expiry=dte,
            contracts=option_contracts,
            available_expiries=available_expiries,
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _float(val: object) -> float:
    """Convert an ib_insync value to float; return 0.0 for None/nan."""
    try:
        f = float(val)  # type: ignore[arg-type]
        return 0.0 if f != f else f  # NaN check
    except (TypeError, ValueError):
        return 0.0


def _pos_float(val: object) -> Optional[float]:
    """Return a positive float or None (used for bid/ask/last where 0 / -1 means absent)."""
    try:
        f = float(val)  # type: ignore[arg-type]
        return f if f > 0 and f == f else None
    except (TypeError, ValueError):
        return None


def _to_datetime(d: object) -> datetime:
    """Normalise IB BarData.date to datetime.

    Daily bars: ``datetime.date`` → midnight UTC.
    Intraday bars: ``datetime.datetime`` → returned as-is.
    String fallback: ISO parse.
    """
    if isinstance(d, datetime):
        return d
    if isinstance(d, date):
        return datetime(d.year, d.month, d.day)
    try:
        return datetime.fromisoformat(str(d))
    except ValueError:
        return datetime.utcnow()
