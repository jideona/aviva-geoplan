import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const NAV = [
  { to: '/projects', label: 'Projects' },
]

export function Wordmark({ light = false }: { light?: boolean }) {
  return (
    <span className="select-none">
      <span className={`font-bold tracking-[0.18em] ${light ? 'text-white' : 'text-navy'}`}>
        AVIVA
      </span>
      <span className="tracking-[0.12em] text-brand-networx"> networx</span>
    </span>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-pale px-5 py-3">
        <div className="flex items-center gap-8">
          <Link to="/projects"><Wordmark /></Link>
          <nav className="flex gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 text-sm ${
                    isActive ? 'bg-lightgrey text-navy' : 'text-steel hover:text-navy'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <span className="badge bg-lightgrey text-steel">Local dev</span>
          <span className="text-sm text-steel">{user?.email}</span>
          <button
            className="btn-ghost py-1"
            onClick={() => { logout(); navigate('/login') }}
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-auto"><Outlet /></main>
    </div>
  )
}
