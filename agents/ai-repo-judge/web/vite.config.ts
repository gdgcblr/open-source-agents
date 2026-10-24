import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base "./" keeps every asset and data path relative, so the build works on GitHub Pages or any sub-path.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
});
