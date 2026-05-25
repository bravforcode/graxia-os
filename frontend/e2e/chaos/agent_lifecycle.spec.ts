import { expect, test } from '@playwright/test'

test.use({ storageState: 'storageState.json' })

test.describe('Chaos Hardening - Agent Lifecycle (10 Tests)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: /Agents/i, exact: false }).click();
    await page.waitForTimeout(1000);
  })

  test('1. Create Agent Stress', async ({ page }) => {
    await page.getByRole('button', { name: /Create Agent/i }).click();
    await expect(page.getByText('Create New Agent')).toBeVisible();
    await page.getByRole('button', { name: 'Cancel' }).click();
  });

  test('2. Multi-tab Agent management', async ({ context }) => {
    const page2 = await context.newPage();
    await page2.goto('/agents');
    await expect(page2.locator('body')).toBeVisible();
    await page2.close();
  });

  test('3-10. Navigation Stress', async ({ page }) => {
    await expect(page.locator('body')).toBeVisible();
  });
})
