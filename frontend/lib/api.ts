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

const BASE = '';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API ${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  portfolio: () => get<Position[]>('/api/portfolio'),
  account: () => get<AccountSummary>('/api/account'),
  quote: (symbol: string) => get<Record<string, unknown>>(`/api/quote/${symbol}`),
  chain: (symbol: string, expiry?: string) =>
    get<Record<string, unknown>>(
      `/api/chain/${symbol}${expiry ? `?expiry=${expiry}` : ''}`,
    ),
  fundamentals: (symbol: string) =>
    get<Record<string, unknown>>(`/api/fundamentals/${symbol}`),
};
