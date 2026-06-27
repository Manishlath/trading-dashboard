'use client';

import { useState, useCallback, useRef } from 'react';
import { api, type OptionChain, type OptionContract, type IVRank } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types & constants
// ---------------------------------------------------------------------------

type Side = 'all' | 'call' | 'put';

const IV_RANK_THRESHOLD = 50;   // highlight when HV rank > this
const PUT_DELTA_LO = -0.35;
const PUT_DELTA_HI = -0.25;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined) return '—';
  return v.toFixed(decimals);
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return `${(v * 100).toFixed(1)}%`;
}

function fmtVol(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

function isPutCandidate(c: OptionContract, hvRank: number): boolean {
  return (
    c.opt_type === 'put' &&
    c.delta !== null &&
    c.delta >= PUT_DELTA_LO &&
    c.delta <= PUT_DELTA_HI &&
    hvRank > IV_RANK_THRESHOLD
  );
}

// ---------------------------------------------------------------------------
// StatBadge
// ---------------------------------------------------------------------------

function StatBadge({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded px-3 py-1.5 text-center ${
        accent
          ? 'border border-amber-600/40 bg-amber-900/20'
          : 'border border-border bg-bg'
      }`}
    >
      <div className="text-[10px] uppercase tracking-wide text-text-secondary">{label}</div>
      <div className={`font-mono text-sm font-medium ${accent ? 'text-amber-400' : ''}`}>
        {value}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChainTable — butterfly layout: calls | strike | puts
// ---------------------------------------------------------------------------

function ChainTable({
  contracts,
  underlyingPrice,
  hvRank,
}: {
  contracts: OptionContract[];
  underlyingPrice: number;
  hvRank: number;
}) {
  // Group into rows by strike
  const byStrike = new Map<number, { call?: OptionContract; put?: OptionContract }>();
  for (const c of contracts) {
    const row = byStrike.get(c.strike) ?? {};
    row[c.opt_type] = c;
    byStrike.set(c.strike, row);
  }
  const strikes = Array.from(byStrike.keys()).sort((a, b) => a - b);

  // ATM = strike nearest to underlying
  const atm = strikes.length
    ? strikes.reduce((prev, cur) =>
        Math.abs(cur - underlyingPrice) < Math.abs(prev - underlyingPrice) ? cur : prev,
        strikes[0],
      )
    : null;

  const th = 'px-2 py-2 text-right text-[11px] font-normal uppercase tracking-wide text-text-secondary whitespace-nowrap';
  const td = 'px-2 py-1.5 text-right font-mono text-xs';

  return (
    <div className="overflow-x-auto rounded border border-border">
      <table className="w-full min-w-[860px] border-collapse">
        <thead>
          <tr className="border-b border-border bg-bg/60">
            {/* Call side */}
            <th className={th}>Δ</th>
            <th className={th}>IV</th>
            <th className={th}>θ</th>
            <th className={th}>Bid</th>
            <th className={th}>Ask</th>
            <th className={th}>Vol</th>
            <th className={th}>OI</th>
            {/* Centre */}
            <th className="px-3 py-2 text-center text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
              Strike
            </th>
            {/* Put side */}
            <th className={th}>Bid</th>
            <th className={th}>Ask</th>
            <th className={th}>IV</th>
            <th className={th}>Δ</th>
            <th className={th}>γ</th>
            <th className={th}>θ</th>
            <th className={th}>ν</th>
            <th className={th}>Vol</th>
            <th className={th}>OI</th>
          </tr>
        </thead>
        <tbody>
          {strikes.map((strike) => {
            const { call, put } = byStrike.get(strike)!;
            const isAtm = strike === atm;
            const hl = put ? isPutCandidate(put, hvRank) : false;

            return (
              <tr
                key={strike}
                className={`border-b border-border/40 ${
                  isAtm ? 'bg-surface' : 'hover:bg-surface/50'
                }`}
              >
                {/* Calls */}
                <td className={`${td} text-sky-400`}>{fmt(call?.delta)}</td>
                <td className={td}>{fmtPct(call?.iv)}</td>
                <td className={`${td} text-red-500/70`}>{fmt(call?.theta)}</td>
                <td className={td}>{fmt(call?.bid)}</td>
                <td className={td}>{fmt(call?.ask)}</td>
                <td className={`${td} text-text-secondary`}>{fmtVol(call?.volume)}</td>
                <td className={`${td} text-text-secondary`}>{fmtVol(call?.open_interest)}</td>

                {/* Strike */}
                <td className="px-3 py-1.5 text-center font-mono text-sm">
                  {isAtm && (
                    <span className="mr-1 text-[9px] font-semibold uppercase text-sky-400">
                      ATM
                    </span>
                  )}
                  <span className={isAtm ? 'text-text-primary font-medium' : 'text-text-secondary'}>
                    {Number.isInteger(strike) ? strike : strike.toFixed(2)}
                  </span>
                </td>

                {/* Puts */}
                <td className={`${td} ${hl ? 'bg-amber-900/25 font-semibold text-amber-300' : ''}`}>
                  {fmt(put?.bid)}
                </td>
                <td className={`${td} ${hl ? 'bg-amber-900/25 font-semibold text-amber-300' : ''}`}>
                  {fmt(put?.ask)}
                </td>
                <td className={`${td} ${hl ? 'bg-amber-900/25 text-amber-400' : ''}`}>
                  {fmtPct(put?.iv)}
                </td>
                <td
                  className={`${td} font-medium ${
                    hl ? 'bg-amber-900/25 text-amber-400' : 'text-rose-400'
                  }`}
                >
                  {fmt(put?.delta)}
                </td>
                <td className={`${td} ${hl ? 'bg-amber-900/25' : ''}`}>{fmt(put?.gamma, 4)}</td>
                <td className={`${td} text-red-500/70 ${hl ? 'bg-amber-900/25' : ''}`}>
                  {fmt(put?.theta)}
                </td>
                <td className={`${td} ${hl ? 'bg-amber-900/25' : ''}`}>{fmt(put?.vega)}</td>
                <td className={`${td} text-text-secondary ${hl ? 'bg-amber-900/25' : ''}`}>
                  {fmtVol(put?.volume)}
                </td>
                <td className={`${td} text-text-secondary ${hl ? 'bg-amber-900/25' : ''}`}>
                  {fmtVol(put?.open_interest)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {strikes.length === 0 && (
        <p className="py-8 text-center text-sm text-text-secondary">
          No contracts in this expiry — try another date or check the IBKR connection.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// OptionsDesk
// ---------------------------------------------------------------------------

export function OptionsDesk() {
  const [inputSymbol, setInputSymbol] = useState('NVDA');
  const [activeSymbol, setActiveSymbol] = useState('');
  const [chain, setChain] = useState<OptionChain | null>(null);
  const [ivRank, setIvRank] = useState<IVRank | null>(null);
  const [selectedExpiry, setSelectedExpiry] = useState('');
  const [side, setSide] = useState<Side>('all');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loadChain = useCallback(async (sym: string, exp?: string) => {
    if (!sym) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setLoading(true);
    setError(null);

    const [chainResult, ivResult] = await Promise.allSettled([
      api.chain(sym, exp),
      api.ivRank(sym),
    ]);

    if (chainResult.status === 'rejected') {
      setError(String(chainResult.reason?.message ?? 'Failed to load chain'));
      setLoading(false);
      return;
    }

    const c = chainResult.value;
    setChain(c);
    setActiveSymbol(sym);
    if (!exp) setSelectedExpiry(c.expiry);

    if (ivResult.status === 'fulfilled') setIvRank(ivResult.value);

    setLoading(false);
  }, []);

  const handleLoad = () => loadChain(inputSymbol.toUpperCase().trim());

  const handleExpiryChange = (e: string) => {
    setSelectedExpiry(e);
    loadChain(activeSymbol, e);
  };

  // Filter contracts by side tab
  const visible = chain
    ? side === 'all'
      ? chain.contracts
      : chain.contracts.filter((c) => c.opt_type === side)
    : [];

  const hvRank = ivRank?.hv_rank_52w ?? 0;
  const rankAccent = hvRank > IV_RANK_THRESHOLD;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-4 text-lg font-medium">Options desk</h2>

      {/* Symbol input */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          value={inputSymbol}
          onChange={(e) => setInputSymbol(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === 'Enter' && handleLoad()}
          className="w-28 rounded border border-border bg-bg px-3 py-1.5 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-text-secondary"
          placeholder="Symbol"
        />
        <button
          onClick={handleLoad}
          disabled={loading}
          className="rounded border border-border bg-bg px-4 py-1.5 text-sm transition-colors hover:bg-surface disabled:opacity-40"
        >
          {loading ? 'Loading…' : 'Load chain'}
        </button>
        {error && <span className="text-xs text-negative">{error}</span>}
      </div>

      {/* ── Chain loaded ── */}
      {chain && (
        <>
          {/* Stats */}
          <div className="mb-3 flex flex-wrap gap-2">
            <StatBadge label={chain.underlying} value={`$${chain.underlying_price.toFixed(2)}`} />
            <StatBadge label="Expiry" value={chain.expiry || '—'} />
            <StatBadge label="DTE" value={chain.days_to_expiry ? `${chain.days_to_expiry}d` : '—'} />
            {ivRank && (
              <>
                <StatBadge label="HV 30d" value={fmtPct(ivRank.current_hv30)} />
                <StatBadge
                  label="HV rank 52w"
                  value={`${hvRank.toFixed(0)}%`}
                  accent={rankAccent}
                />
                <StatBadge label="HV pct 52w" value={`${ivRank.hv_pct_52w.toFixed(0)}%`} />
              </>
            )}
          </div>

          {/* Controls */}
          <div className="mb-3 flex flex-wrap items-center gap-3">
            {chain.available_expiries.length > 0 && (
              <select
                value={selectedExpiry}
                onChange={(e) => handleExpiryChange(e.target.value)}
                className="rounded border border-border bg-bg px-2 py-1.5 font-mono text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-text-secondary"
              >
                {chain.available_expiries.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
            )}

            <div className="flex overflow-hidden rounded border border-border text-sm">
              {(['all', 'call', 'put'] as Side[]).map((s) => (
                <button
                  key={s}
                  onClick={() => setSide(s)}
                  className={`px-3 py-1.5 capitalize transition-colors ${
                    side === s
                      ? 'bg-text-secondary text-bg'
                      : 'bg-bg text-text-secondary hover:bg-surface'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>

            {rankAccent && (
              <span className="rounded border border-amber-600/40 bg-amber-900/20 px-2 py-1 text-xs text-amber-400">
                ⚡ HV rank elevated — put-sell candidates highlighted
              </span>
            )}
          </div>

          {/* Table */}
          {chain.contracts.length > 0 ? (
            <>
              <ChainTable
                contracts={visible}
                underlyingPrice={chain.underlying_price}
                hvRank={hvRank}
              />
              <p className="mt-2 text-[10px] text-text-secondary">
                Greeks from IB model · Amber = put Δ {PUT_DELTA_LO} to {PUT_DELTA_HI} with HV rank &gt;{IV_RANK_THRESHOLD}%
              </p>
            </>
          ) : (
            <div className="rounded border border-dashed border-border p-6 text-center text-sm text-text-secondary">
              <p>No contracts returned for <span className="font-mono">{chain.underlying}</span>.</p>
              <p className="mt-1 text-xs">Try a different expiry, or check the IBKR market-data subscription.</p>
            </div>
          )}
        </>
      )}

      {/* Empty state */}
      {!chain && !loading && (
        <div className="rounded border border-dashed border-border p-6 text-center text-sm text-text-secondary">
          Enter a symbol above and click <span className="font-mono text-text-primary">Load chain</span>.
        </div>
      )}
    </div>
  );
}
