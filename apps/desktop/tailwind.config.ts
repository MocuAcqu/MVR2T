import type { Config } from 'tailwindcss';

/**
 * Design tokens (Uber-inspired, black and white).
 * Source: independent analysis of uber.com (getdesign.md). Not an official Uber design system.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    // Breakpoints: 960 = Electron minimum window width
    screens: { sm: '600px', md: '768px', lg: '960px', xl: '1120px' },
    extend: {
      colors: {
        background: '#ffffff',
        foreground: '#000000',
        chip: '#efefef', // secondary / filter surface
        'hover-gray': '#e2e2e2',
        'hover-light': '#f3f3f3',
        'body-gray': '#4b4b4b', // secondary text (AA on white)
        'muted-gray': '#afafaf', // use on black only (fails AA on white)
      },
      fontFamily: {
        sans: [
          'Inter Variable',
          'Noto Sans TC Variable',
          'system-ui',
          'PingFang TC',
          'Microsoft JhengHei',
          'sans-serif',
        ],
      },
      fontSize: {
        display: ['3.25rem', { lineHeight: '1.23', fontWeight: '700' }], // 52
        h1: ['2.25rem', { lineHeight: '1.22', fontWeight: '700' }], // 36
        h2: ['1.5rem', { lineHeight: '1.33', fontWeight: '700' }], // 24
        h3: ['1.25rem', { lineHeight: '1.4', fontWeight: '700' }], // 20
        lg: ['1.125rem', { lineHeight: '1.33' }], // 18
        sm: ['0.875rem', { lineHeight: '1.43' }], // 14
        xs: ['0.75rem', { lineHeight: '1.67' }], // 12
      },
      borderRadius: { pill: '999px' }, // lg = 8px (cards, inputs), xl = 12px (featured)
      boxShadow: {
        card: '0 4px 16px 0 rgb(0 0 0 / 0.12)',
        raised: '0 4px 16px 0 rgb(0 0 0 / 0.16)',
        float: '0 2px 8px 0 rgb(0 0 0 / 0.16)',
        press: 'inset 0 0 0 999px rgb(0 0 0 / 0.08)',
      },
      // 不確定進度的進度條（例如後端正在檢查檔案）
      keyframes: {
        indeterminate: { '0%': { left: '-33%' }, '100%': { left: '100%' } },
      },
      animation: { indeterminate: 'indeterminate 1.2s ease-in-out infinite' },
    },
  },
  plugins: [],
} satisfies Config;
