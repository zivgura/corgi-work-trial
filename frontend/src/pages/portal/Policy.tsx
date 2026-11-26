import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api, type Payment, type PolicyDetail, type Statement as S } from '../../lib/api'
import { fdate, fdatetime, usd } from '../../lib/format'
import { Statement } from '../../components/Statement'
import { PayPanel } from '../../components/PayPanel'
import { Lockable } from '../../components/PaymentLock'
import { Badge, Card, LoadError, Icon, PaymentBadge, PolicyStatus } from '../../components/ui'

export default function PortalPolicy() {
  const { id = '' } = useParams(); const qc = useQueryClient()
  const detail = useQuery({ queryKey: ['policy', id], queryFn: () => api<PolicyDetail>(`/policies/${id}`),
    refetchInterval: (q) => (q.state.data?.payment_status === 'pending' ? 3000 : false) })
  const statement = useQuery({ queryKey: ['statement', id], queryFn: () => api<S>(`/policies/${id}/statement`) })
  const [paid, setPaid] = useState<Payment | null>(null)
  const refresh = (r?: Payment) => { if (r?.status === 'succeeded') { setPaid(r); window.scrollTo({ top: 0, behavior: 'smooth' }) } ['policy', 'statement'].forEach((k) => qc.invalidateQueries({ queryKey: [k, id] })); qc.invalidateQueries({ queryKey: ['policies'] }) }
  const p = detail.data
  if (detail.isLoading) return <div className="text-muted">Loading…</div>
  if (!p) return <LoadError error={detail.error} />
  const due = p.balance_cents
  const corrections = p.coverages.filter((c) => c.versions.length > 1)
  return (
    <>
      <Lockable>
      <Link to="/portal" className="text-[13px] text-body hover:text-ink inline-flex items-center gap-1 mb-2"><Icon name="arrow_back" className="!text-[16px]" /> All policies</Link>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div>
          <h1 className="text-[32px] flex items-center gap-3">{p.number} <PolicyStatus status={p.status} /> <PaymentBadge status={p.payment_status} /></h1>
          <p className="text-body mt-1">{fdate(p.start_date)} → expires {fdate(p.end_date)}{p.status === 'cancelled' && p.cancelled_on ? ` · cancelled effective ${fdate(p.cancelled_on)}` : ''}</p>
        </div>
      </div>

      {corrections.map((c) => {
        const prev = c.versions[c.versions.length - 2]; const cur = c.versions[c.versions.length - 1]
        return (
          <div key={c.id} className="mb-4 rounded-corgi border border-orange/30 bg-tint/40 p-4 flex gap-3">
            <Icon name="edit_calendar" className="text-orange-deep" />
            <div className="text-[14px]">
              <div className="font-medium">We corrected the start date of your {c.name}</div>
              <p className="text-body mt-0.5">It now starts <b>{fdate(cur.effective_date)}</b> (previously {fdate(prev.effective_date)}) — {cur.reason || 'correction'}. Recorded {fdatetime(cur.recorded_at)} by {cur.recorded_by}. Your original charge is unchanged below; the difference is a separate “Correction” line.</p>
            </div>
          </div>
        )
      })}

      </Lockable>

      {paid && <Card className="p-4 mb-4 flex items-center gap-3 text-ok"><Icon name="check_circle" /> Payment of {usd(paid.amount_cents)} successful. Thank you.</Card>}
      {due > 0 && <div className="mb-6"><PayPanel policyId={p.id} amountDue={due} hasOpenAttempt={p.payment_status === 'pending'} onChanged={refresh} /></div>}
      {due < 0 && <Card className="p-5 mb-6 flex items-center gap-3"><Icon name="savings" className="text-ok" /><div><div className="font-medium">You have a credit of {usd(-due)}</div><div className="text-body text-[13px]">Your broker will refund it to your original payment method.</div></div></Card>}
      {due === 0 && !paid && p.payment_status && <Card className="p-4 mb-6 flex items-center gap-3 text-ok"><Icon name="check_circle" /> Nothing due. You're all settled.</Card>}

      <Lockable>
      <h2 className="text-[22px] mb-2">Your coverage</h2>
      <div className="grid sm:grid-cols-2 gap-3 mb-8">
        {p.coverages.map((c) => (
          <Card key={c.id} className="p-4">
            <div className="flex items-center justify-between"><div className="font-medium">{c.name}</div><Badge tone={c.kind === 'base' ? 'dark' : 'neutral'}>{c.limit} limit</Badge></div>
            <div className="text-body text-[13px] mt-1.5">In force from {fdate(c.effective_date)}<br />{c.covered_days} days of cover · <span className="money">{usd(c.earned_premium_cents)}</span> premium</div>
          </Card>
        ))}
      </div>

      <h2 className="text-[22px] mb-2">Statement</h2>
      <p className="text-body text-[13px] mb-3">Select any line to see exactly how it was calculated and what caused it.</p>
      {statement.data && <Statement data={statement.data} audience="customer" />}
      </Lockable>
    </>
  )
}
