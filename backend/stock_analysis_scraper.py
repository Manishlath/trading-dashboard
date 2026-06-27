"""
StockAnalysis.com client.

StockAnalysis exposes a JSON API behind the website that returns the same data
shown on the statistics/overview pages — no HTML scraping or JS rendering
needed. Public (free-tier) data covers everything in the ``Fundamentals`` model;
a Pro ``session_cookie`` is forwarded when supplied to unlock Pro-only history.

Endpoints used:
  - /api/symbol/s/{symbol}/overview     -> market cap, PE, EPS, dividend, earnings date
  - /api/symbol/s/{symbol}/statistics   -> margins, ratios, ROE, debt/equity, PEG

Responses are cached in-process for ``FUNDAMENTALS_CACHE_HOURS`` (default 24h).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Any, Optional

import httpx

from models import Fundamentals

logger = logging.getLogger(__name__)

_SUFFIX = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}


def _num(raw: Any) -> Optional[float]:
    """Parse StockAnalysis display strings into floats.

    Handles ``$1.00``, ``4.71T``, ``74.145%``, ``29.98``, ``1,234,567`` and
    ``$1.00 (0.51%)`` (takes the leading token). Returns None when unparseable.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in {"-", "n/a", "N/A"}:
        return None
    s = s.split("(")[0].strip()           # "$1.00 (0.51%)" -> "$1.00"
    s = s.replace("$", "").replace(",", "").strip()
    is_pct = s.endswith("%")
    s = s.rstrip("%").strip()
    mult = 1.0
    if s and s[-1] in _SUFFIX:
        mult = _SUFFIX[s[-1]]
        s = s[:-1]
    try:
        val = float(s) * mult
    except ValueError:
        return None
    return val / 100.0 if is_pct else val


def _index(section: dict[str, Any]) -> dict[str, str]:
    """Flatten a statistics section's ``data`` list into ``{id: hover|value}``.

    Prefers the precise ``hover`` field, falling back to the display ``value``.
    """
    out: dict[str, str] = {}
    for item in (section or {}).get("data", []):
        if isinstance(item, dict) and "id" in item:
            out[item["id"]] = item.get("hover") or item.get("value")
    return out


class StockAnalysisClient:
    """Client for StockAnalysis.com (Pro session optional)."""

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
        self._cache_hours = float(os.getenv("FUNDAMENTALS_CACHE_HOURS", "24"))

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "Mozilla/5.0 (trading-dashboard)"}
        if self.session_cookie:
            headers["Cookie"] = self.session_cookie
        return headers

    async def login(self) -> None:
        """No-op: the JSON API is reachable without an interactive login.

        Pro entitlements ride on the ``session_cookie`` passed at construction.
        """
        return None

    async def _fetch(self, client: httpx.AsyncClient, path: str) -> dict[str, Any]:
        url = f"{self.BASE_URL}/api/symbol/s/{path}"
        logger.info("stockanalysis GET %s", path)
        resp = await client.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        body = resp.json()
        return body.get("data", {}) if isinstance(body, dict) else {}

    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        """Fetch a fundamentals snapshot, cached for ``FUNDAMENTALS_CACHE_HOURS``."""
        sym = symbol.upper()
        cached = self._cache.get(sym)
        if cached:
            ts, data = cached
            if (datetime.utcnow() - ts).total_seconds() < self._cache_hours * 3600:
                return data

        async with httpx.AsyncClient() as client:
            overview = await self._fetch(client, f"{sym}/overview")
            stats = await self._fetch(client, f"{sym}/statistics")

        ratios = _index(stats.get("ratios", {}))
        margins = _index(stats.get("margins", {}))
        efficiency = _index(stats.get("financialEfficiency", {}))
        position = _index(stats.get("financialPosition", {}))
        valuation = _index(stats.get("valuation", {}))
        dividends = _index(stats.get("dividends", {}))

        data = Fundamentals(
            symbol=sym,
            fetched_at=datetime.utcnow(),
            market_cap=_num(valuation.get("marketcap") or overview.get("marketCap")),
            pe_ratio=_num(ratios.get("pe") or overview.get("peRatio")),
            forward_pe=_num(ratios.get("peForward") or overview.get("forwardPE")),
            peg_ratio=_num(ratios.get("pegRatio")),
            price_to_sales=_num(ratios.get("ps")),
            price_to_book=_num(ratios.get("pb")),
            eps_ttm=_num(overview.get("eps")),
            gross_margin=_num(margins.get("grossMargin")),
            operating_margin=_num(margins.get("operatingMargin")),
            net_margin=_num(margins.get("profitMargin")),
            roe=_num(efficiency.get("roe")),
            debt_to_equity=_num(position.get("debtEquity")),
            dividend_yield=_num(dividends.get("dividendYield")),
            next_earnings_date=overview.get("earningsDate"),
        )
        logger.info(
            "stockanalysis fundamentals symbol=%s pe=%s fwd_pe=%s peg=%s net_margin=%s",
            sym, data.pe_ratio, data.forward_pe, data.peg_ratio, data.net_margin,
        )
        self._cache[sym] = (datetime.utcnow(), data)
        return data
