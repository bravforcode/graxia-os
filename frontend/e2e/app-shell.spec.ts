import { expect, test } from '@playwright/test'

// Use the pre-logged-in storageState from globalSetup
test.use({ storageState: 'storageState.json' })

test.describe('Graxia OS - Live Production E2E (No Mocks)', () => {
  const TEST_EMAIL = 'real-test@graxia.io'

  test('should verify already logged in and at root', async ({ page }) => {
    await page.goto('/')
    // Should NOT redirect to login because of storageState
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  })

  test('should navigate through all sidebar pages and verify live data', async ({ page }) => {
    await page.goto('/')
    
    const pages = [
      { name: 'Dashboard', url: '/', heading: 'Overview' },
      { name: 'Agents', url: '/agents', heading: 'Agents' },
      { name: 'Leads', url: '/leads', heading: 'Leads' },
      { name: 'Tasks', url: '/tasks', heading: 'Tasks and reminders' },
      { name: 'Inbox', url: '/emails', heading: 'Email inbox' },
      { name: 'Costs', url: '/costs', heading: 'Cost monitoring' },
      { name: 'Settings', url: '/settings', heading: 'System settings' }
    ]

    for (const p of pages) {
      if (p.name !== 'Dashboard') {
        await page.getByRole('link', { name: p.name, exact: false }).click()
      } else {
        await page.goto('/') 
      }

      await expect(page).toHaveURL(new RegExp(p.url))
      await expect(page.getByRole('heading', { name: p.heading, exact: false }).first()).toBeVisible()
    }
  })

  test('should sign out successfully', async ({ page }) => {
    await page.goto('/')
    const profileButton = page.getByRole('button').filter({ hasText: TEST_EMAIL })
    await profileButton.click()
    await page.getByRole('menuitem', { name: 'Log out' }).click()
    await expect(page).toHaveURL(/\/login$/)
  })

  test('should trigger Sentry error from backend', async ({ page }) => {
    const response = await page.request.get('/api/v1/system/debug-sentry')
    expect(response.status()).toBe(500)
    const text = await response.text()
    expect(text).toBeTruthy()
  })
})
