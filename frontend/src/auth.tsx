import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, tokenStore, type AppConfig, type User } from './lib/api'

interface Ctx { user: User | null; loading: boolean; config: AppConfig | null; login: (e: string, p: string) => Promise<User>; logout: () => void }
const AuthCtx = createContext<Ctx>(null as unknown as Ctx)
export const useAuth = () => useContext(AuthCtx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [config, setConfig] = useState<AppConfig | null>(null)

  useEffect(() => {
    api<AppConfig>('/config').then(setConfig).catch(() => undefined)
    if (!tokenStore.get()) { setLoading(false); return }
    api<User>('/me').then(setUser).catch(() => tokenStore.clear()).finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ token: string; user: User }>('/auth/login', { body: { email, password } })
    tokenStore.set(r.token)
    setUser(r.user)
    return r.user
  }, [])
  const logout = useCallback(() => { tokenStore.clear(); setUser(null) }, [])
  return <AuthCtx.Provider value={{ user, loading, config, login, logout }}>{children}</AuthCtx.Provider>
}
