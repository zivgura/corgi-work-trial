import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import { useEffect } from 'react'

export function Icon({ name, className = '' }: { name: string; className?: string }) {
  return <span className={`msr ${className}`} aria-hidden>{name}</span>
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'dark' | 'danger'; small?: boolean }
export function Button({ variant = 'primary', small, className = '', ...p }: BtnProps) {
  const base = 'inline-flex items-center justify-center gap-1.5 rounded-corgi font-medium transition disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer'
  const size = small ? 'h-8 px-3 text-[13px]' : 'h-10 px-4 text-sm'
  const v = {
    primary: 'bg-orange text-white hover:bg-orange-deep shadow-[0_2px_0_0_#cc4a00]',
    dark: 'bg-ink text-white hover:bg-dark',
    ghost: 'bg-white text-ink border border-line hover:bg-canvas',
    danger: 'bg-white text-danger border border-danger/40 hover:bg-danger/5',
  }[variant]
  return <button {...p} className={`${base} ${size} ${v} ${className}`} />
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`bg-white border border-line rounded-corgi shadow-soft ${className}`}>{children}</div>
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="block text-[12px] font-medium text-body mb-1">{label}</span>
      {children}
      {hint && <span className="block text-[12px] text-muted mt-1">{hint}</span>}
    </label>
  )
}
const inputCls = 'w-full h-10 rounded-corgi border border-line bg-white px-3 text-sm focus:border-orange'
export function Input(p: InputHTMLAttributes<HTMLInputElement>) { return <input {...p} className={`${inputCls} ${p.className ?? ''}`} /> }
export function Select(p: SelectHTMLAttributes<HTMLSelectElement>) { return <select {...p} className={`${inputCls} ${p.className ?? ''}`} /> }

const tones: Record<string, string> = {
  ok: 'bg-ok/10 text-ok', warn: 'bg-tint text-orange-deep', bad: 'bg-danger/10 text-danger',
  neutral: 'bg-ink/5 text-body', dark: 'bg-ink text-white',
}
export function Badge({ tone = 'neutral', children }: { tone?: keyof typeof tones; children: ReactNode }) {
  return <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[12px] font-medium ${tones[tone]}`}>{children}</span>
}

export function PaymentBadge({ status }: { status: string | null }) {
  if (!status) return <Badge>No payment yet</Badge>
  if (status === 'succeeded') return <Badge tone="ok"><Icon name="check_circle" className="!text-[14px]" /> Paid</Badge>
  if (status === 'pending') return <Badge tone="warn"><Icon name="hourglass_top" className="!text-[14px]" /> Payment pending</Badge>
  if (status === 'failed') return <Badge tone="bad"><Icon name="error" className="!text-[14px]" /> Payment failed</Badge>
  return <Badge>{status}</Badge>
}

export function PolicyStatus({ status }: { status: string }) {
  return status === 'active' ? <Badge tone="ok">Active</Badge> : <Badge tone="neutral">Cancelled</Badge>
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-ink/40 p-4 overflow-auto" onMouseDown={onClose}>
      <div role="dialog" aria-modal aria-label={title} onMouseDown={(e) => e.stopPropagation()}
        className={`bg-white rounded-corgi shadow-soft w-full ${wide ? 'max-w-2xl' : 'max-w-lg'} mt-[8vh]`}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-line">
          <h3 className="text-[20px]">{title}</h3>
          <button onClick={onClose} aria-label="Close" className="text-muted hover:text-ink cursor-pointer"><Icon name="close" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  const msg = error instanceof Error ? error.message : String(error)
  return <div role="alert" className="rounded-corgi bg-danger/10 text-danger px-3 py-2 text-[13px]">{msg}</div>
}

export function PageTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-5">
      <h1 className="text-[32px]">{children}</h1>
      {sub && <p className="text-body mt-1">{sub}</p>}
    </div>
  )
}
