'use client';

import { useState, useCallback } from 'react';
import { api, type ScreenCandidate } from '@/lib/api';

function pct(v: number | null): string {
  return v === null || v === undefined ? '—' : `${(v * 100).toFixed(0)}%`;
}
function num(v: number | null, d = 2): string {
  return v === null || v === undefined ? '—' : v.toFixed(d);
}

function biasTone(bias: string): string {
  if (bias === 'bullish') return 'text-green-400';
  if (bias === 'bearish') return 'text-red-400';
  return 'text-text-secondary';
}

export function Screener({ onPick }: { onPick: (symbol: string) => void }) {
  const [rows, setRows] = useState<ScreenCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.screen();
      setRows(res.candidates);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Screen failed');
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium">Screener</h2>
          <p className="text-xs text-text-secondary">
            Ranked by fundamentals + technicals · pick a leader to build an OTM premium strategy
          </p>
        </div>
        <button
          onClick={run}
          disabled={loading}
          className="rounded border border-border bg-bg px-3 py-1.5 text-sm hover:border-text-secondary disabled:opacity-50"
        >
          {loading ? 'Screening…' : 'Run screen'}
        </button>
      </div>

      {error && (
        <div className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {!rows.length && !error && (
        <div className="rounded border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
          Click <span className="font-mono">Run screen</span> to rank the watchlist. Screening pulls
          a year of history per name, so this takes a moment.
        </div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded border border-border">
          <table className="w-full text-sm">
            <thead className="bg-bg text-[10px] uppercase tracking-wide text-text-secondary">
              <tr>
                <th className="px-3 py-1.5 text-left">Symbol</th>
                <th className="px-3 py-1.5 text-right">Score</th>
                <th className="px-3 py-1.5 text-left">Bias</th>
                <th className="px-3 py-1.5 text-right">Price</th>
                <th className="px-3 py-1.5 text-left">Trend</th>
                <th className="px-3 py-1.5 text-right">RSI</th>
                <th className="px-3 py-1.5 text-right">PEG</th>
                <th className="px-3 py-1.5 text-right">Net M.</th>
                <th className="px-3 py-1.5 text-right">ROE</th>
                <th className="px-3 py-1.5 text-right">HV rk</th>
                <th className="px-3 py-1.5"></th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {rows.map((c) => (
                <tr key={c.symbol} className="border-t border-border hover:bg-bg/50">
                  <td className="px-3 py-1.5 font-medium">{c.symbol}</td>
                  <td className="px-3 py-1.5 text-right">{c.score.toFixed(1)}</td>
                  <td className={`px-3 py-1.5 ${biasTone(c.bias)}`}>{c.bias}</td>
                  <td className="px-3 py-1.5 text-right">{num(c.last_price)}</td>
                  <td className="px-3 py-1.5 text-text-secondary">{c.trend}</td>
                  <td className="px-3 py-1.5 text-right">{num(c.rsi14, 0)}</td>
                  <td className="px-3 py-1.5 text-right">{num(c.peg_ratio)}</td>
                  <td className="px-3 py-1.5 text-right">{pct(c.net_margin)}</td>
                  <td className="px-3 py-1.5 text-right">{pct(c.roe)}</td>
                  <td className="px-3 py-1.5 text-right">{num(c.hv_rank, 0)}</td>
                  <td className="px-3 py-1.5 text-right">
                    <button
                      onClick={() => onPick(c.symbol)}
                      className="rounded border border-border px-2 py-0.5 text-xs hover:border-text-secondary"
                    >
                      Strategy →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
