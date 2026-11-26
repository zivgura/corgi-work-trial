export type Role = 'broker' | 'customer'
export interface User { id: number; name: string; email: string; role: Role; customer_id: number | null }
export interface Customer { id: number; name: string; contact_name: string; email: string }
export interface Version { id: number; effective_date: string; recorded_at: string; recorded_by: string; reason: string; is_current: boolean }
export interface Coverage {
  id: number; code: string; name: string; limit: string; kind: string
  term_premium_cents: number; effective_date: string; earned_premium_cents: number
  covered_days: number; versions: Version[]
}
export interface PolicyDetail {
  id: number; number: string; status: 'active' | 'cancelled'
  start_date: string; end_date: string; term_days: number
  cancelled_on: string | null; cancel_reason: string | null
  customer: Customer; coverages: Coverage[]; balance_cents: number
  payment_status: 'pending' | 'succeeded' | 'failed' | 'canceled' | null
}
export interface PolicyRow {
  id: number; number: string; status: 'active' | 'cancelled'; start_date: string; end_date: string
  balance_cents: number; payment_status: PolicyDetail['payment_status']
  customer: Customer; coverage_names: string[]
}
export interface StatementRow {
  id: number; date: string; type: 'CHARGE' | 'ADJUSTMENT' | 'CREDIT' | 'PAYMENT' | 'REFUND'
  description: string; amount_cents: number; running_balance_cents: number
  explanation: string; calc: Record<string, unknown>
  action: { id: number; kind: string; summary: string; actor: string; note: string; at: string }
}
export interface Statement {
  policy_number: string; rows: StatementRow[]; balance_cents: number
  totals: { net_premium_cents: number; paid_cents: number; refunded_cents: number }
  payment_attempts: { id: number; status: string; amount_cents: number; failure_reason: string | null; provider: string; created_at: string }[]
}
export interface TimelineItem { id: number; kind: string; summary: string; actor: string; note: string; at: string }
export interface Payment { id: number; policy_id: number; status: 'pending' | 'succeeded' | 'failed' | 'canceled'; amount_cents: number; provider: string; provider_ref: string; failure_reason: string | null; refunded_cents: number }
export interface AppConfig {
  payment_provider: 'fake' | 'stripe'; stripe_publishable_key: string; email_provider: string
  catalog: Record<string, { name: string; kind: string; limits: Record<string, number> }>
}
export interface PreviewLine {
  coverage: string; effective_date: string; covered_days: number; term_days: number
  term_premium_cents: number; amount_cents: number; previously_booked_cents: number
  delta_cents: number; formula: string
}
export interface Preview {
  lines: PreviewLine[]; premium_change_cents: number; current_balance_cents: number
  new_balance_cents: number; refund_cents: number
}

const KEY = 'corgi-token'
export const tokenStore = {
  get(): string | null { try { return localStorage.getItem(KEY) } catch { return null } },
  set(t: string) { try { localStorage.setItem(KEY, t) } catch { /* private mode */ } },
  clear() { try { localStorage.removeItem(KEY) } catch { /* private mode */ } },
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const token = tokenStore.get()
  const res = await fetch(`/api${path}`, {
    method: init.method ?? (init.body ? 'POST' : 'GET'),
    headers: { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: init.body ? JSON.stringify(init.body) : undefined,
  })
  const text = await res.text()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let data: any = null
  try { data = text ? JSON.parse(text) : null } catch { /* non-JSON body, e.g. a proxy's plain-text 502 */ }
  if (!res.ok) {
    const detail = data?.detail
    const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: { loc?: string[]; msg: string }) => `${d.loc?.slice(-1)[0] ?? ''} ${d.msg}`).join('; ') : res.statusText
    if (res.status === 401) tokenStore.clear()
    throw new ApiError(msg, res.status)
  }
  return data as T
}
