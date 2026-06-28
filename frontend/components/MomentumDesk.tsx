'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend,
} from 'recharts';
import { api, type MomentumName, type MomentumBacktest } from '@/lib/api';

function parseTickers(text: string): string[] {
  return Array.from(
    new Set(text.toUpperCase().split(/[\s,]+/).map((t) => t.trim()).filter(Boolean)),
  );
}

function Stat({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="rounded border border-border bg-bg px-3 py-2 text-center">
      <div className="text-[10px] uppercase tracking-wide text-text-secondary">{label}</div>
      <div className={`font-mono text-sm font-medium ${good ? 'text-green-400' : ''}`}>{value}</div>
    </div>
  );
}

export function MomentumDesk() {
  const [universeText, setUniverseText] = useState('');
  const [start, setStart] = useState('2023-01-01');
  const [end, setEnd] = useState('2026-06-27');
  const [ranking, setRanking] = useState<MomentumName[]>([]);
  const [bt, setBt] = useState<MomentumBacktest | null>(null);
  const [loading, setLoading] = useState<'rank' | 'bt' | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Seed the editable universe from the backend default once.
  useEffect(() => {
    api.momentumUniverse().then((d) => setUniverseText(d.universe.join(', '))).catch(() => {});
  }, []);

  const run = useCallback(
    async (mode: 'rank' | 'bt') => {
      const tickers = parseTickers(universeText);
      if (tickers.length < 12) {
        setError('Enter at least ~12 tickers for a meaningful ranking.');
        return;
      }
      setLoading(mode);
      setError(null);
      try {
        if (mode === 'rank') {
          setRanking((await api.momentumRank(tickers)).ranking);
        } else {
          const res = await api.momentumBacktest(tickers, start, end);
          if (res.error) setError(res.error);
          else setBt(res);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Request failed');
      } finally {
        setLoading(null);
      }
    },
    [universeText, start, end],
  );

  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium">Momentum desk</h2>
          <p className="text-xs text-text-secondary">
            Residual (market-adjusted) momentum · edit the universe and recalculate
          </p>
        </div>
        <span className="text-[10px] uppercase tracking-wide text-text-secondary">
          top 10 · top-20 buffer · SPY-200 safety
        </span>
      </div>

      {/* Editable universe */}
      <label className="mb-1 block text-[10px] uppercase tracking-wide text-text-secondary">
        Universe (comma / space separated — editable)
      </label>
      <textarea
        value={universeText}
        onChange={(e) => setUniverseText(e.target.value)}
        rows={3}
        className="mb-3 w-full resize-y rounded border border-border bg-bg px-2 py-1.5 font-mono text-xs outline-none focus:border-text-secondary"
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input value={start} onChange={(e) => setStart(e.target.value)}
          className="w-32 rounded border border-border bg-bg px-2 py-1.5 font-mono text-sm outline-none focus:border-text-secondary" />
        <span className="text-text-secondary">→</span>
        <input value={end} onChange={(e) => setEnd(e.target.value)}
          className="w-32 rounded border border-border bg-bg px-2 py-1.5 font-mono text-sm outline-none focus:border-text-secondary" />
        <button onClick={() => run('rank')} disabled={loading !== null}
          className="rounded border border-border bg-bg px-3 py-1.5 text-sm hover:border-text-secondary disabled:opacity-50">
          {loading === 'rank' ? 'Ranking…' : 'Rank top 10'}
        </button>
        <button onClick={() => run('bt')} disabled={loading !== null}
          className="rounded border border-border bg-bg px-3 py-1.5 text-sm hover:border-text-secondary disabled:opacity-50">
          {loading === 'bt' ? 'Backtesting…' : 'Backtest vs SPY'}
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Ranking table */}
      {ranking.length > 0 && (
        <div className="mb-4 overflow-hidden rounded border border-border">
          <table className="w-full text-sm">
            <thead className="bg-bg text-[10px] uppercase tracking-wide text-text-secondary">
              <tr>
                <th className="px-3 py-1.5 text-left">#</th>
                <th className="px-3 py-1.5 text-left">Ticker</th>
                <th className="px-3 py-1.5 text-right">Trend</th>
                <th className="px-3 py-1.5 text-right">Mkt Adj</th>
                <th className="px-3 py-1.5 text-right">Score</th>
                <th className="px-3 py-1.5 text-left">Action</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {ranking.slice(0, 15).map((r) => (
                <tr key={r.ticker}
                  className={`border-t border-border ${r.selected ? 'bg-green-950/20' : ''}`}>
                  <td className="px-3 py-1.5 text-text-secondary">{r.rank}</td>
                  <td className="px-3 py-1.5 font-medium">{r.ticker}</td>
                  <td className="px-3 py-1.5 text-right">{r.trend.toFixed(2)}</td>
                  <td className={`px-3 py-1.5 text-right ${r.mkt_adj < 0 ? 'text-red-400' : 'text-green-400'}`}>
                    {r.mkt_adj >= 0 ? '+' : ''}{r.mkt_adj.toFixed(2)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-medium">{r.score.toFixed(2)}</td>
                  <td className={`px-3 py-1.5 ${r.selected ? 'text-green-400' : 'text-text-secondary'}`}>
                    {r.selected ? 'Buy / Hold' : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Backtest result */}
      {bt && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
            <Stat label="Total" value={`${bt.total_return.toFixed(1)}%`} good={bt.total_return > bt.spy_total} />
            <Stat label="CAGR" value={`${bt.cagr.toFixed(1)}%`} />
            <Stat label="Max DD" value={`${bt.max_drawdown.toFixed(1)}%`} />
            <Stat label="SPY" value={`${bt.spy_total.toFixed(1)}%`} />
            <Stat label="vs SPY" value={`${bt.excess_vs_spy >= 0 ? '+' : ''}${bt.excess_vs_spy.toFixed(1)}%`}
              good={bt.excess_vs_spy > 0} />
          </div>

          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={bt.curve} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.3} />
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: 'var(--text-secondary)' }}
                  stroke="var(--border)" minTickGap={40} />
                <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 10, fill: 'var(--text-secondary)' }}
                  stroke="var(--border)" width={44} />
                <Tooltip contentStyle={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
                  formatter={(v: number) => `${v.toFixed(1)}%`} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="strategy" stroke="#22c55e" dot={false} strokeWidth={2} name="Strategy" />
                <Line type="monotone" dataKey="spy" stroke="#60a5fa" dot={false} strokeWidth={1.5} name="SPY" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="flex flex-wrap gap-3 text-xs text-text-secondary">
            <span>{bt.start} → {bt.end} · {bt.rebalances} weekly rebalances</span>
            <span>·</span>
            <span>By year: {bt.yearly.map((y) => `${y.year} ${y.strategy >= 0 ? '+' : ''}${y.strategy.toFixed(0)}%`).join('  ')}</span>
          </div>
          <div className="rounded border border-border bg-bg px-3 py-2 text-sm">
            <span className="text-[10px] uppercase tracking-wide text-text-secondary">Current holdings: </span>
            <span className="font-mono">{bt.current_holdings.join(', ')}</span>
          </div>
        </div>
      )}
    </div>
  );
}
