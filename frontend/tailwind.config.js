/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        podium: ['"FSP DEMO - PODIUM Sharp 4.11"', "system-ui", "sans-serif"],
        inter: ['"Inter"', "system-ui", "sans-serif"],
      },
      colors: {
        ink: "#0a0a0f",
        accent: "#6366f1",
      },
    },
  },
  plugins: [],
};
