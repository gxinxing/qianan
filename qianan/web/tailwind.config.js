/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 海洋深蓝品牌 ramp（由 #0f4c81 生成，contrast-verified）
        brand: {
          50: "#eef6ff",
          100: "#daeafc",
          200: "#bfd7f1",
          300: "#9ec2e7",
          400: "#79a9dc",
          500: "#5a93ce",
          600: "#427bb4",
          700: "#336393",
          800: "#2a5075",
          900: "#1f3a55",
          950: "#0e2033",
          DEFAULT: "#336393",
        },
        // 蓝调中性色（hue 250，替代默认 slate）
        ink: {
          50: "#f2f5fb",
          100: "#e3e8f0",
          200: "#cdd5e0",
          300: "#b4bfce",
          400: "#97a6bb",
          500: "#8090a8",
          600: "#65768d",
          700: "#546175",
          800: "#434e5d",
          900: "#313844",
          950: "#1a2027",
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
