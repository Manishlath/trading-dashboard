# Trading Dashboard

Personal trading and portfolio analytics dashboard, built with Claude Code.

Connects to **Interactive Brokers** for live positions, market data, and option chains; pulls **fundamentals from StockAnalysis.com** (Pro subscription); computes technicals, Greeks, and trade structures locally; and exposes everything through a React/Next.js UI with an embedded AI chat pane that routes queries to specialized Claude Code subagents.

> **Status:** scaffold. Modules below are stubs ready for iterative development with Claude Code.

## Architecture

```
IBKR TWS/Gateway     StockAnalysis.com     Web/News
        │                    │                │
        └──────────── MCP Layer ──────────────┘
                          │
                Claude Code Orchestrator
                          │
   ┌────────┬─────────┬──────────┬─────────┐
   │Funda-  │Techni-  │ Options  │Strategy │
   │mentals │cals     │ Engine   │Builder  │
   └────────┴─────────┴──────────┴─────────┘
                          │
              FastAPI Backend (REST/WS)
                          │
            Next.js Dashboard (React)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for full details.

## Modules

| Module | Status | File |
|---|---|---|
| Portfolio monitor | scaffold | `frontend/components/PortfolioMonitor.tsx` |
| Options desk | scaffold | `frontend/components/OptionsDesk.tsx` |
| Technicals | todo | — |
| Fundamentals | todo | — |
| Strategy console | todo | — |
| AI chat pane | todo | — |
| Black-Scholes / Greeks | ✅ implemented | `backend/options_math.py` |
| IBKR client | stub | `backend/ibkr_client.py` |
| StockAnalysis scraper | stub | `backend/stock_analysis_scraper.py` |

## Prerequisites

- **Python 3.11+** and **Node.js 20+**
- **Interactive Brokers** account with TWS or IB Gateway installed and API enabled (default port 4002 for Gateway, 7497 for TWS paper, 7496 for TWS live)
- **StockAnalysis.com Pro** subscription
- **Claude Code** installed: `npm install -g @anthropic-ai/claude-code`
- **IBKR MCP server** — choose one:
  - [`osauer/ibkr`](https://github.com/osauer/ibkr) — read-only, recommended for safety
  - [`ArjunDivecha/ibkr-mcp-server`](https://github.com/ArjunDivecha/ibkr-mcp-server) — full trading

## Setup

```bash
# 1. Clone
git clone https://github.com/<your-username>/trading-dashboard.git
cd trading-dashboard

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then fill in IBKR + StockAnalysis credentials
uvicorn main:app --reload --port 8000

# 3. Frontend (new terminal)
cd frontend
npm install
cp .env.example .env.local         # optional; defaults to http://localhost:8000
npm run dev                        # opens http://localhost:3000

# 4. Install IBKR MCP plugin for Claude Code
cd ..
claude
> /plugin marketplace add osauer/ibkr
> /plugin install ibkr@ibkr
```

## Configuration

Configuration is via environment variables. Copy the example files and fill them in locally — `.env` / `.env.local` are gitignored, so **never commit real credentials**.

### Backend (`backend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `IBKR_HOST` | `127.0.0.1` | IBKR Gateway/TWS host |
| `IBKR_PORT` | `4002` | `4002`=IB Gateway, `7497`=TWS paper, `7496`=TWS live |
| `IBKR_CLIENT_ID` | `1` | IBKR API client id |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `FUNDAMENTALS_CACHE_HOURS` | `24` | In-process cache TTL for StockAnalysis responses |
| `STOCKANALYSIS_SESSION_COOKIE` | _(unset)_ | Optional; forwarded as the `Cookie` header to unlock Pro data |
| `STOCKANALYSIS_EMAIL` / `STOCKANALYSIS_PASSWORD` | _(unset)_ | Placeholders for future interactive login; currently unused |

> **StockAnalysis auth is optional.** The scraper (`backend/stock_analysis_scraper.py`) uses StockAnalysis.com's public JSON API and returns free-tier fundamentals without any credentials. Set `STOCKANALYSIS_SESSION_COOKIE` only if you have a Pro subscription and want Pro-only data — its value is sent as the `Cookie` header on each request.

### Frontend (`frontend/.env.local`)

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base URL of the FastAPI backend |

## Working with Claude Code

The repo includes:

- **`CLAUDE.md`** — system prompt loaded at every Claude Code session start. Keeps the model aligned with the architecture without re-explaining.
- **`.claude/agents/`** — five specialized subagents, each with isolated context and tool restrictions. Claude Code auto-routes tasks to the right one.

Example prompts to get started:

```text
> Build the put-selling screener: scan my IBKR watchlist, rank by IV rank,
  show 30-delta puts for next monthly expiry, compute premium-to-strike yield,
  and add a Kelly fraction column for position sizing.

> Add a candlestick chart with RSI(14) and MACD(12,26,9) overlays to the
  Technicals module using TradingView Lightweight Charts.

> Use the fundamentals-analyst subagent to pull a side-by-side comparison of
  NVDA, AMD, AVGO on revenue growth, gross margin trajectory, and forward PE.
```

## Safety

This dashboard is **read-only by default**. Order placement is intentionally not wired up in the initial scaffold. If you add order entry:

- Always gate orders behind an explicit UI confirmation step
- Never let an AI agent auto-submit orders without human review
- Test in IBKR paper trading first (port 7497)

## License

MIT — see [`LICENSE`](LICENSE).
