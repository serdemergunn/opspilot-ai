/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ['system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'] },
      colors: {
        navy: { 950: "#0b1424", 900: "#0f1b2e", 800: "#17263f", 700: "#22355a", 400: "#8da2c4", 300: "#b6c4dc" },
        page: "#f6f7f9",
        surface: "#fcfcfb",
        ink: { DEFAULT: "#0b0b0b", secondary: "#52514e", muted: "#6f6d68" },
        hairline: "#e1e0d9",
        series: { 1: "#2a78d6", 2: "#eb6834" },
        status: { critical: "#d03b3b", good: "#0ca30c" },
      },
    },
  },
  plugins: [],
};
