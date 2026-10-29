import type { Config } from "tailwindcss";
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: "#0B1B33", blue: "#1E3A5F", accent: "#2F6FB3",
        paper: "#F4F7FA", line: "#D5DDE7", ink: "#1C2733", muted: "#667385",
        go: "#0B7A4B", gobg: "#DDF3E7", watch: "#8A5300", watchbg: "#FFF0D1",
        no: "#B42318", nobg: "#FDE7E5",
      },
      fontFamily: { sans: ["-apple-system", "Segoe UI", "Inter", "Roboto", "Helvetica Neue", "Arial", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
