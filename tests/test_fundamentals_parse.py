"""Tests for StockAnalysis parsing helpers (offline — no network)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import pytest  # noqa: E402

from stock_analysis_scraper import _index, _num  # noqa: E402


class TestNumParse:
    def test_plain_number(self):
        assert _num("29.98") == 29.98

    def test_trillion_suffix(self):
        assert _num("4.71T") == 4.71e12

    def test_billion_suffix(self):
        assert _num("253.49B") == 253.49e9

    def test_percent_becomes_fraction(self):
        assert _num("74.145%") == pytest.approx(0.74145)

    def test_dollar_and_parenthetical(self):
        # "$1.00 (0.51%)" -> leading token 1.00
        assert _num("$1.00 (0.51%)") == 1.0

    def test_commas_stripped(self):
        assert _num("4,707,743,487,983") == 4707743487983.0

    def test_none_and_dashes(self):
        assert _num(None) is None
        assert _num("-") is None
        assert _num("n/a") is None


class TestIndex:
    def test_flattens_to_id_hover_map(self):
        section = {
            "data": [
                {"id": "pe", "title": "PE Ratio", "value": "29.98", "hover": "29.977"},
                {"id": "peForward", "title": "Forward PE", "value": "19.70"},
            ]
        }
        idx = _index(section)
        assert idx["pe"] == "29.977"        # prefers hover
        assert idx["peForward"] == "19.70"  # falls back to value

    def test_empty_section(self):
        assert _index({}) == {}
        assert _index({"data": []}) == {}
