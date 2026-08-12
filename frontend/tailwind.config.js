/** Aviva Networx Brand Identity Guide v1.0 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy:    { DEFAULT: '#0D1B4B', mid: '#1A2E72', midnight: '#0A1229' },
        brand:   { DEFAULT: '#1A6FA8', networx: '#2589C8', sky: '#4BAADF' },
        teal:    '#00C9A7',
        pale:    '#A8D4EE',
        lightgrey: '#E8EEF6',
        midgrey: '#8FA3BF',
        steel:   '#5A739A',
      },
      fontFamily: {
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
        mono: ['"Space Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
