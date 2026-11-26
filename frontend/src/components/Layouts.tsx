import { NavLink, Navigate, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { Badge, Icon } from './ui'
import type { Role } from '../lib/api'

export function Guard({ role }: { role: Role }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="p-10 text-muted">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== role) return <Navigate to={user.role === 'broker' ? '/broker' : '/portal'} replace />
  return role === 'broker' ? <BrokerLayout /> : <PortalLayout />
}

function Mode() {
  const { config } = useAuth()
  if (!config) return null
  return (
    <div className="flex gap-1.5">
      <Badge tone={config.payment_provider === 'stripe' ? 'ok' : 'warn'}>Payments: {config.payment_provider === 'stripe' ? 'Stripe test' : 'simulated'}</Badge>
      <Badge tone={config.email_provider === 'resend' ? 'ok' : 'warn'}>Email: {config.email_provider === 'resend' ? 'Resend' : 'simulated'}</Badge>
    </div>
  )
}

const navCls = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2.5 rounded-corgi px-3 py-2 text-[14px] ${isActive ? 'bg-orange text-white' : 'text-[#d9d9d9] hover:bg-dark'}`

function BrokerLayout() {
  const { user, logout } = useAuth(); const nav = useNavigate()
  return (
    <div className="min-h-full flex">
      <aside className="w-60 shrink-0 bg-ink text-white flex flex-col p-4 sticky top-0 h-screen">
        <div className="flex items-center gap-1.5 text-orange font-semibold text-[20px] px-2 mb-1"><Icon name="pets" className="!text-[24px]" /> corgi</div>
        <div className="text-[12px] text-[#9a9a9a] px-2 mb-6">Broker console</div>
        <nav className="space-y-1">
          <NavLink to="/broker" end className={navCls}><Icon name="description" /> Policies</NavLink>
          <NavLink to="/broker/new" className={navCls}><Icon name="add_circle" /> Issue policy</NavLink>
          <NavLink to="/broker/customers" className={navCls}><Icon name="groups" /> Customers</NavLink>
          <NavLink to="/broker/integrations" className={navCls}><Icon name="hub" /> Integrations</NavLink>
        </nav>
        <div className="mt-auto text-[13px]">
          <div className="px-2 text-[#d9d9d9]">{user?.name}</div>
          <button onClick={() => { logout(); nav('/login') }} className="px-2 mt-1 text-[#9a9a9a] hover:text-white cursor-pointer">Sign out</button>
        </div>
      </aside>
      <main className="flex-1 min-w-0">
        <div className="flex justify-end px-8 pt-4"><Mode /></div>
        <div className="px-8 pb-12 pt-2 max-w-6xl"><Outlet /></div>
      </main>
    </div>
  )
}

function PortalLayout() {
  const { user, logout } = useAuth(); const nav = useNavigate()
  return (
    <div className="min-h-full">
      <header className="bg-white border-b border-line">
        <div className="max-w-5xl mx-auto flex items-center justify-between px-5 h-14">
          <NavLink to="/portal" className="flex items-center gap-1.5 text-orange font-semibold text-[20px]"><Icon name="pets" className="!text-[24px]" /> corgi</NavLink>
          <div className="flex items-center gap-4"><Mode /><span className="text-body text-[13px]">{user?.name}</span>
            <button onClick={() => { logout(); nav('/login') }} className="text-[13px] text-muted hover:text-ink cursor-pointer">Sign out</button></div>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-5 py-8"><Outlet /></main>
    </div>
  )
}
