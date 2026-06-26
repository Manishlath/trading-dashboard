# Architecture

## Why this shape

The dashboard has two competing requirements: it must show **live** data (positions, quotes, chains) with low latency from a stable backend, and it must support **conversational analysis** that involves multiple data sources and reasoning steps. Conflating these into one process leads to either a chatty UI that's slow, or a clean UI that can't reason.

The solution: split them.

- **FastAPI backend** owns the boring, deterministic work — connect to IBKR, fetch data, compute Black-Scholes, cache fundamentals, serve REST endpoints.
- **Claude Code with subagents** owns the conversational and analytical work — read the deterministic endpoints, combine sources, and produce ranked actionable output.

This keeps the React UI predictable (fixed contracts to a typed API) and the AI layer flexible (it can change subagent prompts without breaking the dashboard).

## Components

### Backend (FastAPI)

Single-process Python app. Responsibilities:

- Hold the IBKR connection (TWS or Gateway, via `ib_insync`)
- Hold the StockAnalysis session
- Cache fundamentals (24h) and price history (1h)
- Expose REST endpoints for the dashboard
- Compute options math (`options_math.py`)

Runs on `localhost:8000`. No external exposure.

### Frontend (Next.js)

Next.js 14 app router. Polls the backend via SWR with sensible refresh intervals (positions 60s, account 60s, quotes 5s when active). Components are organized by module (`PortfolioMonitor`, `OptionsDesk`, `Technicals`, `Fundamentals`, `StrategyConsole`).

Runs on `localhost:3000`. Talks to backend via Next.js rewrites — no CORS dance in production builds.

### Claude Code layer

Three pieces:

1. **`CLAUDE.md`** — system prompt loaded into every session. Contains stack, conventions, file locations, safety rules. Kept under 1500 words to minimize per-turn overhead.

2. **Subagents** (`.claude/agents/*.md`) — five specialists with isolated context windows. Each owns one analytical domain and has restricted tool access.

3. **MCP servers** — `osauer/ibkr` provides read-only IBKR access directly from Claude Code (separate from the FastAPI's `ib_insync` connection). This lets Claude Code answer "show me my positions" without going through the backend.

## Data flow examples

### "Show my portfolio"
```
User → Dashboard → SWR poll → GET /api/portfolio
                                ↓
                          IBKRClient.get_positions()
                                ↓
                          ib_insync.positions()
                                ↓
                          → Position[] → render table
```

### "Find puts to sell on NVDA, AVGO, GOOG"
```
User → Claude Code chat pane
         ↓
Orchestrator routes to options-engine subagent (×3 parallel)
         ↓
Each subagent calls /api/chain/{symbol} + /api/quote/{symbol}
         ↓
options_math.iv_rank(), screens 30-delta puts, computes yields
         ↓
Returns to orchestrator → merged ranked table → UI
```

The two `parallel`s are key: subagents have independent context windows, so screening 3 underlyings happens concurrently without context pollution. (See [Claude Code subagents docs](https://docs.anthropic.com/en/docs/claude-code/subagents).)

## Token efficiency

Three patterns:

1. **System prompt in `CLAUDE.md`, not in every user message.** Loaded once per session.

2. **Subagents instead of one monolithic prompt.** Each subagent prompt is ~300 words instead of one ~2000-word omni-prompt. Only the relevant subagent's prompt enters context per turn.

3. **File paths, not blobs.** When a subagent returns a 500-row chain or 1-year price history, it writes to `/tmp/agent_outputs/` and returns the path. The orchestrator reads only what it needs.

The combined effect: a typical "find puts" query that touches 3 chains stays around 8-12k tokens of input per turn instead of 40k+.

## Future extensions

- **WebSocket channel** for live quotes (currently polled at 5s)
- **News subagent** that watches earnings calendar + flags catalyst events
- **Backtest module** — same `options_math` code, historical chain replay
- **Mobile read-only view** — separate Next.js route at `/m` with simpler layout

## Out of scope

- Order placement from the UI (planned for v2, behind explicit confirm gates)
- Multi-user / authentication (single-user, local-only)
- Cloud deployment (designed to run on the same machine as IB Gateway)
