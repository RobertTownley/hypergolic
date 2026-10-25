import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(import.meta.dirname, "src"),
    },
  },
  test: {
    globals: true,
    // opts in with a `@vitest-environment jsdom` docblock.
    projects: [
      { extends: true, test: { name: "dom", environment: "jsdom", include: ["src/**/*.test.tsx"] } },
      { extends: true, test: { name: "node", environment: "node", include: ["src/**/*.test.ts"] } },
    ],
    pool: "vmThreads",
    vmMemoryLimit: "300Mb",
    setupFiles: ["./src/test/setup.ts"],
    reporters: ["agent"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/test/**",
        "src/**/*.test.{ts,tsx}",
        "src/vite-env.d.ts",
        "src/main.tsx",
      ],
      reporter: ["text", "text-summary"],
    },
  },
});
