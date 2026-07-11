export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#0891B2",
          "on-primary": "#FFFFFF",
          secondary: "#22D3EE",
          accent: "#059669",
          bg: "#ECFEFF",
          fg: "#164E63",
          muted: "#E8F1F6",
          border: "#A5F3FC",
          destructive: "#DC2626",
          ring: "#0891B2",
        },
      },
      fontFamily: {
        display: ["Figtree", "system-ui", "sans-serif"],
        sans: ["Noto Sans", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
