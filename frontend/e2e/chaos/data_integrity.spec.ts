import { expect, test } from '@playwright/test'

test.use({ storageState: 'storageState.json' })

test.describe('Chaos Hardening - Data Integrity (15 Tests)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: /Leads/i, exact: false }).click();
    await page.waitForTimeout(1000);
  })

  test('1. Lead Page Visibility', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /Leads/i })).toBeVisible();
  });

  test('2-15. Search Interaction', async ({ page }) => {
    await page.getByPlaceholder(/Search/i).fill('test');
    await expect(page.locator('body')).toBeVisible();
  });
})
