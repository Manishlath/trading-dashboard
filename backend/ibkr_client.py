"""
IBKR client wrapper.

This is a STUB. Wire up to ib_insync or to the osauer/ibkr MCP server depending
on whether you need read-only or trading-capable access.

The MCP route is preferred for use inside Claude Code (no API key handling,
auto-reconnect, well-tested). For direct backend access from the FastAPI app
that the dashboard talks to, ib_insync is simpler.

TODO (Claude Code prompt):
    > Replace these stubs with real ib_insync calls. Connect on first request
    > and keep the IB connection alive across requests using FastAPI's lifespan.
    > Add structured logging and exponential backoff on disconnect.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from models import AccountSummary, OptionChain, Position, PriceHistory


class IBKRClient:
    """Wraps Interactive Brokers TWS/Gateway API for the dashboard."""

    def __init__(self, host: str, port: int, client_id: int) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self._connected = False

    async def connect(self) -> None:
        """Establish connection to TWS/Gateway.

        TODO: use ib_insync.IB().connectAsync(host, port, clientId)
        """
        # from ib_insync import IB
        # self._ib = IB()
        # await self._ib.connectAsync(self.host, self.port, clientId=self.client_id)
        self._connected = True

    async def disconnect(self) -> None:
        if self._connected:
            # self._ib.disconnect()
            self._connected = False

    async def get_positions(self) -> list[Position]:
        """Return all open positions.

        TODO: parse self._ib.positions() into Position models.
        """
        if not self._connected:
            await self.connect()
        # Placeholder
        return []

    async def get_account_summary(self) -> AccountSummary:
        """Return account-level financial metrics.

        TODO: use self._ib.accountSummary() and map to AccountSummary fields.
        """
        if not self._connected:
            await self.connect()
        return AccountSummary(
            net_liquidation=0.0,
            equity_with_loan_value=0.0,
            buying_power=0.0,
            gross_position_value=0.0,
            total_cash_value=0.0,
            available_funds=0.0,
            initial_margin=0.0,
            maintenance_margin=0.0,
            excess_liquidity=0.0,
            leverage=0.0,
        )

    async def get_quote(self, symbol: str) -> dict:
        """Real-time quote snapshot.

        TODO: use reqMktData with snapshot=True.
        """
        return {"symbol": symbol, "bid": None, "ask": None, "last": None, "timestamp": datetime.utcnow().isoformat()}

    async def get_price_history(
        self, symbol: str, timeframe: str = "1d", lookback_days: int = 365
    ) -> PriceHistory:
        """Historical OHLCV bars.

        TODO: reqHistoricalData with durationStr=f'{lookback_days} D'.
        """
        return PriceHistory(symbol=symbol, timeframe=timeframe, bars=[])

    async def get_option_chain(self, symbol: str, expiry: Optional[str] = None) -> OptionChain:
        """Full option chain for one underlying.

        TODO: reqSecDefOptParams to get expiries + strikes, then reqMktData
        for each contract (parallelise — chains are big).
        """
        return OptionChain(
            underlying=symbol,
            underlying_price=0.0,
            expiry=expiry or "",
            days_to_expiry=0,
            contracts=[],
        )
