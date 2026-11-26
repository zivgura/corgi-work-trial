import { fdatetime } from '../lib/format'
import type { TimelineItem } from '../lib/api'
import { Icon } from './ui'

const ICON: Record<string, string> = {
  ISSUE_POLICY: 'description', ADD_COVERAGE: 'add_circle', CORRECT_EFFECTIVE_DATE: 'edit_calendar',
  CANCEL_POLICY: 'block', PAYMENT_STARTED: 'credit_card', PAYMENT_SUCCEEDED: 'check_circle',
  PAYMENT_FAILED: 'error', REFUND_ISSUED: 'currency_exchange',
}

export function Timeline({ items }: { items: TimelineItem[] }) {
  return (
    <ol className="relative border-l border-line ml-3 space-y-5">
      {items.map((a) => (
        <li key={a.id} className="ml-6">
          <span className="absolute -left-[13px] flex h-6 w-6 items-center justify-center rounded-full bg-white border border-line text-orange">
            <Icon name={ICON[a.kind] ?? 'circle'} className="!text-[15px]" />
          </span>
          <div className="text-[14px]">{a.summary}</div>
          <div className="text-[12px] text-muted">{a.actor} · {fdatetime(a.at)}</div>
          {a.note && <div className="text-[13px] text-body mt-0.5">“{a.note}”</div>}
        </li>
      ))}
    </ol>
  )
}
