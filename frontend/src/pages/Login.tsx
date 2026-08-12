import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Wordmark } from '../components/Layout'
import { useAuth } from '../auth/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email, password)
      navigate('/projects')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-lightgrey px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="text-2xl"><Wordmark /></div>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.2em] text-steel">
            GeoPlan
          </p>
        </div>
        <form onSubmit={submit} className="card p-6">
          <h1 className="mb-5 text-lg text-navy">Sign in</h1>
          <div className="mb-4">
            <label className="label" htmlFor="email">Email address</label>
            <input id="email" type="email" required autoFocus className="field"
                   value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="mb-5">
            <label className="label" htmlFor="password">Password</label>
            <input id="password" type="password" required className="field"
                   value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && (
            <p className="mb-4 rounded border-l-2 border-brand bg-lightgrey px-3 py-2 text-sm text-navy">
              {error}
            </p>
          )}
          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="mt-6 text-center font-mono text-[10px] text-midgrey">
          AVIVA NETWORX LTD. · ABUJA FCT
        </p>
      </div>
    </div>
  )
}
