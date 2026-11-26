import { Fragment, useState } from 'react'
import { usd, fdate, fdatetime } from '../lib/format'
import type { Statement as S, StatementRow } from '../lib/api'
import { Badge, Icon } from './ui'

const TYPE_LABEL: Record<StatementRow['type'], { label: string; tone: 'neutral' | 'warn' | 'ok' | 'bad' | 'dark' }> = {
  CHARGE: { label: 'Charge', tone: 'neutral' },
  ADJUSTMENT: { label: 'Correction', tone: 'warn' },
  CREDIT: { label: 'Credit', tone: 'ok' },
  PAYMENT: { label: 'Payment', tone: 'ok' },
  REFUND: { label: 'Refund', tone: 'dark' },
}

/** Ledger statement. Every row opens to show the formula and the action behind it. */
export function Statement({ data, audience }: { data: S; audience: 'broker' | 'customer' }) {
  const [open, setOpen] = useState<number | null>(null)
  const due = data.balance_cents
  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <Stat label="Net premium" value={usd(data.totals.net_premium_cents)} />
        <Stat label="Paid" value={usd(data.totals.paid_cents)} />
        <Stat label="Refunded" value={usd(data.totals.refunded_cents)} />
        <Stat label={due < 0 ? 'Credit on account' : 'Amount due'} value={usd(Math.abs(due))} strong tone={due > 0 ? 'warn' : due < 0 ? 'ok' : undefined} />
      </div>
      <div className="overflow-x-auto rounded-corgi border border-line bg-white">
        <table className="w-full text-left">
          <thead>
            <tr className="text-[12px] text-muted border-b border-line">
              <th className="py-2.5 pl-4 pr-2 font-medium">Date</th>
              <th className="py-2.5 px-2 font-medium">Type</th>
              <th className="py-2.5 px-2 font-medium">Description</th>
              <th className="py-2.5 px-2 font-medium text-right">Amount</th>
              <th className="py-2.5 px-2 font-medium text-right">Balance</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {data.rows.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-muted">No activity yet.</td></tr>}
            {data.rows.map((r) => {
              const t = TYPE_LABEL[r.type]
              const isOpen = open === r.id
              return (
                <Fragment key={r.id}>
                  <tr className={`border-b border-line/70 hover:bg-canvas/70 cursor-pointer ${r.type === 'ADJUSTMENT' ? 'bg-tint/30' : ''}`} onClick={() => setOpen(isOpen ? null : r.id)}>
                    <td className="py-3 pl-4 pr-2 whitespace-nowrap text-body">{fdate(r.date)}</td>
                    <td className="py-3 px-2"><Badge tone={t.tone}>{t.label}</Badge></td>
                    <td className="py-3 px-2">{r.description}</td>
                    <td className={`py-3 px-2 text-right money ${r.amount_cents < 0 ? 'text-ok' : ''}`}>{r.amount_cents > 0 ? '+' : ''}{usd(r.amount_cents)}</td>
                    <td className="py-3 px-2 text-right money text-body">{usd(r.running_balance_cents)}</td>
                    <td className="pr-3 text-muted"><Icon name={isOpen ? 'expand_less' : 'expand_more'} /></td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-canvas/60 border-b border-line/70">
                      <td colSpan={6} className="px-4 py-3">
                        <div className="text-[13px] space-y-1.5">
                          <p><span className="font-medium">How this was calculated: </span>{r.explanation}</p>
                          <p className="text-body">
                            <span className="font-medium text-ink">Caused by: </span>
                            {r.action.summary} — {r.action.actor}, {fdatetime(r.action.at)}
                            {audience === 'broker' && <span className="text-muted"> · action #{r.action.id} · ledger entry #{r.id}</span>}
                          </p>
                          {r.action.note && <p className="text-body"><span className="font-medium text-ink">Reason: </span>{r.action.note}</p>}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      {data.payment_attempts.length > 0 && (
        <div className="mt-4">
          <h3 className="text-[16px] mb-2">Payment attempts not on the statement</h3>
          <ul className="space-y-1.5">
            {data.payment_attempts.map((p) => (
              <li key={p.id} className="flex items-center gap-2 text-[13px] text-body">
                <Badge tone={p.status === 'failed' ? 'bad' : 'warn'}>{p.status}</Badge>
                <span className="money">{usd(p.amount_cents)}</span>
                <span>{fdatetime(p.created_at)}</span>
                {p.failure_reason && <span className="text-danger">— {p.failure_reason}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, strong, tone }: { label: string; value: string; strong?: boolean; tone?: 'warn' | 'ok' }) {
  const bg = tone === 'warn' ? 'bg-tint border-orange/30' : tone === 'ok' ? 'bg-ok/10 border-ok/30' : 'bg-white border-line'
  return (
    <div className={`rounded-corgi border px-4 py-3 ${bg}`}>
      <div className="text-[12px] text-body">{label}</div>
      <div className={`money ${strong ? 'text-[22px]' : 'text-[18px]'}`}>{value}</div>
    </div>
  )
}
