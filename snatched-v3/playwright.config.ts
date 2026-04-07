// ⚠️ DEPRECATED — Old test config targeting tests/ with stale Quick Rescue / Full Export tests.
// Use e2e/ directory instead:  cd e2e && npx playwright test
// These old tests reference pre-monetization product names and WILL FAIL.
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 300_000,        // 5 min per test (uploads + processing take time)
  expect: { timeout: 30_000 },
  fullyParallel: false,     // Sequential — one job at a time
  retries: 0,
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: 'http://127.0.0.1:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
