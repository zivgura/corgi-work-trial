import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api, type Customer, type PolicyDetail } from '../../lib/api'
import { useAuth } from '../../auth'
import { today, usd, fdate } from '../../lib/format'
import { Button, Card, ErrorNote, Field, Input, PageTitle, Select } from '../../components/ui'

function addYear(iso: string) { const [y, m, d] = iso.split('-').map(Number); return `${y + 1}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}` }
function days(a: string, b: string) { return Math.round((Date.parse(b) - Date.parse(a)) / 86400000) }
const roundDiv = (n: number, d: number) => Math.floor((2 * n + d) / (2 * d)) // same half-up rule as the server

export default function IssuePolicy() {
  const { config } = useAuth(); const nav = useNavigate(); const qc = useQueryClient()
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => api<Customer[]>('/customers') })
  const [customerId, setCustomerId] = useState<number | ''>('')
  const [start, setStart] = useState(today()); const [end, setEnd] = useState(addYear(today()))
  const [picked, setPicked] = useState<Record<string, string>>({ general_liability: '1M' })
  const catalog = config?.catalog ?? {}
  const tdays = Math.max(0, days(start, end))
  const lines = Object.entries(picked).map(([code, limit]) => ({ code, limit, name: catalog[code]?.name ?? code, est: tdays ? roundDiv((catalog[code]?.limits[limit] ?? 0) * tdays, 365) : 0 }))
  const total = lines.reduce((s, l) => s + l.est, 0)
  const m = useMutation({
    mutationFn: () => api<PolicyDetail>('/policies', { body: { customer_id: customerId, start_date: start, end_date: end, coverages: lines.map(({ code, limit }) => ({ code, limit })) } }),
    onSuccess: (p) => { qc.invalidateQueries({ queryKey: ['policies'] }); nav(`/broker/policies/${p.id}`) },
  })
  const toggle = (code: string) => setPicked((p) => { const n = { ...p }; if (n[code]) delete n[code]; else n[code] = Object.keys(catalog[code].limits)[0]; return n })
  function submit(e: FormEvent) { e.preventDefault(); m.mutate() }
  return (
    <>
      <PageTitle sub="Pick the customer, the term, and coverage. Premium is priced from the catalog and booked to the ledger on issue.">Issue a policy</PageTitle>
      <form onSubmit={submit} className="grid lg:grid-cols-[1fr_320px] gap-5 items-start">
        <div className="space-y-5">
          <Card className="p-5 space-y-4">
            <Field label="Customer" hint={customers.data?.length === 0 ? undefined : undefined}>
              <Select value={customerId} onChange={(e) => setCustomerId(Number(e.target.value))} required>
                <option value="">Select a customer…</option>
                {customers.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </Field>
            <p className="text-[12px] text-muted -mt-2">Need a new one? <Link className="text-orange-deep underline" to="/broker/customers">Create a customer</Link></p>
            <div className="grid sm:grid-cols-2 gap-4">
              <Field label="Coverage starts"><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} required /></Field>
              <Field label="Expires on (first day not covered)"><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} required /></Field>
            </div>
          </Card>
          <Card className="p-5">
            <h3 className="text-[18px] mb-3">Coverage</h3>
            <div className="space-y-2">
              {Object.entries(catalog).map(([code, c]) => (
                <div key={code} className={`flex items-center justify-between gap-3 rounded-corgi border px-3 py-2.5 ${picked[code] ? 'border-orange bg-tint/30' : 'border-line'}`}>
                  <label className="flex items-center gap-2.5 cursor-pointer"><input type="checkbox" className="accent-[#ff5c00]" checked={!!picked[code]} onChange={() => toggle(code)} />
                    <span className="font-medium">{c.name}</span><span className="text-[12px] text-muted">{c.kind === 'base' ? 'Core' : 'Add-on'}</span></label>
                  {picked[code] && (
                    <Select className="!w-auto !h-8" value={picked[code]} onChange={(e) => setPicked((p) => ({ ...p, [code]: e.target.value }))}>
                      {Object.entries(c.limits).map(([lim, cents]) => <option key={lim} value={lim}>{lim} limit · {usd(cents)}/yr</option>)}
                    </Select>)}
                </div>
              ))}
            </div>
          </Card>
        </div>
        <Card className="p-5 lg:sticky lg:top-4">
          <h3 className="text-[18px] mb-3">Premium summary</h3>
          {lines.length === 0 ? <p className="text-muted">Choose at least one coverage.</p> : (
            <ul className="space-y-1.5">{lines.map((l) => <li key={l.code} className="flex justify-between"><span>{l.name} {l.limit}</span><span className="money">{usd(l.est)}</span></li>)}</ul>
          )}
          <div className="border-t border-line mt-3 pt-3 flex justify-between font-medium"><span>Term premium</span><span className="money">{usd(total)}</span></div>
          <p className="text-[12px] text-muted mt-2">{tdays > 0 ? `${fdate(start)} → ${fdate(end)} (${tdays} days). ` : ''}Annual price × term days ÷ 365, rounded to the cent. The server recomputes this when you issue.</p>
          <div className="mt-4 space-y-3"><ErrorNote error={m.error} />
            <Button className="w-full" disabled={m.isPending || !customerId || lines.length === 0 || tdays <= 0}>{m.isPending ? 'Issuing…' : 'Issue policy'}</Button></div>
        </Card>
      </form>
    </>
  )
}
