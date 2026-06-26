"""
StockAnalysis.com Pro client.

This is a STUB. Wire up using either:
  - playwright with a logged-in browser context (handles JS rendering, robust)
  - httpx + session cookie (faster, fragile if site updates)

Endpoints to scrape:
  - /stocks/{symbol}/financials/             -> income statement
  - /stocks/{symbol}/financials/balance-sheet/ -> balance sheet
  - /stocks/{symbol}/financials/cash-flow/   -> cash flow
  - /stocks/{symbol}/statistics/             -> ratios, margins, growth
  - /stocks/{symbol}/earnings/               -> earnings history + next date

TODO (Claude Code prompt):
    > Implement using playwright. Add login flow that caches the session cookie
    > to disk and refreshes when stale. Parse the statistics page into the
    > Fundamentals model. Cache responses for 24h based on FUNDAMENTALS_CACHE_HOURS.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from models import Fundamentals


class StockAnalysisClient:
    """Client for StockAnalysis.com Pro."""

    BASE_URL = "https://stockanalysis.com"

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        session_cookie: Optional[str] = None,
    ) -> None:
        self.email = email
        self.password = password
        self.session_cookie = session_cookie
        self._cache: dict[str, tuple[datetime, Fundamentals]] = {}

    async def login(self) -> None:
        """Authenticate and cache session.

        TODO: implement with playwright headless browser.
        """
        pass

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        """Fetch fundamentals snapshot for a symbol.

        TODO: scrape /stocks/{symbol}/statistics/ for ratios, margins, growth.
        Cache for FUNDAMENTALS_CACHE_HOURS hours.
        """
        # Cache check
        cached = self._cache.get(symbol.upper())
        if cached:
            ts, data = cached
            if (datetime.utcnow() - ts).total_seconds() < 24 * 3600:
                return data

        # Placeholder
        data = Fundamentals(symbol=symbol.upper(), fetched_at=datetime.utcnow())
        self._cache[symbol.upper()] = (datetime.utcnow(), data)
        return data
