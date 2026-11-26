import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { useAuth } from '../../auth'
import { fdatetime } from '../../lib/format'
import { Badge, Card, PageTitle } from '../../components/ui'

interface Ops {
  payment_provider: string
  provider_events: { id: string; provider: string; type: string; received_at: string }[]
  emails: { id: number; policy_id: number | null; to: string; subject: string; template: string; provider: string; status: string; provider_id: string | null; error: string | null; created_at: string }[]
}

export default function Integrations() {
  const { config } = useAuth()
  const q = useQuery({ queryKey: ['ops'], queryFn: () => api<Ops>('/ops/events'), refetchInterval: 4000 })
  const stripe = config?.payment_provider === 'stripe'; const resend = config?.email_provider === 'resend'
  return (
    <>
      <PageTitle sub="What is live sandbox and what is simulated, plus the raw events as evidence.">Integrations</PageTitle>
      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        <Card className="p-5"><div className="flex items-center justify-between"><h3 className="text-[18px]">Payments · Stripe</h3><Badge tone={stripe ? 'ok' : 'warn'}>{stripe ? 'LIVE · test mode' : 'SIMULATED'}</Badge></div>
          <p className="text-body mt-2 text-[13px]">{stripe ? 'PaymentIntents and Refunds against Stripe test mode. Outcomes arrive as signed webhooks.' : 'No network calls. Confirmations are injected through the same event handler the Stripe webhook uses.'}</p></Card>
        <Card className="p-5"><div className="flex items-center justify-between"><h3 className="text-[18px]">Email · Resend</h3><Badge tone={resend ? 'ok' : 'warn'}>{resend ? 'LIVE · sandbox' : 'SIMULATED'}</Badge></div>
          <p className="text-body mt-2 text-[13px]">{resend ? 'Transactional email through Resend to test recipients.' : 'Emails are rendered and logged below but not sent.'}</p></Card>
      </div>
      <h2 className="text-[22px] mb-2">Provider events</h2>
      <Card className="overflow-x-auto mb-6"><table className="w-full text-left text-[13px]"><thead><tr className="text-[12px] text-muted border-b border-line"><th className="p-3 font-medium">Received</th><th className="p-3 font-medium">Provider</th><th className="p-3 font-medium">Type</th><th className="p-3 font-medium">Event id</th></tr></thead>
        <tbody>{q.data?.provider_events.map((e) => <tr key={e.id} className="border-b border-line/70"><td className="p-3 whitespace-nowrap">{fdatetime(e.received_at)}</td><td className="p-3">{e.provider}</td><td className="p-3">{e.type}</td><td className="p-3 mono">{e.id}</td></tr>)}
          {q.data?.provider_events.length === 0 && <tr><td colSpan={4} className="p-5 text-muted text-center">No events yet.</td></tr>}</tbody></table></Card>
      <h2 className="text-[22px] mb-2">Emails</h2>
      <Card className="overflow-x-auto"><table className="w-full text-left text-[13px]"><thead><tr className="text-[12px] text-muted border-b border-line"><th className="p-3 font-medium">Sent</th><th className="p-3 font-medium">To</th><th className="p-3 font-medium">Subject</th><th className="p-3 font-medium">Status</th><th className="p-3 font-medium">Provider id</th></tr></thead>
        <tbody>{q.data?.emails.map((m) => <tr key={m.id} className="border-b border-line/70"><td className="p-3 whitespace-nowrap">{fdatetime(m.created_at)}</td><td className="p-3">{m.to}</td><td className="p-3">{m.subject}</td><td className="p-3"><Badge tone={m.status === 'sent' ? 'ok' : m.status === 'failed' ? 'bad' : 'warn'}>{m.status}</Badge></td><td className="p-3 mono">{m.provider_id ?? '—'}</td></tr>)}
          {q.data?.emails.length === 0 && <tr><td colSpan={5} className="p-5 text-muted text-center">No emails yet.</td></tr>}</tbody></table></Card>
    </>
  )
}
