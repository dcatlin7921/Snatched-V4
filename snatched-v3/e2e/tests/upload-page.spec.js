const { test, expect } = require('@playwright/test');

test.describe('Upload page — simplified scan-first flow', () => {

  test('upload page loads without product selection', async ({ page }) => {
    await page.goto('/upload');

    // Should be on the upload page (not redirected to login)
    expect(page.url()).toContain('/upload');

    // Old product buttons should NOT exist
    await expect(page.locator('#btn-quick-rescue')).toHaveCount(0);
    await expect(page.locator('#btn-full-export')).toHaveCount(0);
    await expect(page.locator('#product-selection')).toHaveCount(0);

    // Old processing mode pills should NOT exist
    await expect(page.locator('#upload-options')).toHaveCount(0);
    await expect(page.locator('#mode-quick-rescue-radio')).toHaveCount(0);
  });

  test('upload zone is visible immediately', async ({ page }) => {
    await page.goto('/upload');

    // The drag-drop zone should be visible (not hidden behind product selection)
    const dropzone = page.locator('#dropzone');
    await expect(dropzone).toBeVisible();

    // Should contain the upload prompt text
    await expect(dropzone).toContainText(/Drop your Snapchat export/i);
  });

  test('upload button exists and is disabled until files selected', async ({ page }) => {
    await page.goto('/upload');

    const uploadBtn = page.locator('#btn-upload');
    await expect(uploadBtn).toBeVisible();
    await expect(uploadBtn).toBeDisabled();
    await expect(uploadBtn).toContainText('UPLOAD');
  });

  test('folder upload disclosure is accessible', async ({ page }) => {
    await page.goto('/upload');

    // The disclosure should exist with the new label
    const disclosure = page.locator('#advanced-upload-options summary');
    await expect(disclosure).toBeVisible();
    await expect(disclosure).toContainText(/unzipped.*folder/i);

    // Click to expand
    await disclosure.click();

    // ZIP/Folder toggle buttons should be visible
    await expect(page.locator('#mode-zip')).toBeVisible();
    await expect(page.locator('#mode-folder')).toBeVisible();
  });

  test('scan-first subtitle is visible', async ({ page }) => {
    await page.goto('/upload');

    // The subtitle should set expectations for scan-first flow
    const subtitle = page.locator('text=scan your data');
    await expect(subtitle).toBeVisible();
  });

  test('upload page has inline error banner (no alert dialogs)', async ({ page }) => {
    await page.goto('/upload');
    // Error banner exists in DOM but hidden
    const banner = page.locator('#upload-error-banner');
    await expect(banner).toHaveCount(1);
    // Should be hidden by default
    await expect(banner).toBeHidden();
  });

  test('upload page has no console errors', async ({ page }) => {
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });

    await page.goto('/upload');
    await page.waitForTimeout(1000);

    expect(errors).toEqual([]);
  });
});
