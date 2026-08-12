import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ErrorToaster from './components/ErrorToaster'
import Login from './pages/Login'
import ProjectMap from './pages/ProjectMap'
import Projects from './pages/Projects'
import Register from './pages/Register'
import StreetMatching from './pages/StreetMatching'
import { AuthProvider, useAuth } from './auth/AuthContext'

function Protected({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="p-8 text-sm text-steel">Loading…</div>
  return user ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ErrorToaster />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Protected><Layout /></Protected>}>
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/:id" element={<ProjectMap />} />
            <Route path="/projects/:id/register" element={<Register />} />
            <Route path="/projects/:id/street-matching" element={<StreetMatching />} />
          </Route>
          <Route path="*" element={<Navigate to="/projects" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
