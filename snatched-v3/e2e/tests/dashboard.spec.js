const { test, expect } = require('@playwright/test');

test.describe('Dashboard — authenticated user view', () => {

  test('dashboard has correct page title', async ({ page }) => {
    await page.goto('/dashboard');
    expect(await page.title()).toMatch(/Dashboard.*SNATCHED/i);
  });

  test('dashboard loads with correct heading', async ({ page }) => {
    await page.goto('/dashboard');
    expect(page.url()).toContain('/dashboard');
    const heading = page.locator('h1');
    await expect(heading).toContainText(/Your Jobs/i);
  });

  test('dashboard has New Upload button linking to /upload', async ({ page }) => {
    await page.goto('/dashboard');
    // The header has a "New Upload" button (always visible, even with empty state)
    const newUploadBtn = page.locator('.section-header a.btn-primary[href="/upload"]');
    await expect(newUploadBtn).toBeVisible();
    await expect(newUploadBtn).toContainText(/New Upload/i);
  });

  test('dashboard shows stat cards', async ({ page }) => {
    await page.goto('/dashboard');
    const statsGrid = page.locator('.stats-grid');
    await expect(statsGrid).toBeVisible();
    // Should have an "Uploads" stat
    await expect(statsGrid).toContainText(/Uploads/i);
  });

  test('dashboard empty state has scan-first copy', async ({ page }) => {
    await page.goto('/dashboard');
    // The empty state (if visible) or the job list should be present
    const emptyState = page.locator('#empty-state');
    const jobList = page.locator('#active-jobs');
    // At least one should be visible
    const emptyVisible = await emptyState.isVisible().catch(() => false);
    const jobsVisible = await jobList.isVisible().catch(() => false);
    expect(emptyVisible || jobsVisible).toBeTruthy();

    // If empty state is showing, verify the scan-first copy
    if (emptyVisible) {
      await expect(emptyState).toContainText(/scan.*free/i);
    }
  });

  test('dashboard nav shows active state', async ({ page }) => {
    await page.goto('/dashboard');
    const activeNav = page.locator('a.nav-active[href="/dashboard"]');
    await expect(activeNav).toBeVisible();
  });

  test('dashboard has no console errors', async ({ page }) => {
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        const text = msg.text();
        if (text.includes('Failed to load resource')) return;
        errors.push(text);
      }
    });
    await page.goto('/dashboard');
    await page.waitForTimeout(1500);
    expect(errors).toEqual([]);
  });

  test('dashboard has no stale Quick Rescue or Full Export text', async ({ page }) => {
    await page.goto('/dashboard');
    const body = await page.locator('body').textContent();
    expect(body).not.toContain('Quick Rescue');
    expect(body).not.toContain('Full Export');
    expect(body).not.toContain('Speed Run');
    expect(body).not.toContain('Power User');
  });
});
