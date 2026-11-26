import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { Button, Card, ErrorNote, Field, Icon, Input } from '../components/ui'

const DEMO = {
  broker: { email: 'broker@corgi-demo.test', password: 'corgi-demo-broker' },
  customer: { email: 'ada@acme-ai.test', password: 'corgi-demo-customer' },
}

export default function Login() {
  const { user, login, config } = useAuth()
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null); const [busy, setBusy] = useState(false)
  if (user) return <Navigate to={user.role === 'broker' ? '/broker' : '/portal'} replace />
  async function submit(e?: FormEvent, creds = { email, password }) {
    e?.preventDefault(); setBusy(true); setError(null)
    try { await login(creds.email, creds.password) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  return (
    <div className="min-h-full grid place-items-center p-4"
      style={{ background: 'linear-gradient(180deg,#dfe9f5 0%,#f6f6f6 55%)' }}>
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-1.5 text-orange font-semibold text-[22px]"><Icon name="pets" className="!text-[26px]" /> corgi</div>
          <h1 className="text-[40px] mt-3">Policy admin at the <span className="serif-accent text-[44px]">speed of ledger.</span></h1>
          <p className="text-body mt-2">Work-trial demo: brokers issue and manage policies, customers follow every dollar.</p>
        </div>
        <Card className="p-6">
          <form onSubmit={submit} className="space-y-4">
            <Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required /></Field>
            <Field label="Password"><Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></Field>
            <ErrorNote error={error} />
            <Button className="w-full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</Button>
          </form>
          <div className="mt-5 border-t border-line pt-4">
            <div className="text-[12px] text-muted mb-2">Demo accounts (sandbox, fictional data)</div>
            <div className="grid grid-cols-2 gap-2">
              <Button variant="ghost" small onClick={() => submit(undefined, DEMO.broker)}><Icon name="badge" /> Broker</Button>
              <Button variant="ghost" small onClick={() => submit(undefined, DEMO.customer)}><Icon name="person" /> Policyholder</Button>
            </div>
          </div>
        </Card>
        {config && (
          <p className="text-center text-[12px] text-muted mt-4">
            Payments: {config.payment_provider === 'stripe' ? 'Stripe test mode (live sandbox)' : 'simulated'} · Email: {config.email_provider === 'resend' ? 'Resend (live sandbox)' : 'logged only (simulated)'}
          </p>
        )}
      </div>
    </div>
  )
}
