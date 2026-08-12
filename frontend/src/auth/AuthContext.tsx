import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, hasSession, setTokens, type User } from '../api/client'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  can: (permission: string) => boolean
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!hasSession()) { setLoading(false); return }
    api.me().then(setUser).catch(() => setTokens(null, null)).finally(() => setLoading(false))
  }, [])

  async function login(email: string, password: string) {
    const tokens = await api.login(email, password)
    setTokens(tokens.access_token, tokens.refresh_token)
    setUser(await api.me())
  }

  function logout() {
    setTokens(null, null)
    setUser(null)
  }

  const can = (permission: string) => user?.permissions.includes(permission) ?? false

  return <Ctx.Provider value={{ user, loading, login, logout, can }}>{children}</Ctx.Provider>
}

export function useAuth() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
