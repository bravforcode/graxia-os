import { expect, test } from '@playwright/test'

import { createMockApiState, installApiMocks } from './support/apiMocks'

test.describe('Personal OS browser flows', () => {
  test('redirects unauthenticated operators from root to login', async ({ page }) => {
    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 401,
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ detail: 'Not authenticated' }),
      })
    })

    await page.goto('/')

    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  })

  test('logs in through the auth form and renders the dashboard shell', async ({ page }) => {
    const state = createMockApiState()
    await installApiMocks(page, state)

    await page.goto('/login')

    await page.getByLabel('Email').fill(state.user.email)
    await page.getByLabel('Password').fill('correct horse battery staple')
    await page.getByRole('button', { name: 'Sign in' }).click()

    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('heading', { name: 'Executive dashboard' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'AI Builder Fellowship', exact: true })).toBeVisible()
    await expect(page.getByText('Follow-up to AI Builder Fellowship')).toBeVisible()
    await expect(page.getByText(state.user.email)).toBeVisible()
    await expect(page.getByText('Opportunity queue')).toBeVisible()
    await expect(page.getByText('Runtime posture')).toBeVisible()

    expect(state.loginCalls).toBe(1)
  })

  test('restores an active session, submits a check-in, approves a draft, and signs out', async ({ page }) => {
    const state = createMockApiState()
    await installApiMocks(page, state)

    await page.goto('/')

    await expect(page.getByRole('heading', { name: 'Executive dashboard' })).toBeVisible()
    expect(state.authMeCalls).toBeGreaterThanOrEqual(1)

    await page.getByRole('button', { name: 'Update check-in' }).click()
    await expect(page.getByRole('dialog', { name: 'Update cognitive state' })).toBeVisible()

    await page.getByLabel('Energy (0-10)').fill('9')
    await page.getByLabel('Stress (0-10)').fill('2')
    await page.getByLabel('Hours this week').fill('28')
    await page.getByRole('button', { name: 'Save check-in' }).click()

    await expect(page.getByText('Cognitive check-in updated.')).toBeVisible()
    expect(state.checkinCalls).toBe(1)

    const draftCard = page.locator('article').filter({ hasText: 'Follow-up to AI Builder Fellowship' })
    await draftCard.getByRole('button', { name: 'Approve' }).click()

    await expect(page.getByText('Draft approved.')).toBeVisible()
    expect(state.approveDraftCalls).toBe(1)

    await page.getByRole('button', { name: 'Sign out' }).click()

    await expect(page).toHaveURL(/\/login$/)
    expect(state.logoutCalls).toBe(1)
  })
})
