import { useState } from 'react'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import { loadStripe, type Stripe } from '@stripe/stripe-js'
import { api, type Payment } from '../lib/api'
import { useAuth } from '../auth'
import { usd } from '../lib/format'
import { Badge, Button, Card, ErrorNote, Icon } from './ui'

interface Started { payment: Payment; client_secret: string | null; mode: 'fake' | 'stripe' }

/** Collect the amount due. SIMULATED mode mimics Stripe's test cards; STRIPE mode uses real
 *  Stripe test-mode PaymentIntents + Elements. Either way status moves pending → succeeded/failed
 *  through the same server-side event handler. */
export function PayPanel({ policyId, amountDue, onChanged }: { policyId: number; amountDue: number; onChanged: (p?: Payment) => void }) {
  const [started, setStarted] = useState<Started | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Payment | null>(null)

  async function start() {
    setBusy(true); setError(null); setResult(null)
    try { setStarted(await api<Started>(`/policies/${policyId}/payments`, { method: 'POST', body: {} })); onChanged() }
    catch (e) { setError(e) } finally { setBusy(false) }
  }
  const finished = (p: Payment) => { setResult(p); if (p.status === 'succeeded') setStarted(null); onChanged(p) }

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[12px] text-body">Amount due</div>
          <div className="money text-[28px]">{usd(amountDue)}</div>
        </div>
        {!started && <Button onClick={start} disabled={busy}><Icon name="credit_card" /> Pay {usd(amountDue)}</Button>}
      </div>
      <div className="mt-3"><ErrorNote error={error} /></div>
      {result?.status === 'succeeded' && <div className="mt-3 flex items-center gap-2 text-ok"><Icon name="check_circle" /> Payment successful. Thank you.</div>}
      {result?.status === 'failed' && <div className="mt-3 flex items-center gap-2 text-danger"><Icon name="error" /> Payment failed: {(result.failure_reason ?? '').replace(/\.$/, '')}. You can try again.</div>}
      {started && (
        <div className="mt-4 border-t border-line pt-4">
          <div className="flex items-center gap-2 mb-3">{result?.status === 'failed' ? <Badge tone="bad">Payment failed — try another card</Badge> : <Badge tone="warn">Payment pending</Badge>}
            <span className="text-[12px] text-muted">{started.mode === 'stripe' ? 'Stripe test mode' : 'Simulated test payment — no real network call'}</span></div>
          {started.mode === 'fake'
            ? <SimulatedCard payment={started.payment} onDone={finished} />
            : <StripeCard started={started} onDone={finished} />}
        </div>
      )}
    </Card>
  )
}

function SimulatedCard({ payment, onDone }: { payment: Payment; onDone: (p: Payment) => void }) {
  const [card, setCard] = useState<'succeed' | 'decline'>('succeed')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  async function submit() {
    setBusy(true); setError(null)
    try { const r = await api<{ payment: Payment }>(`/payments/${payment.id}/simulate`, { body: { outcome: card } }); onDone(r.payment) }
    catch (e) { setError(e) } finally { setBusy(false) }
  }
  const opt = (v: 'succeed' | 'decline', num: string, note: string) => (
    <label className={`flex items-center gap-3 rounded-corgi border px-3 py-2.5 cursor-pointer ${card === v ? 'border-orange bg-tint/40' : 'border-line bg-white'}`}>
      <input type="radio" name="card" checked={card === v} onChange={() => setCard(v)} className="accent-[#ff5c00]" />
      <Icon name="credit_card" /><span className="money">{num}</span><span className="text-[12px] text-body">{note}</span>
    </label>
  )
  return (
    <div className="space-y-2">
      <p className="text-[13px] text-body">Choose a test card:</p>
      {opt('succeed', '4242 4242 4242 4242', 'Succeeds')}
      {opt('decline', '4000 0000 0000 0002', 'Declined')}
      <ErrorNote error={error} />
      <Button onClick={submit} disabled={busy}>{busy ? 'Processing…' : 'Submit payment'}</Button>
    </div>
  )
}

let stripePromise: Promise<Stripe | null> | null = null
function StripeCard({ started, onDone }: { started: Started; onDone: (p: Payment) => void }) {
  const { config } = useAuth()
  if (!stripePromise) stripePromise = loadStripe(config?.stripe_publishable_key ?? '')
  return (
    <Elements stripe={stripePromise} options={{ clientSecret: started.client_secret ?? '' }}>
      <StripeForm started={started} onDone={onDone} />
    </Elements>
  )
}

function StripeForm({ started, onDone }: { started: Started; onDone: (p: Payment) => void }) {
  const stripe = useStripe(); const elements = useElements()
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  async function submit() {
    if (!stripe || !elements) return
    setBusy(true); setError(null)
    const { error: err } = await stripe.confirmPayment({ elements, redirect: 'if_required', confirmParams: { return_url: window.location.href } })
    if (err) setError(err.message ?? 'Payment failed')
    // The webhook is the source of truth; poll until the server has recorded the outcome.
    for (let i = 0; i < 20; i++) {
      const list = await api<Payment[]>(`/policies/${started.payment.policy_id}/payments`)
      const p = list.find((x) => x.id === started.payment.id)
      if (p && p.status !== 'pending') { setBusy(false); return onDone(p) }
      await new Promise((r) => setTimeout(r, 1000))
    }
    setBusy(false)
  }
  return (
    <div className="space-y-3">
      <PaymentElement />
      {error && <div role="alert" className="text-danger text-[13px]">{error}</div>}
      <Button onClick={submit} disabled={busy || !stripe}>{busy ? 'Processing…' : 'Pay'}</Button>
    </div>
  )
}
