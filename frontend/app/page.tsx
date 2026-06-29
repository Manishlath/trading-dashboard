'use client';

import { useState, useEffect } from 'react';
import { PortfolioMonitor } from '@/components/PortfolioMonitor';
import { OptionsDesk } from '@/components/OptionsDesk';
import { TradeIdea } from '@/components/TradeIdea';
import { Screener } from '@/components/Screener';
import { MomentumDesk } from '@/components/MomentumDesk';

export default function DashboardPage() {
  const [now, setNow] = useState<string>('');
  const [pickedSymbol, setPickedSymbol] = useState<string | undefined>();
  useEffect(() => {
    setNow(new Date().toLocaleString());
  }, []);

  return (
    <main className="mx-auto max-w-[1600px] p-6">
      <header className="mb-6 flex items-baseline justify-between">
        <h1 className="text-2xl font-medium">Trading Dashboard</h1>
        <span className="text-sm text-text-secondary">
          Connected to IBKR · {now}
        </span>
      </header>

      <div className="mb-6">
        <MomentumDesk />
      </div>

      <div className="mb-6">
        <Screener onPick={setPickedSymbol} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <section>
          <PortfolioMonitor />
        </section>
        <section className="space-y-6">
          <OptionsDesk />
          <TradeIdea requestedSymbol={pickedSymbol} />
        </section>
      </div>
    </main>
  );
}
