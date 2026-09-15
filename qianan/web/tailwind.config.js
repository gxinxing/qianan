/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Shared neutral palette: matches the conversation workspace.
        brand: {
          50: "#f4f5f0",
          100: "#e9ece2",
          200: "#d6dbcc",
          300: "#bdc4b1",
          400: "#939b86",
          500: "#777f6a",
          600: "#5e6752",
          700: "#414638",
          800: "#272824",
          900: "#20211e",
          950: "#181916",
          DEFAULT: "#272824",
        },
        ink: {
          50: "#f7f7f5",
          100: "#edede9",
          200: "#deded9",
          300: "#c2c2bb",
          400: "#858580",
          500: "#73736c",
          600: "#64645e",
          700: "#51514b",
          800: "#3c3c37",
          900: "#252525",
          950: "#191918",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", "sans-serif"],
        display: ["var(--font-display)", "PingFang SC", "Noto Sans SC", "sans-serif"],
        mono: ["var(--font-mono)", "SF Mono", "ui-monospace", "Menlo", "monospace"],
      },
      boxShadow: {
        xs: "0 1px 2px rgb(26 32 39 / 0.05)",
        sm: "0 1px 2px rgb(26 32 39 / 0.06), 0 1px 3px rgb(26 32 39 / 0.10)",
        md: "0 2px 4px rgb(26 32 39 / 0.06), 0 4px 8px rgb(26 32 39 / 0.10)",
        lg: "0 4px 8px rgb(26 32 39 / 0.06), 0 12px 24px rgb(26 32 39 / 0.14)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        "fade-up": "fade-up 300ms cubic-bezier(0.05, 0.7, 0.1, 1) both",
        "pulse-dot": "pulse-dot 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
