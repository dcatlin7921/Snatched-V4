const { test, expect } = require('@playwright/test');

test.describe('Help page — scan-first flow steps', () => {

  test('help page loads and has export guide', async ({ page }) => {
    await page.goto('/help');
    expect(page.url()).toContain('/help');
    // Should have the Snapchat export guide sections
    await expect(page.locator('h2', { hasText: /Configure Your Export/i })).toBeVisible();
  });

  test('help page has updated How It Works with Choose Package step', async ({ page }) => {
    await page.goto('/help');
    const chooseStep = page.locator('.step-item', { hasText: /Choose.*Package/i });
    await expect(chooseStep).toBeVisible();
    const scanStep = page.locator('.step-item', { hasText: /Upload.*Scan/i });
    await expect(scanStep).toBeVisible();
  });

  test('help page has no stale product names', async ({ page }) => {
    await page.goto('/help');
    const body = await page.locator('body').textContent();
    expect(body).not.toContain('Quick Rescue');
    // "Full Export" in Snapchat context ("You want the full export") is OK — it refers to Snap's export, not our old product
    expect(body).not.toContain('Speed Run');
    expect(body).not.toContain('Power User');
  });

  test('help page has no console errors', async ({ page }) => {
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/help');
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
  });

  test('help page has data categories section', async ({ page }) => {
    await page.goto('/help');
    await expect(page.locator('h3', { hasText: /Data Categories/i })).toBeVisible();
    await expect(page.locator('strong', { hasText: /Check every single box/i })).toBeVisible();
  });

  test('help page footer CTA has scan-first language', async ({ page }) => {
    await page.goto('/help');
    const cta = page.locator('.cta-card-landing');
    await expect(cta).toContainText(/Got your export/i);
    await expect(cta.locator('a.btn-primary')).toContainText(/SCAN FREE/i);
  });

  test('page-load progress bar exists', async ({ page }) => {
    await page.goto('/help');
    // The CSS animation bar should exist in the DOM (fixed position, top of page)
    const bar = page.locator('[style*="page-load"]');
    await expect(bar).toHaveCount(1);
  });
});
