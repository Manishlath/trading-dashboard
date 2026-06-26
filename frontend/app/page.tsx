'use client';

import { PortfolioMonitor } from '@/components/PortfolioMonitor';
import { OptionsDesk } from '@/components/OptionsDesk';

export default function DashboardPage() {
  return (
    <main className="mx-auto max-w-[1600px] p-6">
      <header className="mb-6 flex items-baseline justify-between">
        <h1 className="text-2xl font-medium">Trading Dashboard</h1>
        <span className="text-sm text-text-secondary">
          Connected to IBKR · {new Date().toLocaleString()}
        </span>
      </header>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <section>
          <PortfolioMonitor />
        </section>
        <section>
          <OptionsDesk />
        </section>
      </div>
    </main>
  );
}
