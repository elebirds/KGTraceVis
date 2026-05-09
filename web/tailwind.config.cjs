/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        panel: "#0f172a",
        panelSoft: "#111827",
        line: "#243040",
        accent: "#14b8a6",
        accentSoft: "#0f766e",
      },
      boxShadow: {
        soft: "0 0 0 1px rgba(148, 163, 184, 0.10)",
      },
    },
  },
  plugins: [],
};
