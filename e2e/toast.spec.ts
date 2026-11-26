import { expect, test } from '@playwright/test'

const toast = (page: import('@playwright/test').Page) => page.locator('[aria-live="polite"] [role="alert"]')

test('a rejected sign-in is a toast, not text inside the form', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill('nobody@corgi-demo.test')
  await page.getByLabel('Password').fill('wrong-password')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(toast(page)).toBeVisible()
  await expect(page.locator('form [role="alert"]')).toHaveCount(0)
  await toast(page).getByRole('button', { name: 'Dismiss' }).click()
  await expect(toast(page)).toHaveCount(0)
})

test('server down: plain-language toast instead of "Bad Gateway"', async ({ page }) => {
  await page.goto('/login')
  await page.route('**/api/auth/login', (r) => r.fulfill({ status: 502, contentType: 'text/plain', body: 'Bad Gateway' }))
  await page.getByLabel('Email').fill('broker@corgi-demo.test')
  await page.getByLabel('Password').fill('corgi-demo-broker')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(toast(page)).toContainText("couldn't reach the server")
  await expect(page.getByText('Bad Gateway')).toHaveCount(0)
})

test('network failure and uncaught errors still reach the user as toasts', async ({ page }) => {
  await page.goto('/login')
  await page.route('**/api/auth/login', (r) => r.abort())
  await page.getByLabel('Email').fill('broker@corgi-demo.test')
  await page.getByLabel('Password').fill('corgi-demo-broker')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(toast(page)).toContainText("couldn't reach the server")
  await page.evaluate(() => { Promise.reject(new Error('Unexpected failure in a background task')) })
  await expect(toast(page).filter({ hasText: 'Unexpected failure' })).toBeVisible()
})
