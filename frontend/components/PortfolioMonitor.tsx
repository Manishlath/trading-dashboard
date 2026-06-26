'use client';

import useSWR from 'swr';
import { api, type Position } from '@/lib/api';

export function PortfolioMonitor() {
  const { data: positions, error, isLoading } = useSWR<Position[]>(
    '/api/portfolio',
    api.portfolio,
    { refreshInterval: 60000 },
  );
  const { data: account } = useSWR('/api/account', api.account, {
    refreshInterval: 60000,
  });

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-4 text-lg font-medium">Portfolio</h2>

      {account && (
        <div className="mb-4 grid grid-cols-4 gap-4 text-sm">
          <Metric label="Net liquidation" value={fmt(account.net_liquidation)} />
          <Metric label="Buying power" value={fmt(account.buying_power)} />
          <Metric label="Margin used" value={fmt(account.maintenance_margin)} />
          <Metric label="Leverage" value={`${account.leverage.toFixed(2)}x`} />
        </div>
      )}

      {isLoading && <p className="text-text-secondary">Loading positions…</p>}
      {error && <p className="text-negative">Failed to load positions.</p>}

      {positions && positions.length > 0 && (
        <table className="w-full text-sm">
          <thead className="text-left text-text-secondary">
            <tr>
              <th className="py-2">Symbol</th>
              <th>Qty</th>
              <th>Price</th>
              <th>Value</th>
              <th>Unrealized P&L</th>
              <th>Day P&L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.contract_id} className="border-t border-border">
                <td className="py-2 font-mono">{p.symbol}</td>
                <td>{p.quantity}</td>
                <td>{p.market_price.toFixed(2)}</td>
                <td>{fmt(p.market_value)}</td>
                <td className={p.unrealized_pnl >= 0 ? 'text-positive' : 'text-negative'}>
                  {fmt(p.unrealized_pnl)}
                </td>
                <td className={p.daily_pnl >= 0 ? 'text-positive' : 'text-negative'}>
                  {fmt(p.daily_pnl)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {positions && positions.length === 0 && (
        <p className="text-text-secondary">
          No positions yet. Connect IBKR via the MCP plugin to populate.
        </p>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-text-secondary">{label}</div>
      <div className="text-lg">{value}</div>
    </div>
  );
}

function fmt(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}
