/** Tailwind 配置 —— 主题变量与 src/index.css 的 CSS 变量保持一致 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: 'var(--paper)',
        card: 'var(--card)',
        sunk: 'var(--sunk)',
        ink: { DEFAULT: 'var(--ink)', 2: 'var(--ink2)', 3: 'var(--ink3)', 4: 'var(--ink4)' },
        rule: { DEFAULT: 'var(--rule)', strong: 'var(--rule2)' },
        green: { DEFAULT: 'var(--green)', deep: 'var(--greenD)', wash: 'var(--greenW)' },
        proof: 'var(--proof)',
        warn: 'var(--warn)',
        ok: 'var(--ok)',
      },
      fontFamily: {
        serif: ['var(--serif)'],
        sans: ['var(--sans)'],
        mono: ['var(--mono)'],
      },
    },
  },
  plugins: [],
};
