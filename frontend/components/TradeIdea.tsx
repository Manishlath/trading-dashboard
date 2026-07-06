'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid,
} from 'recharts';
import { api, type TradeIdea as TradeIdeaT } from '@/lib/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const usd = (v: number) =>
  `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

function Metric({ label, value, accent }: { label: string; value: string; accent?: 'good' | 'bad' }) {
  const tone =
    accent === 'good' ? 'text-green-400' : accent === 'bad' ? 'text-red-400' : '';
  return (
    <div className="rounded border border-border bg-bg px-3 py-2 text-center">
      <div className="text-[10px] uppercase tracking-wide text-text-secondary">{label}</div>
      <div className={`font-mono text-sm font-medium ${tone}`}>{value}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// P&L curve
// ---------------------------------------------------------------------------

function PnlChart({ idea }: { idea: TradeIdeaT }) {
  const data = idea.pnl_curve.map(([s, p]) => ({ s, p }));
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
          <defs>
            <linearGradient id="pnlPos" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22c55e" stopOpacity={0.5} />
              <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.3} />
          <XAxis
            dataKey="s"
            type="number"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(v) => v.toFixed(0)}
            tick={{ fontSize: 10, fill: 'var(--text-secondary)' }}
            stroke="var(--border)"
          />
          <YAxis
            tickFormatter={(v) => usd(v)}
            tick={{ fontSize: 10, fill: 'var(--text-secondary)' }}
            stroke="var(--border)"
            width={48}
          />
          <Tooltip
            formatter={(v: number) => [usd(v), 'P&L']}
            labelFormatter={(v: number) => `Underlying $${v.toFixed(2)}`}
            contentStyle={{
              background: 'var(--bg)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              fontSize: 12,
            }}
          />
          <ReferenceLine y={0} stroke="var(--text-secondary)" strokeWidth={1} />
          <ReferenceLine
            x={idea.underlying_price}
            stroke="#60a5fa"
            strokeDasharray="4 2"
            label={{ value: 'spot', fontSize: 9, fill: '#60a5fa', position: 'top' }}
          />
          {idea.breakevens.map((be) => (
            <ReferenceLine
              key={be}
              x={be}
              stroke="#f59e0b"
              strokeDasharray="2 2"
              label={{ value: 'BE', fontSize: 9, fill: '#f59e0b', position: 'insideTopRight' }}
            />
          ))}
          <Area type="monotone" dataKey="p" stroke="#22c55e" strokeWidth={2} fill="url(#pnlPos)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TradeIdea panel
// ---------------------------------------------------------------------------

export function TradeIdea({ requestedSymbol }: { requestedSymbol?: string } = {}) {
  const [symbol, setSymbol] = useState('NVDA');
  const [idea, setIdea] = useState<TradeIdeaT | null>(null);
  const [risk, setRisk] = useState('conservative');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generateFor = useCallback(async (raw: string) => {
    const sym = raw.trim().toUpperCase();
    if (!sym) return;
    setLoading(true);
    setError(null);
    try {
      setIdea(await api.tradeIdea(sym, undefined, risk));
    } catch (e) {
      setIdea(null);
      setError(e instanceof Error ? e.message : 'Failed to generate trade idea');
    } finally {
      setLoading(false);
    }
  }, [risk]);

  const generate = useCallback(() => generateFor(symbol), [generateFor, symbol]);

  // When a screener pick arrives, seed the input and auto-generate.
  useEffect(() => {
    if (requestedSymbol) {
      setSymbol(requestedSymbol);
      generateFor(requestedSymbol);
    }
  }, [requestedSymbol, generateFor]);

  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-medium">Trade idea</h2>
        <span className="text-[10px] uppercase tracking-wide text-text-secondary">
          read-only · no auto-submit
        </span>
      </div>

      <div className="mb-4 flex gap-2">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === 'Enter' && generate()}
          placeholder="Symbol"
          className="w-28 rounded border border-border bg-bg px-2 py-1.5 font-mono text-sm outline-none focus:border-text-secondary"
        />
        <select
          value={risk}
          onChange={(e) => setRisk(e.target.value)}
          className="rounded border border-border bg-bg px-2 py-1.5 text-sm outline-none focus:border-text-secondary"
        >
          <option value="conservative">Conservative · 30Δ</option>
          <option value="moderate">Moderate · 38Δ</option>
          <option value="aggressive">Aggressive · 45Δ ×2</option>
        </select>
        <button
          onClick={generate}
          disabled={loading}
          className="rounded border border-border bg-bg px-3 py-1.5 text-sm hover:border-text-secondary disabled:opacity-50"
        >
          {loading ? 'Generating…' : 'Generate idea'}
        </button>
      </div>

      {error && (
        <div className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {!idea && !error && (
        <div className="rounded border border-dashed border-border px-4 py-8 text-center text-sm text-text-secondary">
          Enter a symbol and click <span className="font-mono">Generate idea</span> for a
          defined-risk option structure.
        </div>
      )}

      {idea && (
        <div className="space-y-4">
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-base font-medium">{idea.strategy}</span>
              <span className="rounded bg-bg px-2 py-0.5 text-[10px] uppercase tracking-wide text-text-secondary">
                {idea.direction}
              </span>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-text-secondary">{idea.thesis}</p>
          </div>

          {/* Signals — valuation + chart rationale */}
          {idea.signals.length > 0 && (
            <div className="rounded border border-border bg-bg px-3 py-2">
              <div className="mb-1 text-[10px] uppercase tracking-wide text-text-secondary">
                Why this trade
              </div>
              <ul className="space-y-0.5 text-sm">
                {idea.signals.map((s, i) => (
                  <li key={i} className="flex gap-2 text-text-secondary">
                    <span className="text-text-secondary">·</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Legs */}
          <div className="overflow-hidden rounded border border-border">
            <table className="w-full text-sm">
              <thead className="bg-bg text-[10px] uppercase tracking-wide text-text-secondary">
                <tr>
                  <th className="px-3 py-1.5 text-left">Action</th>
                  <th className="px-3 py-1.5 text-right">Qty</th>
                  <th className="px-3 py-1.5 text-right">Strike</th>
                  <th className="px-3 py-1.5 text-left">Type</th>
                  <th className="px-3 py-1.5 text-right">Mid</th>
                  <th className="px-3 py-1.5 text-right">Δ</th>
                  <th className="px-3 py-1.5 text-right">Spread</th>
                  <th className="px-3 py-1.5 text-right">OI</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {idea.legs.map((l, i) => (
                  <tr key={i} className="border-t border-border">
                    <td
                      className={`px-3 py-1.5 font-medium ${
                        l.action === 'sell' ? 'text-red-400' : 'text-green-400'
                      }`}
                    >
                      {l.action.toUpperCase()}
                    </td>
                    <td className="px-3 py-1.5 text-right">{l.quantity}</td>
                    <td className="px-3 py-1.5 text-right">{l.strike}</td>
                    <td className="px-3 py-1.5">{l.opt_type}</td>
                    <td className="px-3 py-1.5 text-right">{l.mid_price.toFixed(2)}</td>
                    <td className="px-3 py-1.5 text-right">{l.delta?.toFixed(2) ?? '—'}</td>
                    <td
                      className={`px-3 py-1.5 text-right ${
                        l.spread_pct !== null && l.spread_pct > 0.1 ? 'text-amber-400' : ''
                      }`}
                    >
                      {l.spread_pct !== null ? `${(l.spread_pct * 100).toFixed(0)}%` : '—'}
                    </td>
                    <td className="px-3 py-1.5 text-right">{l.open_interest ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Liquidity */}
          <div
            className={`rounded border px-3 py-2 ${
              idea.liquidity_ok
                ? 'border-border bg-bg'
                : 'border-amber-600/40 bg-amber-900/20'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-wide text-text-secondary">
                Liquidity
              </span>
              <span
                className={`text-xs font-medium ${
                  idea.liquidity_ok ? 'text-green-400' : 'text-amber-400'
                }`}
              >
                {idea.liquidity_ok ? 'Good — tight spreads' : 'Marginal — mind the leakage'}
              </span>
            </div>
            <div className="mt-1 text-sm text-text-secondary">
              Est. cost to cross spreads on entry:{' '}
              <span className="font-mono">{usd(idea.est_slippage)}</span>
              {idea.net_credit > 0 && (
                <span className="font-mono">
                  {' '}
                  ({((idea.est_slippage / idea.net_credit) * 100).toFixed(0)}% of credit)
                </span>
              )}
            </div>
            {idea.liquidity_warnings.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-xs text-amber-300">
                {idea.liquidity_warnings.map((w, i) => (
                  <li key={i}>· {w}</li>
                ))}
              </ul>
            )}
          </div>

          {/* Metrics */}
          <div className="grid grid-cols-3 gap-2">
            <Metric label="Net credit" value={usd(idea.net_credit)} accent="good" />
            <Metric label="Max profit" value={usd(idea.max_profit)} accent="good" />
            <Metric label="Max loss" value={usd(idea.max_loss)} accent="bad" />
            <Metric label="Breakeven" value={`$${idea.breakevens[0]?.toFixed(2) ?? '—'}`} />
            <Metric label="Prob. profit" value={`${idea.prob_of_profit.toFixed(0)}%`} />
            <Metric label="Return / risk" value={`${(idea.return_on_risk * 100).toFixed(0)}%`} />
          </div>

          {/* P&L curve */}
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-text-secondary">
              P&L at expiry · {idea.expiry} ({idea.days_to_expiry}d) · IV rank{' '}
              {idea.iv_rank.toFixed(0)} · HV30 {(idea.hv30 * 100).toFixed(0)}%
            </div>
            <PnlChart idea={idea} />
          </div>
        </div>
      )}
    </div>
  );
}
