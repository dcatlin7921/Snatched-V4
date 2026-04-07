const { test: setup } = require('@playwright/test');

// Register + login a test user and save auth state for other tests
setup('authenticate', async ({ page }) => {
  // Try to register (may already exist)
  await page.goto('/register');

  // Get CSRF token from cookie
  const cookies = await page.context().cookies();
  const csrf = cookies.find(c => c.name === 'csrf_token');

  await page.fill('#username', 'e2etest');
  await page.fill('#email', 'e2e@test.local');
  await page.fill('#password', 'testpass123');
  await page.fill('#confirm_password', 'testpass123');
  await page.click('button[type="submit"]');

  // If registration succeeded, we're redirected to /upload
  // If user exists, we get an error — fall through to login
  if (page.url().includes('/register')) {
    // Registration failed (user exists) — login instead
    await page.goto('/login');
    await page.fill('#username', 'e2etest');
    await page.fill('#password', 'testpass123');
    await page.click('button[type="submit"]');
  }

  // Should be on /upload or /dashboard now
  await page.waitForURL(/\/(upload|dashboard)/);

  // Save auth state
  await page.context().storageState({ path: '.auth-state.json' });
});
