// tailwind.config.{ts,js} — extend with LitPilot tokens
module.exports = {
  theme: {
    extend: {
      colors: {
        ink:        '#0E1633',
        'ink-soft': '#1B2547',
        accent:     '#F26A1F',
        'accent-soft': '#FDE3D2',
        paper:      '#F6F4EE',
        line:       '#E4E1D8',
        muted:      '#8C92A8',
      },
      fontFamily: {
        sans: ['Geist', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['Geist Mono', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        app: '22px',
      },
    },
  },
};
