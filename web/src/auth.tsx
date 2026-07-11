import { createContext, useContext, useState, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

interface AuthCtx { token: string | null; setToken: (t: string | null) => void }

const Ctx = createContext<AuthCtx>({ token: null, setToken: () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(() => localStorage.getItem('token'))
  const setToken = (t: string | null) => {
    if (t) localStorage.setItem('token', t)
    else localStorage.removeItem('token')
    setTok(t)
  }
  return <Ctx.Provider value={{ token, setToken }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)

export function RequireAuth({ children }: { children: ReactNode }) {
  const { token } = useAuth()
  return token ? <>{children}</> : <Navigate to="/login" replace />
}
