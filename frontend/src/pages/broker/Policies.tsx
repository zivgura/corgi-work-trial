import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api, type Customer, type PolicyRow } from '../../lib/api'
import { useAuth } from '../../auth'
import { fdate, usd } from '../../lib/format'
import { Button, Card, Icon, PageTitle, PaymentBadge, PolicyStatus } from '../../components/ui'

export default function Policies() {
  const { config } = useAuth(); const qc = useQueryClient(); const nav = useNavigate()
  const q = useQuery({ queryKey: ['policies'], queryFn: () => api<PolicyRow[]>('/policies') })
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => api<Customer[]>('/customers') })
  const demo = useMutation({
    mutationFn: () => api<{ id: number }>('/demo/scenario', { body: { customer_id: customers.data![customers.data!.length - 1].id } }),
    onSuccess: (p) => { qc.invalidateQueries({ queryKey: ['policies'] }); nav(`/broker/policies/${p.id}`) },
  })
  return (
    <>
      <div className="flex items-end justify-between">
        <PageTitle sub="Everything you've issued. Open a policy to change, correct or cancel it.">Policies</PageTitle>
        <div className="flex gap-2">
          {config?.payment_provider === 'fake' && customers.data?.length ? (
            <Button variant="ghost" onClick={() => demo.mutate()} disabled={demo.isPending} title="Creates a policy whose premium and mid-term coverage change are already paid (simulated payments)"><Icon name="science" /> Load demo scenario</Button>
          ) : null}
          <Link to="/broker/new"><Button><Icon name="add" /> Issue policy</Button></Link>
        </div>
      </div>
      <Card className="overflow-x-auto">
        <table className="w-full text-left">
          <thead><tr className="text-[12px] text-muted border-b border-line">
            {['Policy', 'Customer', 'Coverage', 'Term', 'Status', 'Payment', 'Balance'].map((h, i) => <th key={h} className={`py-2.5 px-4 font-medium ${i === 6 ? 'text-right' : ''}`}>{h}</th>)}
          </tr></thead>
          <tbody>
            {q.isLoading && <tr><td colSpan={7} className="p-6 text-muted">Loading…</td></tr>}
            {q.data?.length === 0 && <tr><td colSpan={7} className="p-8 text-center text-muted">No policies yet. Issue one to get started.</td></tr>}
            {q.data?.map((p) => (
              <tr key={p.id} className="border-b border-line/70 hover:bg-canvas/70">
                <td className="py-3 px-4"><Link className="font-medium text-orange-deep hover:underline" to={`/broker/policies/${p.id}`}>{p.number}</Link></td>
                <td className="py-3 px-4">{p.customer.name}</td>
                <td className="py-3 px-4 text-body">{p.coverage_names.join(', ')}</td>
                <td className="py-3 px-4 text-body whitespace-nowrap">{fdate(p.start_date)} → {fdate(p.end_date)}</td>
                <td className="py-3 px-4"><PolicyStatus status={p.status} /></td>
                <td className="py-3 px-4"><PaymentBadge status={p.payment_status} /></td>
                <td className={`py-3 px-4 text-right money ${p.balance_cents > 0 ? 'text-orange-deep' : p.balance_cents < 0 ? 'text-ok' : ''}`}>{usd(p.balance_cents)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}
