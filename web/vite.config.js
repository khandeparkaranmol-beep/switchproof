import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Base is relative so the built app also works when opened from a file server or subpath.
export default defineConfig({
  base: "./",
  plugins: [react()],
});
