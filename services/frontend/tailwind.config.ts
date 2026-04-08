import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        // 해양 관제 색상 팔레트
        ocean: {
          950: "#020d1a",
          900: "#041428",
          800: "#082240",
          700: "#0d3360",
          600: "#164e8a",
          500: "#1d6ab8",
          400: "#2e8dd4",
          300: "#5aade0",
          200: "#93cded",
          100: "#cce6f7",
        },
        alert: {
          critical: "#ef4444",
          warning: "#f59e0b",
          info: "#3b82f6",
        },
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
