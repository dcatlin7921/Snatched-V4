const { test, expect } = require('@playwright/test');

test.describe('Snatched public pages — post-monetization polish', () => {

  test('upload page requires authentication', async ({ page }) => {
    const response = await page.goto('/upload');
    // Should redirect to login (302 chain ends at /login)
    expect(page.url()).toContain('/login');
  });

  test('landing page hero has scan-first CTA', async ({ page }) => {
    await page.goto('/');
    // The primary CTA button should reference the free scan
    const heroCta = page.locator('a.btn-primary', { hasText: /scan your export/i });
    await expect(heroCta).toBeVisible();
    await expect(heroCta).toHaveAttribute('href', '/upload');
  });

  test('landing page How It Works has new monetization steps', async ({ page }) => {
    await page.goto('/');
    // Step 3 should be "Choose Your Package" (not old "We Process")
    const chooseStep = page.locator('.step-item', { hasText: /Choose.*Package/i });
    await expect(chooseStep).toBeVisible();
    // Step 2 should mention scanning
    const scanStep = page.locator('.step-item', { hasText: /Upload.*Scan/i });
    await expect(scanStep).toBeVisible();
  });

  test('landing page has no console errors', async ({ page }) => {
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/');
    // Wait for page to settle
    await page.waitForTimeout(1000);
    expect(errors).toEqual([]);
  });

  test('landing page footer CTA has scan-first language', async ({ page }) => {
    await page.goto('/');
    const footerCta = page.locator('.cta-card-landing');
    await expect(footerCta).toContainText(/see what.*export.*free/i);
    const footerBtn = footerCta.locator('a.btn-primary');
    await expect(footerBtn).toContainText(/scan free/i);
  });

  test('landing page pricing hint is visible', async ({ page }) => {
    await page.goto('/');
    // The pricing line below the hero CTA
    const pricingHint = page.locator('text=GPS & full archive from $4.99');
    await expect(pricingHint).toBeVisible();
  });
});
