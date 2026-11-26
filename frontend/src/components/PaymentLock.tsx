import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

/** While a payment is being processed nothing else on the page may be used: navigating away,
 *  signing out or editing could leave the customer unsure whether they were charged. */
const Ctx = createContext<{ locked: boolean; setLocked: (v: boolean) => void }>({ locked: false, setLocked: () => {} })

export function PaymentLockProvider({ children }: { children: ReactNode }) {
  const [locked, setLocked] = useState(false)
  useEffect(() => {
    if (!locked) return
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', h)
    return () => window.removeEventListener('beforeunload', h)
  }, [locked])
  return <Ctx.Provider value={{ locked, setLocked }}>{children}</Ctx.Provider>
}

export const usePaymentLock = () => useContext(Ctx)

/** Wrap anything that must be unusable (and visibly dimmed) during a payment. `inert` removes it
 *  from clicks, keyboard focus and screen readers. */
export function Lockable({ children, as: Tag = 'div', className = '' }: { children: ReactNode; as?: 'div' | 'header'; className?: string }) {
  const { locked } = usePaymentLock()
  return <Tag inert={locked} className={`${className} transition-opacity ${locked ? 'opacity-40 select-none' : ''}`}>{children}</Tag>
}
