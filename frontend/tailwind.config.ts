import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        forge: {
          50: "#f7f9fc",
          100: "#eff6ff",
          200: "#bfdbfe",
          500: "#2563eb",
          700: "#1d4ed8",
          800: "#1e3a8a",
          900: "#172033",
        },
      },
    },
  },
  plugins: [],
};

export default config;
