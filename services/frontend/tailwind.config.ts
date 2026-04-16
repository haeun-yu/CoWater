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
      animation: {
        "slide-in-top": "slideInTop 0.3s ease-out",
        "slide-in-right": "slideInRight 0.3s ease-out",
        "fade-in": "fadeIn 0.3s ease-out",
        "pulse-slow": "pulseSlow 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "count-update": "countUpdate 0.4s ease-out",
      },
      keyframes: {
        slideInTop: {
          from: {
            opacity: "0",
            transform: "translateY(-10px)",
          },
          to: {
            opacity: "1",
            transform: "translateY(0)",
          },
        },
        slideInRight: {
          from: {
            opacity: "0",
            transform: "translateX(20px)",
          },
          to: {
            opacity: "1",
            transform: "translateX(0)",
          },
        },
        fadeIn: {
          from: {
            opacity: "0",
          },
          to: {
            opacity: "1",
          },
        },
        pulseSlow: {
          "0%, 100%": {
            opacity: "1",
          },
          "50%": {
            opacity: "0.5",
          },
        },
        countUpdate: {
          "0%": {
            opacity: "0.6",
          },
          "50%": {
            opacity: "1",
          },
          "100%": {
            opacity: "1",
          },
        },
      },
    },
  },
  plugins: [],
};

export default config;
