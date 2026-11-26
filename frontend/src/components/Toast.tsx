import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '../lib/api'

type Kind = 'error' | 'success' | 'info'
interface ToastItem { id: number; kind: Kind; message: string }
interface ToastApi { error: (e: unknown) => void; success: (m: string) => void; info: (m: string) => void }

// Lets code outside React (query cache, window handlers, error boundary) raise a toast.
let sink: ((e: unknown) => void) | null = null
const IGNORED = /ResizeObserver loop|AbortError|Script error\.?$/
export function reportError(e: unknown) {
  const msg = e instanceof Error ? e.message : String(e ?? '')
  if (!msg || IGNORED.test(msg) || (e instanceof DOMException && e.name === 'AbortError')) return
  sink?.(e)
}

const Ctx = createContext<ToastApi>({ error: () => {}, success: () => {}, info: () => {} })
export const useToast = () => useContext(Ctx)

const GENERIC = new Set(['Bad Gateway', 'Service Unavailable', 'Gateway Timeout', 'Internal Server Error'])

/** Turn raw transport errors into something a customer can act on. Messages the backend wrote on
 *  purpose (e.g. "Nothing is due on this policy") are shown as they are. */
export function friendly(e: unknown): string {
  if (e instanceof ApiError) {
    if (GENERIC.has(e.message)) return "We couldn't reach the server. Please try again in a moment."
    return e.message
  }
  if (e instanceof TypeError) return "We couldn't reach the server. Check your connection and try again."
  return e instanceof Error ? e.message : String(e)
}

const STYLE: Record<Kind, { icon: string; bar: string; tone: string }> = {
  error: { icon: 'error', bar: 'bg-danger', tone: 'text-danger' },
  success: { icon: 'check_circle', bar: 'bg-ok', tone: 'text-ok' },
  info: { icon: 'info', bar: 'bg-orange', tone: 'text-orange-deep' },
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const next = useRef(1)
  const dismiss = useCallback((id: number) => setItems((l) => l.filter((t) => t.id !== id)), [])
  const push = useCallback((kind: Kind, message: string) => {
    setItems((l) => (l.some((t) => t.message === message) ? l : [...l.slice(-3), { id: next.current++, kind, message }]))
  }, [])
  const api = useMemo<ToastApi>(() => ({
    error: (e) => push('error', friendly(e)),
    success: (m) => push('success', m),
    info: (m) => push('info', m),
  }), [push])
  useEffect(() => {
    sink = api.error
    // Last line of defence: anything nobody caught still reaches the user as a toast.
    const rej = (ev: PromiseRejectionEvent) => reportError(ev.reason)
    const err = (ev: ErrorEvent) => reportError(ev.error ?? ev.message)
    window.addEventListener('unhandledrejection', rej)
    window.addEventListener('error', err)
    return () => { sink = null; window.removeEventListener('unhandledrejection', rej); window.removeEventListener('error', err) }
  }, [api])
  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="fixed top-4 right-4 z-[70] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
        {items.map((t) => <ToastCard key={t.id} item={t} onClose={() => dismiss(t.id)} />)}
      </div>
    </Ctx.Provider>
  )
}

function ToastCard({ item, onClose }: { item: ToastItem; onClose: () => void }) {
  const s = STYLE[item.kind]
  useEffect(() => { const h = setTimeout(onClose, item.kind === 'error' ? 8000 : 5000); return () => clearTimeout(h) }, [item, onClose])
  return (
    <div role={item.kind === 'error' ? 'alert' : 'status'} className="relative flex items-start gap-2.5 overflow-hidden rounded-corgi border border-line bg-white py-3 pl-4 pr-3 shadow-soft">
      <span className={`absolute inset-y-0 left-0 w-1 ${s.bar}`} />
      <span className={`msr ${s.tone} !text-[20px] mt-px`} aria-hidden>{s.icon}</span>
      <p className="flex-1 text-[14px] leading-snug text-ink">{item.message}</p>
      <button onClick={onClose} aria-label="Dismiss" className="text-muted hover:text-ink cursor-pointer"><span className="msr !text-[18px]" aria-hidden>close</span></button>
    </div>
  )
}
