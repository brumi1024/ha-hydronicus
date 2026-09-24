import { defineConfig } from "vitest/config";

export default defineConfig({
  define: { HYDRONICUS_FRONTEND_VERSION: JSON.stringify("0.0.0-test") },
  test: {
    // Element-level tests render the real Lit elements in a DOM.
    environment: "happy-dom",
    include: ["test/**/*.test.ts"],
  },
});
