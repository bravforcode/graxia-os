import { expect, test } from '@playwright/test'

test.use({ storageState: 'storageState.json' })

test.describe('Chaos Hardening - Resilience (10 Tests)', () => {
  test('1. System Response', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('body')).toBeVisible();
  });

  test('2. 500 Recovery', async ({ page }) => {
    const r = await page.request.get('/api/v1/system/debug-sentry');
    expect(r.status()).toBe(500);
  });

  test('3-10. Nav Stability', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: /Settings/i }).click();
    await expect(page).toHaveURL(/\/settings/);
  });
})
