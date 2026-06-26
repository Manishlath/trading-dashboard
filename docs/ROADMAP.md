# Roadmap

## v0.1 — Scaffold ✅ (this commit)
- Repository structure
- Backend skeleton with options math implemented and tested
- Frontend skeleton with Portfolio + Options Desk placeholders
- CLAUDE.md + five subagent definitions
- Documentation

## v0.2 — Live data wired up
- [ ] Implement `ibkr_client.py` with `ib_insync` — positions, account, quotes
- [ ] Test `/api/portfolio` returns real data
- [ ] Polish `PortfolioMonitor` UI — sortable columns, currency conversion, sector grouping
- [ ] Add error boundaries and connection state indicators

## v0.3 — Options desk
- [ ] Implement `IBKRClient.get_option_chain()` — handle large chains (paginate)
- [ ] Chain viewer UI: filterable by expiry, strike range
- [ ] Show live Greeks (delta, gamma, theta, vega) from IBKR
- [ ] IV rank from 1Y historical IV (need to store time-series)

## v0.4 — Fundamentals
- [ ] Implement `StockAnalysisClient` with playwright
- [ ] Login flow with cached session cookie
- [ ] Parse statistics page → `Fundamentals` model
- [ ] Fundamentals card in UI

## v0.5 — Technicals
- [ ] OHLCV pull from IBKR with caching
- [ ] Indicator computations (pandas-based)
- [ ] Candlestick chart with TradingView Lightweight Charts
- [ ] RSI / MACD overlays

## v0.6 — Strategy console
- [ ] Spread builder UI
- [ ] P&L curve visualization
- [ ] Kelly sizing widget
- [ ] Put-selling screener

## v0.7 — AI chat pane
- [ ] Embed chat UI that talks to Claude Code via local socket
- [ ] Route conversational queries to subagents
- [ ] Stream responses with markdown rendering

## Stretch
- [ ] Backtest replay (historical chains)
- [ ] Earnings calendar overlay
- [ ] WebSocket live quotes
- [ ] Order entry with confirm gates (separate Level 2 risk)
