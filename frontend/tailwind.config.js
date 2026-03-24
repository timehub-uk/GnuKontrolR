/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      animation: {
        'fade-in': 'fadeIn 0.15s ease-out',
        'slide-up': 'slideUp 0.2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      colors: {
        // ── Base surfaces ──────────────────────────────────────────────────────
        panel: {
          base:     '#070709',   // page background
          surface:  '#0c0c0f',   // sidebar, topbar
          card:     '#111113',   // cards, panels
          elevated: '#18181b',   // hover states, inner rows
          border:   '#1f1f23',   // card borders
          subtle:   '#27272a',   // dividers, sidebar border
          // legacy aliases (keep for pages not yet migrated)
          900: '#070709',
          800: '#0c0c0f',
          700: '#18181b',
          600: '#27272a',
          500: '#3f3f46',
        },
        // ── Text ──────────────────────────────────────────────────────────────
        ink: {
          primary:   '#fafafa',
          secondary: '#a1a1aa',
          muted:     '#52525b',
          faint:     '#71717a',
        },
        // ── Brand accent (indigo) ─────────────────────────────────────────────
        brand: {
          DEFAULT: '#6366f1',
          light:   '#a5b4fc',
          dark:    '#4f46e5',
          glow:    'rgba(99,102,241,0.20)',
          // legacy aliases
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        },
        // ── Violet ────────────────────────────────────────────────────────────
        violet: {
          DEFAULT: '#8b5cf6',
          light:   '#c4b5fd',
        },
        // ── Status ────────────────────────────────────────────────────────────
        ok:   { DEFAULT: '#10b981', light: '#6ee7b7' },
        warn: { DEFAULT: '#f59e0b', light: '#fcd34d' },
        bad:  { DEFAULT: '#ef4444', light: '#fca5a5' },
      },
    },
  },
  plugins: [],
};
