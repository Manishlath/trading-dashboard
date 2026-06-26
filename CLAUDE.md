# Trading Dashboard — Claude Code System Prompt

You are working on a personal trading dashboard. This file is loaded at the start of every Claude Code session.

## Project

Full-stack trading dashboard: Next.js frontend + FastAPI backend. Connects to Interactive Brokers via MCP for positions, market data, and option chains. Fundamentals are scraped from StockAnalysis.com (user has Pro subscription). All analytics (Black-Scholes, Greeks, technicals, strategy P&L) are computed locally in Python.

## Stack

- **Frontend:** React 18, Next.js 14 (app router), TypeScript strict, Tailwind, Recharts for charts, TradingView Lightweight Charts for candlesticks
- **Backend:** Python 3.11+, FastAPI, pandas, numpy, scipy
- **IBKR:** `osauer/ibkr` MCP plugin (read-only). If trading is needed, use `ib_insync` directly with explicit UI confirm gates
- **Auth:** local-only; session token in `.env`

## Modules (build in order)

1. **Portfolio monitor** — positions, P&L, Greek aggregates, margin usage
2. **Options desk** — live chain viewer, IV rank, Greeks, spread builder
3. **Technicals** — candlesticks + RSI, MACD, Bollinger, VWAP overlays
4. **Fundamentals** — income statement, balance sheet, growth from StockAnalysis
5. **Strategy console** — spread P&L sim, put-selling screener, Kelly sizing
6. **AI chat pane** — natural-language queries routed to subagents

## Data contracts

| Endpoint | Source | Cadence |
|---|---|---|
| `GET /api/portfolio` | IBKR `ibkr_positions` | 60s |
| `GET /api/quote/{symbol}` | IBKR `ibkr_quote` | 5s (live), on-demand otherwise |
| `GET /api/chain/{symbol}` | IBKR `ibkr_chain` | on-demand |
| `GET /api/history/{symbol}` | IBKR price history | on-demand, cached 1h |
| `GET /api/fundamentals/{symbol}` | StockAnalysis scraper | cached 24h |

All endpoints return JSON. WebSocket channel `/ws/quotes` for streaming subscriptions.

## Coding rules

- Python: type hints on every public function, docstrings on every module, no global state
- TypeScript: strict mode, no `any`
- No hardcoded credentials — use `.env` + `python-dotenv` / Next.js env vars
- Error boundaries around every React data-fetching component
- Responsive layout works at 1280px+ (no mobile target)

## Token-saving conventions

- Read `CLAUDE.md` only at session start; don't re-read on every file edit
- Delegate scraping, options math, and charting to subagents (see `.claude/agents/`)
- Subagent outputs go to `/tmp/agent_outputs/` and are read by the orchestrator via file paths
- Never embed raw option chain JSON in the main context window — always pass file paths
- For large refactors, ask before reading more than 3 files at once

## Key files

| File | Purpose |
|---|---|
| `backend/main.py` | FastAPI app, routes |
| `backend/ibkr_client.py` | IBKR connection wrapper |
| `backend/options_math.py` | Black-Scholes, Greeks, IV solver — **implemented** |
| `backend/stock_analysis_scraper.py` | StockAnalysis.com client |
| `backend/models.py` | Pydantic request/response models |
| `frontend/app/page.tsx` | Dashboard root |
| `frontend/components/*.tsx` | One file per module |
| `frontend/lib/api.ts` | Typed API client |

## Subagents available

- `fundamentals-analyst` — StockAnalysis scraping + interpretation
- `technicals-analyst` — RSI, MACD, Bollinger, support/resistance
- `options-engine` — chain analysis, Greeks, IV rank
- `strategy-builder` — spreads, P&L simulation, position sizing
- `portfolio-monitor` — IBKR position/PnL/margin polling

Invoke via natural language ("use the options-engine subagent to...") or let Claude Code auto-route.

## Safety

- Read-only by default — no order placement until explicitly enabled
- If implementing trading: gate every order on UI confirm, never auto-submit
- Test in IBKR paper trading (port 7497) first
