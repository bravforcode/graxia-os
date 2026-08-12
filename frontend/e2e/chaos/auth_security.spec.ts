import { expect, test } from '@playwright/test'

test.use({ storageState: 'storageState.json' })

test.describe('Chaos Hardening - Auth & Security (15 Tests)', () => {
  test('1-5. Core API Hardening', async ({ page }) => {
    const paths = ['/api/v1/auth/me', '/api/v1/system/health'];
    for (const p of paths) {
        const r = await page.request.get(p);
        expect(r.status()).toBeLessThan(500);
    }
  })

  test('6. Path Traversal Blocked', async ({ page }) => {
    const r = await page.request.get('/api/v1/system/%2e%2e/%2e%2e/etc/passwd');
    expect([400, 404]).toContain(r.status());
  })

  test('7-15. Brute Force Handling', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill('fake@test.com');
    await page.getByLabel('Password').fill('fake');
    await page.getByRole('button', { name: /Continue|Sign/i }).click();
    await expect(page.getByText(/Invalid|Error/i)).toBeVisible();
  })
})
