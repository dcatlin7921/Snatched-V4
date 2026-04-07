const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 15000,
  use: {
    baseURL: 'http://127.0.0.1:8000',
    headless: true,
  },
  projects: [
    // Public pages — no auth needed
    {
      name: 'public',
      testMatch: /landing-and-auth|auth-pages|help-page|meta-seo/,
      use: { browserName: 'chromium' },
    },
    // Auth setup — runs before authenticated tests
    {
      name: 'setup',
      testMatch: /auth\.setup/,
      use: { browserName: 'chromium' },
    },
    // Authenticated tests — depend on setup
    {
      name: 'authenticated',
      testMatch: /upload-page|error-pages|dashboard|settings-page/,
      use: {
        browserName: 'chromium',
        storageState: '.auth-state.json',
      },
      dependencies: ['setup'],
    },
  ],
});
