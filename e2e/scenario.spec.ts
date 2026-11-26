import { expect, test, type Page } from '@playwright/test'

const shot = (page: Page, name: string) => page.screenshot({ path: `screenshots/${name}.png`, fullPage: true })

async function signIn(page: Page, email: string, password: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.waitForURL(/\/(broker|portal)/)
}
async function signOut(page: Page) { await page.getByRole('button', { name: 'Sign out' }).click(); await expect(page).toHaveURL(/login/) }

async function pay(page: Page, card: 'succeed' | 'decline') {
  await page.getByRole('button', { name: /^Pay \$/ }).click()
  await expect(page.getByText('Payment pending').first()).toBeVisible()
  await page.getByRole('radio').nth(card === 'succeed' ? 0 : 1).check()
  await page.getByRole('button', { name: 'Submit payment' }).click()
}

test('headline scenario: issue → pay → add coverage → pay → correct date → customer sees it → cancel/refund', async ({ page }) => {
  // ---- broker creates a customer and issues a policy
  await signIn(page, 'broker@corgi-demo.test', 'corgi-demo-broker')
  await page.getByRole('link', { name: 'Customers' }).click()
  await page.getByRole('button', { name: 'New customer' }).click()
  await page.getByLabel('Company name').fill('Globex Robotics')
  await page.getByLabel('Contact name').fill('Gil Founder')
  await page.getByLabel('Contact email').fill('gil@globex-robotics.test')
  await page.getByRole('button', { name: 'Create customer' }).click()
  const creds = await page.locator('.mono').filter({ hasText: 'gil@globex-robotics.test' }).innerText()
  const tempPassword = creds.split('\n').pop()!.trim()
  await shot(page, '01-customer-created')
  await page.getByRole('button', { name: 'Done' }).click()

  await page.getByRole('link', { name: 'Issue policy' }).click()
  await page.getByLabel('Customer').selectOption({ label: 'Globex Robotics' })
  await page.getByLabel('Coverage starts').fill('2026-01-01')
  await page.getByLabel(/Expires on/).fill('2027-01-01')
  await expect(page.locator('.money', { hasText: '$2,400.00' }).first()).toBeVisible()
  await shot(page, '02-issue-policy')
  await page.getByRole('button', { name: 'Issue policy' }).click()
  await expect(page.getByRole('heading', { name: /CRG-/ })).toBeVisible()
  await expect(page.locator('.money', { hasText: '$2,400.00' }).first()).toBeVisible()
  const policyUrl = page.url()
  await shot(page, '03-policy-issued')
  await signOut(page)

  // ---- customer pays: declined card first (failed), then success
  await signIn(page, 'gil@globex-robotics.test', tempPassword)
  await page.getByText('CRG-').first().click()
  await pay(page, 'decline')
  await expect(page.getByText(/Payment failed: .*declined/)).toBeVisible()
  await shot(page, '04-payment-failed')
  await page.getByRole('radio').nth(0).check() // retry with the approved test card
  await page.getByRole('button', { name: 'Submit payment' }).click()
  await expect(page.getByText(/successful. Thank you/)).toBeVisible()
  await shot(page, '05-payment-succeeded')
  await signOut(page)

  // ---- broker adds Tech E&O mid-term effective Mar 1 -> $3,060.00
  await signIn(page, 'broker@corgi-demo.test', 'corgi-demo-broker')
  await page.goto(policyUrl)
  await page.getByRole('button', { name: 'Add coverage' }).click()
  await page.getByRole('dialog').locator('select').first().selectOption({ label: 'Tech E&O' })
  await page.getByLabel('Takes effect on').fill('2026-03-01')
  await expect(page.getByText('306/365 days').first()).toBeVisible()
  await expect(page.getByText('+$3,060.00').first()).toBeVisible()
  await shot(page, '06-add-coverage-preview')
  await page.getByRole('dialog').getByRole('button', { name: 'Add coverage' }).click()
  await expect(page.getByText('$3,060.00').first()).toBeVisible()
  await signOut(page)

  await signIn(page, 'gil@globex-robotics.test', tempPassword)
  await page.getByText('CRG-').first().click()
  await pay(page, 'succeed')
  await expect(page.getByText(/successful. Thank you/)).toBeVisible()
  await signOut(page)

  // ---- THE SCENARIO: broker corrects the rider's effective date to Feb 22
  await signIn(page, 'broker@corgi-demo.test', 'corgi-demo-broker')
  await page.goto(policyUrl)
  await page.getByRole('button', { name: 'Correct start date' }).nth(1).click()
  await page.getByLabel('Actual effective date').fill('2026-02-22')
  await page.getByLabel(/Reason/).fill('Binder confirms cover began Feb 22')
  await expect(page.getByText('313/365 days').first()).toBeVisible()
  await expect(page.getByText('+$70.00').first()).toBeVisible()
  await shot(page, '07-correction-preview')
  await page.getByRole('button', { name: 'Apply correction' }).click()
  await expect(page.getByText('Amount due').first()).toBeVisible()
  await expect(page.locator('.money', { hasText: '$70.00' }).first()).toBeVisible()
  await page.getByText('Correction').first().click()
  await shot(page, '08-broker-after-correction')
  await signOut(page)

  // ---- customer sees: original charge + correction, the reason, and $70.00 due
  await signIn(page, 'gil@globex-robotics.test', tempPassword)
  await page.getByText('CRG-').first().click()
  await expect(page.getByText('We corrected the start date of your Tech E&O')).toBeVisible()
  await expect(page.getByText('$3,060.00').first()).toBeVisible()
  await page.getByRole('row', { name: /Correction/ }).click()
  await expect(page.getByText(/Effective date corrected Mar 1, 2026 → Feb 22, 2026/)).toBeVisible()
  await shot(page, '09-customer-statement')
  await pay(page, 'succeed')
  await expect(page.getByText(/successful. Thank you/)).toBeVisible()
  await signOut(page)

  // ---- broker cancels effective Jul 1: pro-rata refund
  await signIn(page, 'broker@corgi-demo.test', 'corgi-demo-broker')
  await page.goto(policyUrl)
  await page.getByRole('button', { name: 'Cancel policy' }).click()
  await page.getByLabel('Cancellation effective').fill('2026-07-01')
  await page.getByLabel('Reason').fill('Company wound down')
  await expect(page.getByText('Refund $3,049.86')).toBeVisible()
  await shot(page, '10-cancel-preview')
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel policy' }).click()
  await expect(page.getByText('Cancelled', { exact: true }).first()).toBeVisible()
  await page.getByRole('link', { name: 'Integrations' }).click()
  await shot(page, '11-integrations')
  await page.goto(policyUrl)
  await shot(page, '12-final-statement')
})
