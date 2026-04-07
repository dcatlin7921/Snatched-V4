/**
 * Snatched v3 — Landing Page E2E Tests
 *
 * Tests: hero, countdown, social proof, privacy strip, nav, CTAs
 */
import { test, expect } from '@playwright/test';

test.describe('Landing Page', () => {

  test('hero section renders with headline and CTA', async ({ page }) => {
    await page.goto('/');

    // Hero headline
    const hero = page.locator('.hero-h1');
    await expect(hero).toBeVisible();
    await expect(hero).toContainText('Snapchat');

    // Hero subtitle
    await expect(page.locator('.hero-subtitle')).toBeVisible();

    // Primary CTA button
    const ctaBtn = page.locator('.hero-cta .btn-primary');
    await expect(ctaBtn).toBeVisible();
    await expect(ctaBtn).toHaveAttribute('href', '/upload');
    await expect(ctaBtn).toContainText('RESCUE YOUR MEMORIES');
  });

  test('countdown timer renders and ticks', async ({ page }) => {
    await page.goto('/');

    // Countdown section visible
    await expect(page.locator('.countdown-section')).toBeVisible();

    // Target label
    await expect(page.locator('.countdown-target')).toContainText('September 1, 2026');

    // Wait for JS to populate values (replace "---" placeholders)
    const daysEl = page.locator('#cd-days');
    await expect(daysEl).not.toHaveText('---', { timeout: 3_000 });

    // Values should be numeric
    const days = await daysEl.textContent();
    expect(Number(days)).toBeGreaterThan(0);

    const hours = await page.locator('#cd-hours').textContent();
    expect(Number(hours)).toBeGreaterThanOrEqual(0);
    expect(Number(hours)).toBeLessThanOrEqual(23);
  });

  test('social proof stats section renders', async ({ page }) => {
    await page.goto('/');

    // Trust stats section — may or may not be visible depending on data
    const trustSection = page.locator('.trust-section');
    const isVisible = await trustSection.isVisible();

    if (isVisible) {
      // Verify stat labels
      await expect(page.locator('.trust-stat-label').nth(0)).toContainText('Memories Rescued');
      await expect(page.locator('.trust-stat-label').nth(1)).toContainText('Locations Restored');
      await expect(page.locator('.trust-stat-label').nth(2)).toContainText('Users Served');

      // Values should be present
      const values = page.locator('.trust-stat-value');
      await expect(values).toHaveCount(3);
    }
    // If not visible, stats are all zero — that's valid
  });

  test('privacy strip always renders', async ({ page }) => {
    await page.goto('/');

    const privacyStrip = page.locator('.privacy-strip');
    await expect(privacyStrip).toBeVisible();

    // 3 privacy items
    const items = page.locator('.privacy-item');
    await expect(items).toHaveCount(3);

    // Check content
    await expect(items.nth(0)).toContainText('never shared');
    await expect(items.nth(1)).toContainText('7 days');
    await expect(items.nth(2)).toContainText('No tracking');
  });

  test('features section renders', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('.features-section')).toBeVisible();

    // "Capabilities" section label
    await expect(page.locator('.section-label-text').first()).toContainText('Capabilities');
  });

  test('how it works section renders', async ({ page }) => {
    await page.goto('/');

    // Second section label should be "How It Works"
    const labels = page.locator('.section-label-text');
    const count = await labels.count();
    let found = false;
    for (let i = 0; i < count; i++) {
      const text = await labels.nth(i).textContent();
      if (text?.includes('How It Works')) {
        found = true;
        break;
      }
    }
    expect(found).toBe(true);
  });

  test('bottom CTA card renders with urgency message', async ({ page }) => {
    await page.goto('/');

    const ctaCard = page.locator('.cta-card-landing');
    await expect(ctaCard).toBeVisible();
    await expect(page.locator('.cta-urgency')).toContainText('September 2026');

    const startBtn = ctaCard.locator('.btn-primary');
    await expect(startBtn).toContainText('START NOW');
    await expect(startBtn).toHaveAttribute('href', '/upload');
  });

  test('nav shows login/signup when not authenticated', async ({ page }) => {
    await page.goto('/');

    // Should see Log In and Sign Up links
    await expect(page.locator('.nav-auth-link')).toBeVisible();
    await expect(page.locator('.nav-signup-btn')).toBeVisible();

    // Should NOT see logout or username
    await expect(page.locator('.nav-logout')).not.toBeVisible();
    await expect(page.locator('.nav-user-link')).not.toBeVisible();
  });

  test('nav login link goes to login page', async ({ page }) => {
    await page.goto('/');

    await page.locator('.nav-auth-link').click();
    await expect(page).toHaveURL(/\/login/);
  });

  test('nav signup link goes to register page', async ({ page }) => {
    await page.goto('/');

    await page.locator('.nav-signup-btn').click();
    await expect(page).toHaveURL(/\/register/);
  });

  test('hero CTA links to upload (redirects to login if not authed)', async ({ page }) => {
    await page.goto('/');

    await page.locator('.hero-cta .btn-primary').click();
    // /upload is protected, should redirect to login
    await expect(page).toHaveURL(/\/login/);
  });

  test('page has correct title', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Snatched/i);
  });
});
