/** @type {import('tailwindcss').Config} */
module.exports = {
  content: {
    relative: true,
    files: [
      "./app/**/*.{js,ts,jsx,tsx,mdx}",
      "./components/**/*.{js,ts,jsx,tsx,mdx}",
    ],
  },
  theme: {
    extend: {},
  },
  plugins: [],
}
