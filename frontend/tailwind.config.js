export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        brand: {
          // --- CRISP BRIGHT REFRESH (design direction 1d) ---
          // Brighter red identity on a cool, neutral ground. Every component reads
          // these tokens, so the whole app follows from this block.
          primary: "#FF2E45",
          "primary-hover": "#E01730",
          "on-primary": "#FFFFFF",
          accent: "#FFCA28",
          success: "#22A06B",
          bg: "#F6F7F9",
          fg: "#14161A",
          "fg-muted": "#6B727D",
          muted: "#F1F3F5",
          border: "#EAECEF",
          destructive: "#78050D",
          ring: "#FF2E45",

          // Welcome banner surface — pale rose, used by HeroBanner.jsx.
          // hero-accent tints the banner's decorative circles. It equals `primary`
          // in Crisp Bright but stays separate: the design's other directions
          // diverge (Coral pairs #F5323F with a green hero).
          "hero-bg": "#FFE0E3",
          "hero-text": "#14161A",
          "hero-accent": "#FF2E45",

          // --- DASHBOARD PROTOTYPE ADDITIONS (Step 2) ---
          // Informational blue + warm surface for alert cards
          info: "#2563EB",
          "surface-alt": "#FFF7ED",

          // Per-skill chart colours — one per cognitive dimension
          // Used by ProfileRadarChart.jsx, SkillBars.jsx, DeficiencyAlerts.jsx
          "chart-1": "#FF2E45", // Phonological Processing
          "chart-2": "#FFCA28", // Decoding
          "chart-3": "#2563EB", // Spelling
          "chart-4": "#22A06B", // Comprehension
          "chart-5": "#7C3AED", // Working Memory
          "chart-6": "#EC4899", // Executive Functioning
          "chart-7": "#F97316", // Visualisation
          // --- END DASHBOARD PROTOTYPE ADDITIONS ---
        },
      },
      fontFamily: {
        display: ["Poppins", "system-ui", "sans-serif"],
        sans: ["Poppins", "system-ui", "sans-serif"],
        // Long-form reading (generated activities). Poppins is a geometric display
        // face — fine for labels, tiring for paragraphs a therapist reads end to
        // end. System serifs only, so this costs no extra webfont request.
        reading: ["Charter", "Georgia", "Cambria", "Times New Roman", "serif"],
      },
    },
  },
  plugins: [],
};
