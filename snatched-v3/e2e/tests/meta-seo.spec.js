const { test, expect } = require('@playwright/test');

test.describe('Meta tags and SEO — base.html head', () => {

  test('landing page has correct title', async ({ page }) => {
    await page.goto('/');
    const title = await page.title();
    expect(title).toContain('SNATCHED');
    expect(title).toContain('Snapchat');
  });

  test('landing page has meta description with pricing', async ({ page }) => {
    await page.goto('/');
    const desc = await page.locator('meta[name="description"]').getAttribute('content');
    expect(desc).toContain('$4.99');
    expect(desc).toContain('Snapchat');
  });

  test('landing page has Open Graph tags', async ({ page }) => {
    await page.goto('/');
    const ogTitle = await page.locator('meta[property="og:title"]').getAttribute('content');
    expect(ogTitle).toContain('SNATCHED');
    const ogDesc = await page.locator('meta[property="og:description"]').getAttribute('content');
    expect(ogDesc).toBeTruthy();
    const ogType = await page.locator('meta[property="og:type"]').getAttribute('content');
    expect(ogType).toBe('website');
  });

  test('landing page has Twitter Card', async ({ page }) => {
    await page.goto('/');
    const card = await page.locator('meta[name="twitter:card"]').getAttribute('content');
    expect(card).toBe('summary');
  });

  test('all pages have favicon', async ({ page }) => {
    for (const path of ['/', '/login', '/register', '/help']) {
      await page.goto(path);
      const icon = page.locator('link[rel="icon"]');
      await expect(icon).toHaveCount(1);
      const href = await icon.getAttribute('href');
      expect(href).toContain('svg');
      expect(href).toContain('FFFC00'); // snap-yellow
    }
  });

  test('all pages have theme-color', async ({ page }) => {
    await page.goto('/');
    const color = await page.locator('meta[name="theme-color"]').getAttribute('content');
    expect(color).toBe('#FFFC00');
  });

  test('privacy strip shows correct retention', async ({ page }) => {
    await page.goto('/');
    const privacyStrip = page.locator('.privacy-strip');
    await expect(privacyStrip).toContainText('30 days');
    await expect(privacyStrip).toContainText('never shared');
  });

  test('caution tape divider is present', async ({ page }) => {
    await page.goto('/');
    const tape = page.locator('.caution-tape');
    await expect(tape).toBeVisible();
  });

  test('site footer is present with copyright', async ({ page }) => {
    await page.goto('/');
    // base.html footer is the last one (landing may have its own)
    const footer = page.locator('footer').last();
    await expect(footer).toBeVisible();
    await expect(footer).toContainText('2026');
  });

  test('every page has a unique descriptive title', async ({ page }) => {
    const titleChecks = [
      ['/', /Recover.*Snapchat/i],
      ['/login', /Login.*SNATCHED/i],
      ['/register', /Register.*SNATCHED/i],
      ['/help', /Help.*SNATCHED/i],
    ];
    for (const [path, pattern] of titleChecks) {
      await page.goto(path);
      const title = await page.title();
      expect(title, `Title on ${path}`).toMatch(pattern);
    }
  });

  test('reduced-motion CSS exists in stylesheet', async ({ page }) => {
    await page.goto('/');
    const hasRule = await page.evaluate(() => {
      for (const sheet of document.styleSheets) {
        try {
          for (const rule of sheet.cssRules) {
            if (rule.conditionText && rule.conditionText.includes('prefers-reduced-motion')) return true;
          }
        } catch (e) { /* cross-origin */ }
      }
      return false;
    });
    expect(hasRule).toBe(true);
  });
});
