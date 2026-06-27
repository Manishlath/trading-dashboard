"""Tests for IBKRClient — ib_insync.IB is fully mocked; no TWS required.

Run with:
    pytest tests/test_ibkr_client.py -v
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from ibkr_client import IBKRClient, _float, _pos_float, _to_datetime  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(mock_ib: MagicMock) -> IBKRClient:
    """Return an IBKRClient whose internal IB() is replaced by mock_ib."""
    with patch("ibkr_client.IB", return_value=mock_ib):
        client = IBKRClient("127.0.0.1", 4002, 1)
    client._ib = mock_ib
    return client


def _portfolio_item(
    *,
    con_id: int = 12345,
    symbol: str = "AAPL",
    sec_type: str = "STK",
    local_symbol: str = "AAPL",
    currency: str = "USD",
    position: float = 100.0,
    market_price: float = 150.0,
    market_value: float = 15000.0,
    average_cost: float = 140.0,
    unrealized_pnl: float = 1000.0,
    realized_pnl: float = 0.0,
) -> MagicMock:
    item = MagicMock()
    item.contract.conId = con_id
    item.contract.symbol = symbol
    item.contract.secType = sec_type
    item.contract.localSymbol = local_symbol
    item.contract.currency = currency
    item.position = position
    item.marketPrice = market_price
    item.marketValue = market_value
    item.averageCost = average_cost
    item.unrealizedPNL = unrealized_pnl
    item.realizedPNL = realized_pnl
    return item


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# get_positions
# ---------------------------------------------------------------------------

class TestGetPositions:
    def test_single_stock_maps_all_fields(self):
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.portfolio.return_value = [
            _portfolio_item(
                con_id=12345, symbol="AAPL", sec_type="STK",
                position=100.0, market_price=150.0, market_value=15000.0,
                average_cost=140.0, unrealized_pnl=1000.0,
            )
        ]
        client = _make_client(mock_ib)
        positions = run(client.get_positions())

        assert len(positions) == 1
        p = positions[0]
        assert p.contract_id == 12345
        assert p.symbol == "AAPL"
        assert p.asset_class == "STK"
        assert p.quantity == 100.0
        assert p.market_price == 150.0
        assert p.market_value == 15000.0
        assert p.average_price == 140.0
        assert p.unrealized_pnl == 1000.0
        assert p.currency == "USD"

    def test_option_position_uses_local_symbol_as_description(self):
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.portfolio.return_value = [
            _portfolio_item(
                symbol="AAPL", sec_type="OPT",
                local_symbol="AAPL  260117C00200000",
                position=2.0, market_price=5.5, market_value=1100.0,
                average_cost=3.0, unrealized_pnl=500.0,
            )
        ]
        client = _make_client(mock_ib)
        positions = run(client.get_positions())

        assert positions[0].asset_class == "OPT"
        assert positions[0].description == "AAPL  260117C00200000"

    def test_short_position_negative_quantity(self):
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.portfolio.return_value = [
            _portfolio_item(symbol="TSLA", position=-5.0, market_price=300.0,
                            market_value=-1500.0, unrealized_pnl=250.0)
        ]
        client = _make_client(mock_ib)
        positions = run(client.get_positions())
        assert positions[0].quantity == -5.0

    def test_empty_portfolio_returns_empty_list(self):
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.portfolio.return_value = []
        client = _make_client(mock_ib)
        assert run(client.get_positions()) == []

    def test_multiple_positions_all_mapped(self):
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.portfolio.return_value = [
            _portfolio_item(symbol="AAPL", position=10.0, market_price=150.0,
                            market_value=1500.0, average_cost=130.0, unrealized_pnl=200.0),
            _portfolio_item(symbol="MSFT", sec_type="STK", position=20.0,
                            market_price=400.0, market_value=8000.0,
                            average_cost=380.0, unrealized_pnl=400.0),
        ]
        client = _make_client(mock_ib)
        positions = run(client.get_positions())
        assert len(positions) == 2
        symbols = {p.symbol for p in positions}
        assert symbols == {"AAPL", "MSFT"}

    def test_gbp_position_preserves_currency(self):
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.portfolio.return_value = [
            _portfolio_item(symbol="BARC", currency="GBP", position=1000.0,
                            market_price=5.10, market_value=5100.0,
                            average_cost=5.00, unrealized_pnl=100.0)
        ]
        client = _make_client(mock_ib)
        positions = run(client.get_positions())
        assert positions[0].currency == "GBP"


# ---------------------------------------------------------------------------
# get_account_summary
# ---------------------------------------------------------------------------

class TestGetAccountSummary:
    def _make_av(self, tag: str, value: str, currency: str = "USD") -> MagicMock:
        av = MagicMock()
        av.tag = tag
        av.value = value
        av.currency = currency
        return av

    def test_maps_all_standard_tags(self):
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.accountValues.return_value = [
            self._make_av("NetLiquidation", "250000.00"),
            self._make_av("EquityWithLoanValue", "245000.00"),
            self._make_av("BuyingPower", "500000.00"),
            self._make_av("GrossPositionValue", "300000.00"),
            self._make_av("TotalCashValue", "50000.00"),
            self._make_av("AvailableFunds", "150000.00"),
            self._make_av("InitialMarginReq", "75000.00"),
            self._make_av("MaintMarginReq", "60000.00"),
            self._make_av("ExcessLiquidity", "190000.00"),
            self._make_av("Leverage", "1.20"),
        ]
        client = _make_client(mock_ib)
        summary = run(client.get_account_summary())

        assert summary.net_liquidation == 250000.0
        assert summary.buying_power == 500000.0
        assert summary.leverage == 1.20
        assert summary.initial_margin == 75000.0

    def test_missing_tags_default_to_zero(self):
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.accountValues.return_value = [
            self._make_av("NetLiquidation", "100000.00"),
        ]
        client = _make_client(mock_ib)
        summary = run(client.get_account_summary())

        assert summary.net_liquidation == 100000.0
        assert summary.buying_power == 0.0
        assert summary.leverage == 0.0

    def test_non_usd_tag_ignored_when_usd_present(self):
        """BASE-currency duplicate of a tag should not overwrite the USD one."""
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.accountValues.return_value = [
            self._make_av("NetLiquidation", "123456.00", "USD"),
            self._make_av("NetLiquidation", "99999.00", "GBP"),  # should be ignored
        ]
        client = _make_client(mock_ib)
        summary = run(client.get_account_summary())
        # USD value wins because it's processed first
        assert summary.net_liquidation == 123456.0


# ---------------------------------------------------------------------------
# Auto-reconnect
# ---------------------------------------------------------------------------

class TestAutoReconnect:
    def test_reconnect_fires_on_disconnect_event(self):
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.connectAsync = AsyncMock()
        # Capture the handler registered on disconnectedEvent
        handlers: list = []
        mock_ib.disconnectedEvent.__iadd__ = lambda self_, h: handlers.append(h)

        with patch("ibkr_client.IB", return_value=mock_ib):
            client = IBKRClient("127.0.0.1", 4002, 1)
        client._ib = mock_ib

        # connect() wires the handler
        with patch.object(client, "_connect_with_backoff", new=AsyncMock()):
            run(client.connect())

        assert len(handlers) == 1, "disconnect handler must be registered"

    def test_backoff_retries_on_connection_failure(self):
        """_connect_with_backoff must retry and eventually raise after max_attempts."""
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = False
        mock_ib.connectAsync = AsyncMock(side_effect=ConnectionRefusedError("refused"))

        client = _make_client(mock_ib)

        with patch("asyncio.sleep", new=AsyncMock()):  # skip real sleeps
            with pytest.raises(ConnectionRefusedError):
                run(client._connect_with_backoff(max_attempts=3))

        assert mock_ib.connectAsync.call_count == 3

    def test_backoff_delays_follow_exponential_sequence(self):
        """Sleep delays between retries must be 1, 2, 4, 8, … capped at 30s."""
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = False
        mock_ib.connectAsync = AsyncMock(side_effect=ConnectionRefusedError("refused"))

        client = _make_client(mock_ib)

        delays: list[float] = []

        async def _capture(d):
            delays.append(d)

        with patch("asyncio.sleep", new=_capture):
            with pytest.raises(ConnectionRefusedError):
                run(client._connect_with_backoff(max_attempts=8))

        # 7 sleeps between 8 attempts; doubling from 1s, capped at 30s.
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]

    def test_no_retry_if_already_connected(self):
        mock_ib = MagicMock()
        mock_ib.isConnected.return_value = True
        mock_ib.connectAsync = AsyncMock()

        client = _make_client(mock_ib)
        run(client._connect_with_backoff())

        mock_ib.connectAsync.assert_not_called()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_float_converts_normal(self):
        assert _float(1.5) == 1.5
        assert _float("2.0") == 2.0

    def test_float_returns_zero_for_none(self):
        assert _float(None) == 0.0

    def test_float_returns_zero_for_nan(self):
        assert _float(float("nan")) == 0.0

    def test_pos_float_positive_value(self):
        assert _pos_float(42.0) == 42.0

    def test_pos_float_zero_returns_none(self):
        assert _pos_float(0.0) is None

    def test_pos_float_negative_returns_none(self):
        assert _pos_float(-1.0) is None

    def test_pos_float_nan_returns_none(self):
        assert _pos_float(float("nan")) is None

    def test_to_datetime_from_date(self):
        d = date(2026, 6, 26)
        dt = _to_datetime(d)
        assert isinstance(dt, datetime)
        assert dt.year == 2026 and dt.month == 6 and dt.day == 26
        assert dt.hour == 0 and dt.minute == 0

    def test_to_datetime_from_datetime_passthrough(self):
        dt_in = datetime(2026, 6, 26, 15, 30)
        assert _to_datetime(dt_in) is dt_in

    def test_to_datetime_from_iso_string(self):
        dt = _to_datetime("2026-06-26T15:30:00")
        assert dt.year == 2026 and dt.hour == 15
