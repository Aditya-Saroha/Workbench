import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0F1214",
        surface: "#171B1E",
        surface2: "#1D2226",
        border: "#2A2F33",
        text: "#E8EAEB",
        muted: "#8B939A",
        amber: "#D4A054",
        sage: "#5B9279",
        brick: "#B85450",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        DEFAULT: "3px",
        sm: "2px",
        md: "4px",
      },
    },
  },
  plugins: [],
};
export default config;
