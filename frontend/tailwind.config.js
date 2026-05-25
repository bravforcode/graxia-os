/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#000000',
        foreground: '#ffffff',
        border: '#27272a', /* zinc-800 */
        muted: '#18181b', /* zinc-900 */
        primary: {
          DEFAULT: '#ffffff',
          foreground: '#000000',
        },
        secondary: {
          DEFAULT: '#27272a',
          foreground: '#ffffff',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        'vercel': '0 0 0 1px rgba(255,255,255,0.1), 0 2px 4px rgba(0,0,0,0.5)',
      }
    },
  },
  plugins: [],
}
