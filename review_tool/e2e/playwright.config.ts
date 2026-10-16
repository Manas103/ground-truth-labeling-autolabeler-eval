import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests",
  timeout: 30_000,
  use: {
    // Playwright's own bundled Chromium, headless; launched and closed by
    // this test only, never the user's installed browser (BUILDER.md
    // section 3a).
    browserName: "chromium",
    headless: true,
  },
});
