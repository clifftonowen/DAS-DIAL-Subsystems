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
