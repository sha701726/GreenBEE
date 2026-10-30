// Tailwind build config. CSS rebuild:  npm i -D tailwindcss@3.4.17 && npx tailwindcss -c tailwind.config.js -i static/css/tailwind.src.css -o static/css/tailwind.css --minify
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      screens: { xs: "420px" },
      colors: {
        ink: "#14181A",
        green: { DEFAULT: "#1E8449", dark: "#145A30", light: "#34C069" },
        charcoal: { DEFAULT: "#1C1F1D", light: "#3A403C" },
        cloth: "#F7F8F6"
      },
      fontFamily: { display: ["Poppins", "sans-serif"], body: ["Inter", "sans-serif"] }
    }
  }
};
