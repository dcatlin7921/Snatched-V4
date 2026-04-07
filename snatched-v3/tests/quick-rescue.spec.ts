/**
 * Snatched v3 — Quick Rescue End-to-End Test
 *
 * Flow: Register → Login → Upload ZIP → Processing → Download
 * Test files: /mnt/nas-pool/snapchat-input/test/*.zip
 */
import { test, expect, type Page } from '@playwright/test';
import path from 'path';
import fs from 'fs';

const BASE_URL = 'http://127.0.0.1:8000';
const TEST_DIR = '/mnt/nas-pool/snapchat-input/test';
const TEST_USER = {
  username: 'playwright_test_' + Date.now(),
  password: 'TestPass123!secure',
};

// Use the ZIP that has actual memories (memories/ dir + json/memories_history.json)
const TEST_ZIP = path.join(TEST_DIR, 'mydata~1772809395742.zip'); // 46MB — has media

test.describe('Quick Rescue Flow', () => {
  test.beforeAll(() => {
    // Verify test file exists
    if (!fs.existsSync(TEST_ZIP)) {
      throw new Error(`Test ZIP not found: ${TEST_ZIP}`);
    }
  });

  test('full quick rescue: register → upload → process → download', async ({ page }) => {
    // ─── Step 1: Register a new test user ───
    await test.step('Register new user', async () => {
      await page.goto('/register');
      await expect(page.locator('#username')).toBeVisible();

      await page.fill('#username', TEST_USER.username);
      await page.fill('#password', TEST_USER.password);
      await page.fill('#confirm_password', TEST_USER.password);
      await page.locator('.auth-submit').click();

      // Should redirect to dashboard or upload after registration
      await page.waitForURL(/\/(dashboard|upload)/, { timeout: 10_000 });
    });

    // ─── Step 2: Navigate to upload page ───
    await test.step('Navigate to upload page', async () => {
      await page.goto('/upload');
      await expect(page.locator('#btn-quick-rescue')).toBeVisible();
    });

    // ─── Step 3: Verify Quick Rescue is auto-selected ───
    await test.step('Quick Rescue is auto-selected', async () => {
      await expect(page.locator('#btn-quick-rescue')).toHaveClass(/upload-product-btn--active/);
    });

    // ─── Step 4: Upload ZIP file ───
    await test.step('Select ZIP file for upload', async () => {
      // Set the file on the hidden input
      const fileInput = page.locator('#fileInput');
      await fileInput.setInputFiles(TEST_ZIP);

      // File list should appear
      await expect(page.locator('#file-list-container')).toBeVisible({ timeout: 5_000 });

      // Verify file shows in the list
      const fileListBody = page.locator('#file-list-body');
      await expect(fileListBody.locator('tr')).toHaveCount(1);

      // Upload button should be enabled
      await expect(page.locator('#btn-upload')).toBeEnabled();
    });

    // ─── Step 5: Start upload ───
    let snatchedMemoriesUrl: string;
    await test.step('Click upload and wait for processing redirect', async () => {
      // Click the upload button
      await page.locator('#btn-upload').click();

      // Upload phase should appear
      await expect(page.locator('#phase-upload')).toBeVisible({ timeout: 10_000 });

      // Wait for upload to complete and redirect to /snatchedmemories/{jobId}
      // The 40MB file should upload in under 60s on localhost
      await page.waitForURL(/\/snatchedmemories\/\d+/, { timeout: 120_000 });
      snatchedMemoriesUrl = page.url();
      console.log(`  → Redirected to: ${snatchedMemoriesUrl}`);
    });

    // ─── Step 6: Processing pipeline ───
    await test.step('Wait for processing to complete', async () => {
      // Should see the processing UI
      const heroTitle = page.locator('#sm-hero-title');
      await expect(heroTitle).toBeVisible();

      // Wait for completion — hero title changes to "Snatched."
      // Processing a 40MB ZIP should take under 3 minutes
      await expect(heroTitle).toContainText('Snatched.', { timeout: 180_000 });
      console.log('  → Processing complete!');
    });

    // ─── Step 7: Verify download is available ───
    await test.step('Download link is available', async () => {
      // Reload to get server-rendered completed state
      await page.reload();
      await expect(page.locator('#sm-hero-title')).toContainText('Snatched.');
      await expect(page.locator('#sm-hero-sub')).toContainText('memories have been rescued');

      // Download button should be visible
      const downloadBtn = page.locator('.sm-part-btn--single, .sm-part-btn').first();
      await expect(downloadBtn).toBeVisible({ timeout: 10_000 });

      // Verify it has a download link
      const href = await downloadBtn.getAttribute('href');
      expect(href).toMatch(/\/api\/exports\/\d+\/download/);
      console.log(`  → Download link: ${href}`);
    });

    // ─── Step 8: Verify download works ───
    await test.step('Download ZIP file', async () => {
      const downloadBtn = page.locator('.sm-part-btn--single, .sm-part-btn').first();
      const href = await downloadBtn.getAttribute('href');

      // Trigger download via browser and intercept the response
      const [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 30_000 }),
        downloadBtn.click(),
      ]);

      // Verify download started successfully
      const failure = await download.failure();
      expect(failure).toBeNull();

      // Save and check file size
      const filePath = await download.path();
      expect(filePath).toBeTruthy();
      const stats = fs.statSync(filePath!);
      expect(stats.size).toBeGreaterThan(1000); // Real ZIP
      console.log(`  → Downloaded: ${download.suggestedFilename()} (${(stats.size / 1024 / 1024).toFixed(1)} MB)`);
    });
  });
});
