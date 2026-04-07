const { test, expect } = require('@playwright/test');

test.describe('Settings page — account and monetization copy', () => {

  test('settings page loads with account heading', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('h1')).toContainText(/Account.*Settings/i);
  });

  test('settings page shows per-job pricing note', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('text=per-job')).toBeVisible();
    await expect(page.locator('text=no subscription')).toBeVisible();
  });

  test('settings page shows account stats', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('text=Username')).toBeVisible();
    await expect(page.locator('text=Member Since')).toBeVisible();
    await expect(page.locator('text=Total Jobs')).toBeVisible();
  });

  test('settings page has promo code section with updated copy', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('h2', { hasText: /Promo Code/i })).toBeVisible();
    // Should use monetization-neutral language, not "Pro features"
    const body = await page.locator('body').textContent();
    expect(body).not.toContain('unlock Pro features');
  });

  test('settings page has danger zone', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('text=Danger Zone')).toBeVisible();
    await expect(page.locator('text=DELETE ALL MY DATA')).toBeVisible();
  });

  test('settings nav highlights username', async ({ page }) => {
    await page.goto('/settings');
    const userNav = page.locator('a.nav-active[href="/settings"]');
    await expect(userNav).toBeVisible();
  });

  test('settings page has no console errors', async ({ page }) => {
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/settings');
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
  });
});
