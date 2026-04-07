/**
 * Snatched v3 — Authentication E2E Tests
 *
 * Tests: register, login, failed login, logout, protected page redirect
 */
import { test, expect } from '@playwright/test';

const TEST_USER = {
  username: 'auth_test_' + Date.now(),
  password: 'AuthTest123!secure',
};

test.describe('Authentication', () => {

  test('register a new account and land on dashboard', async ({ page }) => {
    await page.goto('/register');
    await expect(page.locator('#username')).toBeVisible();

    await page.fill('#username', TEST_USER.username);
    await page.fill('#password', TEST_USER.password);
    await page.fill('#confirm_password', TEST_USER.password);
    await page.locator('.auth-submit').click();

    await page.waitForURL(/\/(dashboard|upload)/, { timeout: 10_000 });
  });

  test('logout redirects to landing page', async ({ page }) => {
    // Login first
    await page.goto('/login');
    await page.fill('#username', TEST_USER.username);
    await page.fill('#password', TEST_USER.password);
    await page.locator('.auth-submit').click();
    await page.waitForURL(/\/(dashboard|upload)/, { timeout: 10_000 });

    // Now logout
    await page.goto('/logout');
    await page.waitForURL(/\/(login|\?)/, { timeout: 10_000 });

    // Should not be able to access protected pages
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/login/);
  });

  test('login with valid credentials', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('.auth-submit')).toBeVisible();

    await page.fill('#username', TEST_USER.username);
    await page.fill('#password', TEST_USER.password);
    await page.locator('.auth-submit').click();

    await page.waitForURL(/\/(dashboard|upload)/, { timeout: 10_000 });

    // Nav should show username and logout icon
    await expect(page.locator('.nav-user-link')).toBeVisible();
    await expect(page.locator('.nav-logout')).toBeVisible();
  });

  test('login with wrong password shows error', async ({ page }) => {
    await page.goto('/login');

    await page.fill('#username', TEST_USER.username);
    await page.fill('#password', 'WrongPassword999!');
    await page.locator('.auth-submit').click();

    // Should stay on login page with error
    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('.auth-error')).toBeVisible();
  });

  test('login with non-existent user shows error', async ({ page }) => {
    await page.goto('/login');

    await page.fill('#username', 'no_such_user_ever_' + Date.now());
    await page.fill('#password', 'DoesntMatter123!');
    await page.locator('.auth-submit').click();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.locator('.auth-error')).toBeVisible();
  });

  test('protected pages redirect to login', async ({ page }) => {
    // Not logged in — these should all redirect to /login
    const protectedPaths = ['/dashboard', '/upload', '/settings'];

    for (const path of protectedPaths) {
      await page.goto(path);
      await expect(page).toHaveURL(/\/login/, {
        timeout: 5_000,
      });
    }
  });

  test('register with mismatched passwords stays on page', async ({ page }) => {
    await page.goto('/register');

    await page.fill('#username', 'mismatch_test_' + Date.now());
    await page.fill('#password', 'Password123!');
    await page.fill('#confirm_password', 'DifferentPassword456!');
    await page.locator('.auth-submit').click();

    // Should stay on register with error
    await expect(page).toHaveURL(/\/register/);
    await expect(page.locator('.auth-error')).toBeVisible();
  });

  test('register with short password shows error', async ({ page }) => {
    await page.goto('/register');

    await page.fill('#username', 'short_pw_test_' + Date.now());
    await page.fill('#password', 'short');
    await page.fill('#confirm_password', 'short');
    await page.locator('.auth-submit').click();

    await expect(page).toHaveURL(/\/register/);
    await expect(page.locator('.auth-error')).toBeVisible();
  });

  test('register with duplicate username shows error', async ({ page }) => {
    await page.goto('/register');

    await page.fill('#username', TEST_USER.username); // Already registered above
    await page.fill('#password', TEST_USER.password);
    await page.fill('#confirm_password', TEST_USER.password);
    await page.locator('.auth-submit').click();

    await expect(page).toHaveURL(/\/register/);
    await expect(page.locator('.auth-error')).toBeVisible();
  });
});
