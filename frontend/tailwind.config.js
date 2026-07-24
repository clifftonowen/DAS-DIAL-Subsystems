export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#E91626",
          "primary-hover": "#C22933",
          "on-primary": "#FFFFFF",
          accent: "#F8B508",
          success: "#15803D",
          bg: "#FEF2F2",
          fg: "#000000",
          "fg-muted": "#6C6C6C",
          muted: "#F5F6F8",
          border: "#EEEEEE",
          destructive: "#78050D",
          ring: "#E91626",

          // --- DASHBOARD PROTOTYPE ADDITIONS (Step 2) ---
          // Informational blue + warm surface for alert cards
          info: "#2563EB",
          "surface-alt": "#FFF7ED",

          // Per-skill chart colours — one per cognitive dimension
          // Used by ProfileRadarChart.jsx, SkillBars.jsx, DeficiencyAlerts.jsx
          "chart-1": "#E91626", // Phonological Processing
          "chart-2": "#F8B508", // Decoding
          "chart-3": "#2563EB", // Spelling
          "chart-4": "#15803D", // Comprehension
          "chart-5": "#7C3AED", // Working Memory
          "chart-6": "#EC4899", // Executive Functioning
          "chart-7": "#F97316", // Visualisation
          // --- END DASHBOARD PROTOTYPE ADDITIONS ---
        },
      },
      fontFamily: {
        display: ["Poppins", "system-ui", "sans-serif"],
        sans: ["Poppins", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
