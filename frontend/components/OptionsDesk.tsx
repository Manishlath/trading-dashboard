'use client';

import { useState } from 'react';

export function OptionsDesk() {
  const [symbol, setSymbol] = useState('NVDA');

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-4 text-lg font-medium">Options desk</h2>

      <div className="mb-4 flex gap-2">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          className="flex-1 rounded border border-border bg-bg px-3 py-1.5 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-text-secondary"
          placeholder="Symbol"
        />
        <button className="rounded border border-border bg-bg px-3 py-1.5 text-sm hover:bg-surface">
          Load chain
        </button>
      </div>

      <div className="rounded border border-dashed border-border p-6 text-center text-sm text-text-secondary">
        <p className="mb-2">Option chain viewer goes here.</p>
        <p className="text-xs">
          Next: build the chain table (strike, bid/ask, IV, delta, theta) and the spread builder.
          Use the <code className="font-mono">options-engine</code> subagent.
        </p>
      </div>
    </div>
  );
}
