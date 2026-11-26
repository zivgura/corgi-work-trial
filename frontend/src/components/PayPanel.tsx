import { useEffect, useState } from 'react'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import { loadStripe, type Stripe } from '@stripe/stripe-js'
import { api, type Payment } from '../lib/api'
import { useAuth } from '../auth'
import { usd } from '../lib/format'
import { Badge, Button, Card, ErrorNote, Icon } from './ui'
import { usePaymentLock } from './PaymentLock'
import { useToast } from './Toast'

interface Started { payment: Payment; client_secret: string | null; mode: 'fake' | 'stripe' }

/** Collect the amount due. SIMULATED mode mimics Stripe's test cards; STRIPE mode uses real
 *  Stripe test-mode PaymentIntents + Elements. Either way status moves pending → succeeded/failed
 *  through the same server-side event handler. */
export function PayPanel({ policyId, amountDue, hasOpenAttempt, onChanged }: { policyId: number; amountDue: number; hasOpenAttempt: boolean; onChanged: (p?: Payment) => void }) {
  const { setLocked } = usePaymentLock()
  const { config } = useAuth()
  const [started, setStarted] = useState<Started | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Payment | null>(null)
  const [slow, setSlow] = useState(false)

  // Lock the rest of the page while we create an attempt (busy) or a payment is processing (processing).
  const [processing, setProcessing] = useState(false)
  useEffect(() => { setLocked(busy || processing); return () => setLocked(false) }, [busy, processing, setLocked])

  async function start() {
    setBusy(true); setError(null); setResult(null); setSlow(false)
    try { setStarted(await api<Started>(`/policies/${policyId}/payments`, { method: 'POST', body: {} })); onChanged() }
    catch (e) { setError(e) } finally { setBusy(false) }
  }
  // Outcomes: succeeded -> the page shows its success banner; failed -> the attempt is over and the customer
  // starts a fresh one ("Try again"); still pending after a while -> tell them it is safe to wait.
  const finished = (p: Payment) => {
    setResult(p); setSlow(false)
    if (p.status !== 'pending') setStarted(null)
    onChanged(p)
  }

  const failed = result?.status === 'failed'
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-3 border-b border-line bg-canvas/60 px-6 py-4">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-tint text-orange-deep"><Icon name="credit_card" /></span>
        <div>
          <h2 className="text-[20px] leading-tight">Pay your premium</h2>
          <div className="text-[12px] text-muted">{config?.payment_provider === 'stripe' ? 'Card payment · secured by Stripe (test mode)' : 'Card payment · simulated (test mode)'}</div>
        </div>
      </div>
      <div className="px-6 py-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[12px] text-body">Amount due today</div>
            <div className="money text-[34px] leading-tight">{usd(amountDue)}</div>
          </div>
          {!started && <Button onClick={start} disabled={busy} className="!h-11 !px-6 !text-[15px]">{busy ? 'Starting…' : <><Icon name="lock" className="!text-[18px]" /> {failed ? 'Try again' : hasOpenAttempt ? 'Continue payment' : 'Pay'} {usd(amountDue)}</>}</Button>}
        </div>
        <ErrorNote error={error} />
        {hasOpenAttempt && !started && !failed && (
          <p className="mt-4 rounded-corgi bg-canvas px-3 py-2.5 text-[13px] text-body">You started a payment but haven&apos;t finished it. Nothing has been charged yet; continue where you left off.</p>
        )}
        {failed && !started && (
          <div role="alert" className="mt-4 flex items-start gap-2 rounded-corgi border border-danger/30 bg-danger/5 p-3 text-danger">
            <Icon name="error" />
            <div className="text-[14px]"><b>Payment failed.</b> {(result?.failure_reason ?? 'Your card was not charged.').replace(/\.$/, '')}. You have not been charged. Try again with another card.</div>
          </div>
        )}
        {slow && (
          <div role="status" className="mt-4 flex items-start gap-2 rounded-corgi border border-orange/30 bg-tint/40 p-3 text-[14px]">
            <Icon name="hourglass_top" className="text-orange-deep" />
            <div>Your bank is still confirming this payment. You can safely leave this page; the policy will show <b>Paid</b> as soon as it is confirmed. Please do not pay again.</div>
          </div>
        )}
      </div>
      {started && (
        <div className="border-t border-line px-6 py-5">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Badge tone="warn">{processing ? 'Processing payment…' : 'Payment pending'}</Badge>
            <span className="text-[12px] text-muted">{started.mode === 'stripe' ? 'Stripe test mode: use a test card, no real money moves.' : 'Simulated test payment, no network call.'}</span>
          </div>
          {started.mode === 'fake'
            ? <SimulatedCard payment={started.payment} amount={amountDue} onDone={finished} onProcessing={setProcessing} />
            : <StripeCard started={started} amount={amountDue} onDone={finished} onProcessing={setProcessing} onSlow={() => setSlow(true)} />}
        </div>
      )}
    </Card>
  )
}

function SimulatedCard({ payment, amount, onDone, onProcessing }: { payment: Payment; amount: number; onDone: (p: Payment) => void; onProcessing: (v: boolean) => void }) {
  const [card, setCard] = useState<'succeed' | 'decline'>('succeed')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  async function submit() {
    setBusy(true); onProcessing(true); setError(null)
    try { const r = await api<{ payment: Payment }>(`/payments/${payment.id}/simulate`, { body: { outcome: card } }); onDone(r.payment) }
    catch (e) { setError(e) } finally { setBusy(false); onProcessing(false) }
  }
  const opt = (v: 'succeed' | 'decline', num: string, note: string) => (
    <label className={`flex items-center gap-3 rounded-corgi border px-3 py-2.5 cursor-pointer ${card === v ? 'border-orange bg-tint/40' : 'border-line bg-white'}`}>
      <input type="radio" name="card" checked={card === v} onChange={() => setCard(v)} disabled={busy} className="accent-[#ff5c00]" />
      <Icon name="credit_card" /><span className="money">{num}</span><span className="text-[12px] text-body">{note}</span>
    </label>
  )
  return (
    <div className="space-y-2">
      <p className="text-[13px] text-body">Choose a test card:</p>
      {opt('succeed', '4242 4242 4242 4242', 'Succeeds')}
      {opt('decline', '4000 0000 0000 0002', 'Declined')}
      <ErrorNote error={error} />
      <Button onClick={submit} disabled={busy} className="w-full !h-11">{busy ? 'Processing…' : `Submit payment of ${usd(amount)}`}</Button>
    </div>
  )
}

let stripePromise: Promise<Stripe | null> | null = null
function StripeCard({ started, amount, onDone, onProcessing, onSlow }: { started: Started; amount: number; onDone: (p: Payment) => void; onProcessing: (v: boolean) => void; onSlow: () => void }) {
  const { config } = useAuth()
  if (!stripePromise) stripePromise = loadStripe(config?.stripe_publishable_key ?? '')
  return (
    <Elements stripe={stripePromise} options={{ clientSecret: started.client_secret ?? '' }}>
      <StripeForm started={started} amount={amount} onDone={onDone} onProcessing={onProcessing} onSlow={onSlow} />
    </Elements>
  )
}

function StripeForm({ started, amount, onDone, onProcessing, onSlow }: { started: Started; amount: number; onDone: (p: Payment) => void; onProcessing: (v: boolean) => void; onSlow: () => void }) {
  const stripe = useStripe(); const elements = useElements()
  const toast = useToast()
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const [complete, setComplete] = useState(false) // every card field filled in and valid
  async function submit() {
    if (!stripe || !elements || !complete) return
    setBusy(true); onProcessing(true); setError(null)
    try {
      const { error: err } = await stripe.confirmPayment({ elements, redirect: 'if_required', confirmParams: { return_url: window.location.href } })
      // Form mistakes (empty or invalid card fields) never reached the bank: let the customer fix them.
      if (err && err.type === 'validation_error') { setError(err.message ?? 'Please check your card details.'); return }
      // Otherwise the webhook is the source of truth (card declines arrive as a failed event too);
      // poll until the server has recorded the outcome.
      for (let i = 0; i < 20; i++) {
        const list = await api<Payment[]>(`/policies/${started.payment.policy_id}/payments`)
        const p = list.find((x) => x.id === started.payment.id)
        if (p && p.status !== 'pending') return onDone(p)
        await new Promise((r) => setTimeout(r, 1000))
      }
      if (err) toast.error(err.message ?? 'Payment failed')
      else onSlow()
    } catch (e) {
      toast.error(e)
    } finally { setBusy(false); onProcessing(false) }
  }
  return (
    <div className="space-y-3">
      <PaymentElement options={{ readOnly: busy }} onChange={(e) => { setComplete(e.complete); if (e.complete) setError(null) }}
        onLoadError={(e) => toast.error(e.error?.message ?? 'The card form could not be loaded.')} />
      {error && <div role="alert" className="flex items-start gap-2 text-danger text-[13px]"><Icon name="error" className="!text-[18px]" />{error}</div>}
      <Button onClick={submit} disabled={busy || !stripe || !complete} className="w-full !h-11 !text-[15px]">{busy ? 'Processing…' : <><Icon name="lock" className="!text-[18px]" /> Pay {usd(amount)}</>}</Button>
      <p className="text-center text-[12px] text-muted">{complete || busy ? 'Card details are sent straight to Stripe and never touch our servers.' : 'Enter valid card details to enable payment.'}</p>
    </div>
  )
}
