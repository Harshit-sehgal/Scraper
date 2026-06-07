import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["**/*.test.js"],
    exclude: ["e2e/**", "node_modules/**"],
    globals: true,
  },
});
