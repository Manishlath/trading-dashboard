import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: '#0a0a0a',
        surface: '#141414',
        border: '#262626',
        text: { primary: '#fafafa', secondary: '#a3a3a3' },
        positive: '#22c55e',
        negative: '#ef4444',
      },
    },
  },
  plugins: [],
};

export default config;
