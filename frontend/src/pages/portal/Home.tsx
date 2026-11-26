import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type PolicyRow } from '../../lib/api'
import { useAuth } from '../../auth'
import { fdate, usd } from '../../lib/format'
import { Badge, Card, Icon, PaymentBadge, PolicyStatus } from '../../components/ui'

export default function Home() {
  const { user } = useAuth()
  const q = useQuery({ queryKey: ['policies'], queryFn: () => api<PolicyRow[]>('/policies') })
  return (
    <>
      <h1 className="text-[40px] mb-1">Hi {user?.name.split(' ')[0]}, here's your <span className="serif-accent text-[44px]">coverage.</span></h1>
      <p className="text-body mb-6">Every charge, payment and refund, with the reason behind it.</p>
      <div className="space-y-3">
        {q.isLoading && <div className="text-muted">Loading…</div>}
        {q.data?.length === 0 && <Card className="p-8 text-center text-muted">No policies yet. Your broker will set one up for you.</Card>}
        {q.data?.map((p) => (
          <Link key={p.id} to={`/portal/policies/${p.id}`} className="block">
            <Card className="p-5 hover:border-orange transition">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2"><span className="text-[20px] font-medium">{p.number}</span><PolicyStatus status={p.status} /><PaymentBadge status={p.payment_status} /></div>
                  <div className="text-body mt-1">{p.coverage_names.join(' · ')}</div>
                  <div className="text-muted text-[13px] mt-0.5">{fdate(p.start_date)} → expires {fdate(p.end_date)}</div>
                </div>
                <div className="text-right">
                  {p.balance_cents > 0 ? <Badge tone="warn">Amount due</Badge> : p.balance_cents < 0 ? <Badge tone="ok">Credit</Badge> : <Badge tone="ok">All settled</Badge>}
                  <div className="money text-[22px] mt-1">{usd(Math.abs(p.balance_cents))}</div>
                </div>
                <Icon name="chevron_right" className="text-muted" />
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </>
  )
}
