/**
 * Typed API client for the FastAPI backend.
 */

export type Position = {
  contract_id: number;
  symbol: string;
  asset_class: 'STK' | 'OPT' | 'FOP' | 'BOND' | 'CASH' | 'FUT';
  description: string;
  quantity: number;
  market_price: number;
  market_value: number;
  average_price: number;
  unrealized_pnl: number;
  daily_pnl: number;
  currency: string;
};

export type AccountSummary = {
  net_liquidation: number;
  equity_with_loan_value: number;
  buying_power: number;
  gross_position_value: number;
  total_cash_value: number;
  available_funds: number;
  initial_margin: number;
  maintenance_margin: number;
  excess_liquidity: number;
  leverage: number;
  currency: string;
};

export type OptionContract = {
  symbol: string;
  expiry: string;
  strike: number;
  opt_type: 'call' | 'put';
  bid: number | null;
  ask: number | null;
  last: number | null;
  volume: number | null;
  open_interest: number | null;
  iv: number | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
};

export type OptionChain = {
  underlying: string;
  underlying_price: number;
  expiry: string;
  days_to_expiry: number;
  contracts: OptionContract[];
  available_expiries: string[];
};

export type IVRank = {
  symbol: string;
  current_hv30: number;
  hv_rank_52w: number;
  hv_pct_52w: number;
  iv_current: number | null;
  iv_rank_52w: number | null;
};

export type TradeLeg = {
  action: 'buy' | 'sell';
  opt_type: 'call' | 'put';
  strike: number;
  expiry: string;
  quantity: number;
  mid_price: number;
  delta: number | null;
  bid: number | null;
  ask: number | null;
  spread_pct: number | null;
  open_interest: number | null;
  volume: number | null;
};

export type TradeIdea = {
  symbol: string;
  generated_at: string;
  strategy: string;
  direction: string;
  thesis: string;
  underlying_price: number;
  expiry: string;
  days_to_expiry: number;
  legs: TradeLeg[];
  contracts: number;
  net_credit: number;
  max_profit: number;
  max_loss: number;
  breakevens: number[];
  prob_of_profit: number;
  return_on_risk: number;
  iv_rank: number;
  hv30: number;
  pnl_curve: [number, number][];
  signals: string[];
  liquidity_ok: boolean;
  liquidity_warnings: string[];
  est_slippage: number;
};

export type ScreenCandidate = {
  symbol: string;
  score: number;
  bias: string;
  last_price: number;
  trend: string;
  momentum: string;
  rsi14: number | null;
  pe_ratio: number | null;
  forward_pe: number | null;
  peg_ratio: number | null;
  net_margin: number | null;
  roe: number | null;
  hv_rank: number | null;
  signals: string[];
};

export type ScreenResult = {
  generated_at: string;
  universe: string[];
  candidates: ScreenCandidate[];
};

export type MomentumName = {
  ticker: string;
  rank: number;
  trend: number;
  mkt_adj: number;
  score: number;
  selected: boolean;
};

export type MomentumBacktest = {
  start: string;
  end: string;
  rebalances: number;
  total_return: number;
  cagr: number;
  max_drawdown: number;
  spy_total: number;
  excess_vs_spy: number;
  curve: { date: string; strategy: number; spy: number }[];
  yearly: { year: number; strategy: number }[];
  current_holdings: string[];
  error?: string;
};

// Same-origin by default: next.config.js rewrites /api/* to the backend, which
// works from any device (desktop or phone on the LAN) without CORS.
const BASE = process.env.NEXT_PUBLIC_API_URL ?? '';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

export const api = {
  portfolio: () => get<Position[]>('/api/portfolio'),
  account: () => get<AccountSummary>('/api/account'),
  quote: (symbol: string) => get<Record<string, unknown>>(`/api/quote/${symbol}`),
  chain: (symbol: string, expiry?: string) =>
    get<OptionChain>(`/api/chain/${symbol}${expiry ? `?expiry=${expiry}` : ''}`),
  ivRank: (symbol: string) => get<IVRank>(`/api/ivrank/${symbol}`),
  tradeIdea: (symbol: string, expiry?: string) =>
    get<TradeIdea>(`/api/trade-idea/${symbol}${expiry ? `?expiry=${expiry}` : ''}`),
  screen: (symbols?: string[]) =>
    get<ScreenResult>(`/api/screen${symbols?.length ? `?symbols=${symbols.join(',')}` : ''}`),
  momentumUniverse: (market = 'us') =>
    get<{ universe: string[] }>(`/api/momentum/universe?market=${market}`),
  momentumRank: (symbols: string[], market = 'us') =>
    get<{ generated_at: string; ranking: MomentumName[] }>(
      `/api/momentum/rank?symbols=${encodeURIComponent(symbols.join(','))}&market=${market}`),
  momentumBacktest: (symbols: string[], start: string, end: string, market = 'us') =>
    get<MomentumBacktest>(
      `/api/momentum/backtest?symbols=${encodeURIComponent(symbols.join(','))}&start=${start}&end=${end}&market=${market}`),
  fundamentals: (symbol: string) =>
    get<Record<string, unknown>>(`/api/fundamentals/${symbol}`),
};
