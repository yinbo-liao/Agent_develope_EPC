/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: '#003366', light: '#0066CC', accent: '#00A3E0' },
      },
    },
  },
  plugins: [],
};
