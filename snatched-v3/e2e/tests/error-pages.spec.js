const { test, expect } = require('@playwright/test');

test.describe('Error pages — styled error rendering', () => {

  test('404 on invalid configure job shows styled error', async ({ page }) => {
    await page.goto('/configure/99999');
    // Should show the themed error page, not raw JSON
    const container = page.locator('.error-container');
    await expect(container).toBeVisible();
    await expect(container).toContainText(/Not Found/i);
    await expect(container).toContainText(/Job not found/i);
    // Should have navigation links back
    await expect(page.locator('.error-container a[href="/"]')).toBeVisible();
    await expect(page.locator('.error-container a[href="/dashboard"]')).toBeVisible();
  });

  test('404 on invalid snatchedmemories job shows styled error', async ({ page }) => {
    await page.goto('/snatchedmemories/99999');
    const container = page.locator('.error-container');
    await expect(container).toBeVisible();
    await expect(container).toContainText(/Not Found/i);
  });

  test('error page has no JS console errors', async ({ page }) => {
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        const text = msg.text();
        // Ignore browser-generated network errors (expected for 404 pages)
        if (text.includes('Failed to load resource')) return;
        errors.push(text);
      }
    });
    await page.goto('/configure/99999');
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
  });

  test('API endpoints still return JSON for errors', async ({ request }) => {
    const resp = await request.get('/api/jobs/99999');
    expect(resp.status()).toBe(404);
    const body = await resp.json();
    expect(body.detail).toContain('not found');
  });

  test('error pages show authenticated nav and Dashboard highlight', async ({ page }) => {
    await page.goto('/configure/99999');
    // Error handler now passes auth context — should show Dashboard link in nav
    const dashNav = page.locator('a.nav-active[href="/dashboard"]');
    await expect(dashNav).toBeVisible();
    // Error card also has Home + Dashboard escape links
    await expect(page.locator('.error-container a[href="/"]')).toBeVisible();
    await expect(page.locator('.error-container a[href="/dashboard"]')).toBeVisible();
  });
});
