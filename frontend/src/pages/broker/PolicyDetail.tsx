import { useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api, type Coverage, type PolicyDetail, type Preview, type Statement as S, type TimelineItem } from '../../lib/api'
import { useAuth } from '../../auth'
import { fdate, fdatetime, today, usd } from '../../lib/format'
import { Statement } from '../../components/Statement'
import { Timeline } from '../../components/Timeline'
import { Badge, Button, Card, ErrorNote, Field, Icon, Input, Modal, PaymentBadge, PolicyStatus, Select } from '../../components/ui'

function usePolicyData(id: string) {
  const qc = useQueryClient()
  const detail = useQuery({ queryKey: ['policy', id], queryFn: () => api<PolicyDetail>(`/policies/${id}`) })
  const statement = useQuery({ queryKey: ['statement', id], queryFn: () => api<S>(`/policies/${id}/statement`) })
  const timeline = useQuery({ queryKey: ['timeline', id], queryFn: () => api<TimelineItem[]>(`/policies/${id}/timeline`) })
  const refresh = () => ['policy', 'statement', 'timeline', 'policies'].forEach((k) => qc.invalidateQueries({ queryKey: k === 'policies' ? [k] : [k, id] }))
  return { detail, statement, timeline, refresh }
}

function usePreview(id: string, body: Record<string, unknown> | null) {
  return useQuery({ queryKey: ['preview', id, body], enabled: !!body, queryFn: () => api<Preview>(`/policies/${id}/preview`, { body }) })
}

function PreviewBox({ q, kind }: { q: ReturnType<typeof usePreview>; kind: 'premium' | 'cancel' }) {
  if (q.isError) return <ErrorNote error={q.error} />
  if (!q.data) return <div className="rounded-corgi bg-canvas p-3 text-muted text-[13px]">Fill in the details to see the amount before you confirm.</div>
  const p = q.data; const changed = p.lines.filter((l) => l.delta_cents !== 0)
  const after = p.new_balance_cents
  return (
    <div className="rounded-corgi border border-orange/30 bg-tint/30 p-3.5 text-[13px] space-y-2">
      <div className="font-medium text-orange-deep">Preview — nothing is saved yet</div>
      {changed.length === 0 && <div className="text-body">No change to premium.</div>}
      {changed.map((l) => (
        <div key={l.coverage}>
          <div className="flex justify-between"><span>{l.coverage}</span><span className="money">{l.delta_cents > 0 ? '+' : ''}{usd(l.delta_cents)}</span></div>
          <div className="text-body money text-[12px]">{l.formula}{l.previously_booked_cents ? ` − already charged ${usd(l.previously_booked_cents)}` : ''}</div>
        </div>
      ))}
      <div className="border-t border-orange/20 pt-2 flex justify-between font-medium">
        <span>{kind === 'cancel' ? 'Result' : after < 0 ? 'Credit on account after' : 'Amount due after'}</span>
        <span className="money">{kind === 'cancel' && p.refund_cents > 0 ? `Refund ${usd(p.refund_cents)}` : usd(Math.abs(after))}</span>
      </div>
      {kind === 'cancel' && after > 0 && <div className="text-body">Customer would still owe {usd(after)} for earned premium.</div>}
    </div>
  )
}

export default function PolicyPage() {
  const { id = '' } = useParams()
  const { detail, statement, timeline, refresh } = usePolicyData(id)
  const [modal, setModal] = useState<null | 'add' | 'cancel' | 'refund' | { correct: Coverage }>(null)
  const [tab, setTab] = useState<'statement' | 'timeline'>('statement')
  const p = detail.data
  if (detail.isLoading) return <div className="text-muted">Loading…</div>
  if (!p) return <ErrorNote error={detail.error} />
  const bal = p.balance_cents
  return (
    <>
      <Link to="/broker" className="text-[13px] text-body hover:text-ink inline-flex items-center gap-1 mb-2"><Icon name="arrow_back" className="!text-[16px]" /> Policies</Link>
      <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
        <div>
          <h1 className="text-[32px] flex items-center gap-3">{p.number} <PolicyStatus status={p.status} /> <PaymentBadge status={p.payment_status} /></h1>
          <p className="text-body mt-1">{p.customer.name} · {p.customer.contact_name} · {fdate(p.start_date)} → expires {fdate(p.end_date)} ({p.term_days} days)</p>
          {p.status === 'cancelled' && <p className="text-body text-[13px] mt-1">Cancelled effective {fdate(p.cancelled_on!)}{p.cancel_reason ? ` — ${p.cancel_reason}` : ''}</p>}
        </div>
        <div className={`rounded-corgi border px-5 py-3 text-right ${bal > 0 ? 'bg-tint border-orange/30' : bal < 0 ? 'bg-ok/10 border-ok/30' : 'bg-white border-line'}`}>
          <div className="text-[12px] text-body">{bal < 0 ? 'Credit on account' : 'Amount due'}</div>
          <div className="money text-[28px]">{usd(Math.abs(bal))}</div>
        </div>
      </div>

      <Card className="mb-6">
        <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 border-b border-line">
          <h2 className="text-[20px]">Coverage</h2>
          <div className="flex gap-2">
            {p.status === 'active' && <Button small onClick={() => setModal('add')}><Icon name="add" /> Add coverage</Button>}
            {bal < 0 && <Button small variant="dark" onClick={() => setModal('refund')}><Icon name="currency_exchange" /> Refund credit</Button>}
            {p.status === 'active' && <Button small variant="danger" onClick={() => setModal('cancel')}>Cancel policy</Button>}
          </div>
        </div>
        <div className="divide-y divide-line">
          {p.coverages.map((c) => <CoverageRow key={c.id} c={c} policy={p} onCorrect={() => setModal({ correct: c })} />)}
        </div>
      </Card>

      <div className="flex gap-1 mb-3 border-b border-line">
        {(['statement', 'timeline'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 -mb-px border-b-2 cursor-pointer ${tab === t ? 'border-orange text-ink font-medium' : 'border-transparent text-body'}`}>{t === 'statement' ? 'Financial statement' : 'Activity history'}</button>
        ))}
      </div>
      {tab === 'statement' && statement.data && <Statement data={statement.data} audience="broker" />}
      {tab === 'timeline' && timeline.data && <Timeline items={timeline.data} />}

      {modal === 'add' && <AddCoverageModal id={id} p={p} onClose={() => setModal(null)} onDone={refresh} />}
      {modal === 'cancel' && <CancelModal id={id} p={p} onClose={() => setModal(null)} onDone={refresh} />}
      {modal === 'refund' && <RefundModal id={id} credit={-bal} onClose={() => setModal(null)} onDone={refresh} />}
      {modal && typeof modal === 'object' && <CorrectModal id={id} c={modal.correct} onClose={() => setModal(null)} onDone={refresh} />}
    </>
  )
}

function CoverageRow({ c, policy, onCorrect }: { c: Coverage; policy: PolicyDetail; onCorrect: () => void }) {
  const [open, setOpen] = useState(false)
  const corrected = c.versions.length > 1
  return (
    <div className="px-5 py-3.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-medium flex items-center gap-2">{c.name} <span className="text-muted font-normal">{c.limit} limit</span>
            <Badge tone={c.kind === 'base' ? 'dark' : 'neutral'}>{c.kind === 'base' ? 'Core' : 'Add-on'}</Badge>{corrected && <Badge tone="warn">Date corrected</Badge>}</div>
          <div className="text-body text-[13px] mt-0.5">In force from <b>{fdate(c.effective_date)}</b> · {c.covered_days} of {policy.term_days} days · earned <span className="money">{usd(c.earned_premium_cents)}</span> of <span className="money">{usd(c.term_premium_cents)}</span> term premium</div>
        </div>
        <div className="flex gap-2">
          {c.versions.length > 1 && <Button small variant="ghost" onClick={() => setOpen(!open)}>{open ? 'Hide' : 'Show'} date history</Button>}
          <Button small variant="ghost" onClick={onCorrect}><Icon name="edit_calendar" /> Correct start date</Button>
        </div>
      </div>
      {open && (
        <ul className="mt-3 space-y-1.5 text-[13px]">
          {c.versions.map((v) => (
            <li key={v.id} className={`flex flex-wrap gap-x-2 ${v.is_current ? '' : 'text-muted line-through decoration-muted/50'}`}>
              <span className="font-medium">{fdate(v.effective_date)}</span><span>{v.is_current ? '(current)' : '(superseded)'}</span>
              <span>recorded {fdatetime(v.recorded_at)} by {v.recorded_by}</span>{v.reason && <span>— “{v.reason}”</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ModalForm({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return <Modal title={title} onClose={onClose} wide={wide}>{children}</Modal>
}

function AddCoverageModal({ id, p, onClose, onDone }: { id: string; p: PolicyDetail; onClose: () => void; onDone: () => void }) {
  const { config } = useAuth()
  const available = Object.entries(config?.catalog ?? {}).filter(([code]) => !p.coverages.some((c) => c.code === code))
  const [code, setCode] = useState(available[0]?.[0] ?? ''); const [limit, setLimit] = useState('1M')
  const [eff, setEff] = useState(today() < p.start_date ? p.start_date : today() > p.end_date ? p.start_date : today()); const [reason, setReason] = useState('')
  const limits = Object.keys(config?.catalog[code]?.limits ?? {})
  const pv = usePreview(id, code && eff ? { kind: 'add_coverage', code, limit, effective_date: eff } : null)
  const m = useMutation({ mutationFn: () => api(`/policies/${id}/coverages`, { body: { code, limit, effective_date: eff, reason } }), onSuccess: () => { onDone(); onClose() } })
  function submit(e: FormEvent) { e.preventDefault(); m.mutate() }
  if (available.length === 0) return <ModalForm title="Add coverage" onClose={onClose}><p>Every available coverage is already on this policy.</p></ModalForm>
  return (
    <ModalForm title="Add coverage mid-term" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Coverage"><Select value={code} onChange={(e) => { setCode(e.target.value); setLimit(Object.keys(config!.catalog[e.target.value].limits)[0]) }}>{available.map(([c, v]) => <option key={c} value={c}>{v.name}</option>)}</Select></Field>
          <Field label="Limit"><Select value={limit} onChange={(e) => setLimit(e.target.value)}>{limits.map((l) => <option key={l}>{l}</option>)}</Select></Field>
        </div>
        <Field label="Takes effect on" hint="Premium is charged from this date to the end of the term."><Input type="date" min={p.start_date} value={eff} onChange={(e) => setEff(e.target.value)} required /></Field>
        <Field label="Note (optional)"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Customer requested cyber after SOC 2 audit" /></Field>
        <PreviewBox q={pv} kind="premium" /><ErrorNote error={m.error} />
        <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Back</Button><Button disabled={m.isPending}>Add coverage</Button></div>
      </form>
    </ModalForm>
  )
}

function CorrectModal({ id, c, onClose, onDone }: { id: string; c: Coverage; onClose: () => void; onDone: () => void }) {
  const [date, setDate] = useState(c.effective_date); const [reason, setReason] = useState('')
  const changed = date !== c.effective_date
  const pv = usePreview(id, changed ? { kind: 'correction', coverage_id: c.id, new_effective_date: date } : null)
  const m = useMutation({ mutationFn: () => api(`/policies/${id}/coverages/${c.id}/correct-effective-date`, { body: { new_effective_date: date, reason } }), onSuccess: () => { onDone(); onClose() } })
  function submit(e: FormEvent) { e.preventDefault(); m.mutate() }
  return (
    <ModalForm title={`Correct start date · ${c.name} ${c.limit}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-body text-[13px]">Currently recorded as starting <b>{fdate(c.effective_date)}</b>. The original charge stays on the statement; the correction is added as its own line.</p>
        <Field label="Actual effective date"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></Field>
        <Field label="Reason (required — shown to the customer)"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Binder confirms cover began Feb 22" required /></Field>
        <PreviewBox q={pv} kind="premium" /><ErrorNote error={m.error} />
        <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Back</Button><Button disabled={m.isPending || !changed || !reason.trim()}>Apply correction</Button></div>
      </form>
    </ModalForm>
  )
}

function CancelModal({ id, p, onClose, onDone }: { id: string; p: PolicyDetail; onClose: () => void; onDone: () => void }) {
  const [date, setDate] = useState(today() > p.start_date && today() < p.end_date ? today() : p.start_date); const [reason, setReason] = useState('')
  const pv = usePreview(id, date ? { kind: 'cancel', cancelled_on: date } : null)
  const m = useMutation({ mutationFn: () => api(`/policies/${id}/cancel`, { body: { cancelled_on: date, reason } }), onSuccess: () => { onDone(); onClose() } })
  function submit(e: FormEvent) { e.preventDefault(); m.mutate() }
  return (
    <ModalForm title="Cancel policy" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-body text-[13px]">Rule: pro-rata. Coverage ends at 00:00 on the cancellation date; unearned premium is refunded to the original payment method. No short-rate penalty, no fee.</p>
        <Field label="Cancellation effective"><Input type="date" min={p.start_date} value={date} onChange={(e) => setDate(e.target.value)} required /></Field>
        <Field label="Reason"><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <PreviewBox q={pv} kind="cancel" /><ErrorNote error={m.error} />
        <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Keep policy</Button><Button variant="danger" disabled={m.isPending}>Cancel policy</Button></div>
      </form>
    </ModalForm>
  )
}

function RefundModal({ id, credit, onClose, onDone }: { id: string; credit: number; onClose: () => void; onDone: () => void }) {
  const m = useMutation({ mutationFn: () => api(`/policies/${id}/refund`, { body: {} }), onSuccess: () => { onDone(); onClose() } })
  return (
    <ModalForm title="Refund credit" onClose={onClose}>
      <p>The customer has a credit of <b className="money">{usd(credit)}</b>. Refund it to their original payment method? This cannot be undone.</p>
      <div className="mt-4"><ErrorNote error={m.error} /></div>
      <div className="flex justify-end gap-2 mt-4"><Button variant="ghost" onClick={onClose}>Not now</Button><Button onClick={() => m.mutate()} disabled={m.isPending}>Refund {usd(credit)}</Button></div>
    </ModalForm>
  )
}
