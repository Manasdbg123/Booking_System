import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0f",
        surface: "#13131c",
        surface2: "#1b1b27",
        border: "#26263a",
        accent: {
          DEFAULT: "#8b5cf6",
          soft: "#a78bfa",
          glow: "#c4b5fd",
        },
        seat: {
          free: "#2dd4bf",
          held: "#f59e0b",
          sold: "#ef4444",
          mine: "#8b5cf6",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        sans: ["var(--font-sans)", "sans-serif"],
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.5rem",
      },
      boxShadow: {
        glow: "0 0 40px -10px rgba(139, 92, 246, 0.5)",
        card: "0 8px 30px rgba(0,0,0,0.4)",
      },
      backgroundImage: {
        "grid-fade": "radial-gradient(circle at top, rgba(139,92,246,0.15), transparent 60%)",
      },
    },
  },
  plugins: [],
};

export default config;
