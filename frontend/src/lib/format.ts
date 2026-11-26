export function usd(cents: number): string {
  const sign = cents < 0 ? '-' : ''
  const c = Math.abs(cents)
  return `${sign}$${Math.floor(c / 100).toLocaleString('en-US')}.${String(c % 100).padStart(2, '0')}`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Format an ISO date ("2026-03-01") or datetime without any timezone shifting. */
export function fdate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return `${MONTHS[m - 1]} ${d}, ${y}`
}

export function fdatetime(iso: string): string {
  const t = iso.length > 10 ? iso.slice(11, 16) : ''
  return `${fdate(iso)}${t ? ` · ${t} UTC` : ''}`
}

export function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
