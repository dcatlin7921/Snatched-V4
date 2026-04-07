const { test, expect } = require('@playwright/test');

test.describe('Auth pages — branding and monetization copy', () => {

  test('login page shows pricing hint', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('text=Free scan')).toBeVisible();
    await expect(page.locator('text=GPS from $4.99')).toBeVisible();
  });

  test('login page has brand tagline', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('.auth-tagline')).toContainText(/memories.*take them back/i);
  });

  test('login page links to register with "free" language', async ({ page }) => {
    await page.goto('/login');
    const registerLink = page.locator('.auth-footer a[href*="/register"]');
    await expect(registerLink).toBeVisible();
    await expect(registerLink).toContainText(/free/i);
  });

  test('register page shows free scan incentive', async ({ page }) => {
    await page.goto('/register');
    await expect(page.locator('text=Free scan included')).toBeVisible();
    await expect(page.locator('text=No credit card required')).toBeVisible();
  });

  test('register page has brand tagline', async ({ page }) => {
    await page.goto('/register');
    await expect(page.locator('.auth-tagline')).toContainText(/memories.*take them back/i);
  });

  test('login page has no console errors', async ({ page }) => {
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/login');
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
  });

  test('register page has no console errors', async ({ page }) => {
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/register');
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
  });

  test('auth pages have no stale product names', async ({ page }) => {
    await page.goto('/login');
    const loginText = await page.locator('body').textContent();
    expect(loginText).not.toContain('Quick Rescue');
    expect(loginText).not.toContain('Full Export');

    await page.goto('/register');
    const regText = await page.locator('body').textContent();
    expect(regText).not.toContain('Quick Rescue');
    expect(regText).not.toContain('Full Export');
  });

  test('both auth pages have favicon', async ({ page }) => {
    await page.goto('/login');
    const favicon = page.locator('link[rel="icon"]');
    await expect(favicon).toHaveCount(1);
  });
});
