import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, type NewProject, type Project } from '../api/client'
import { useAuth } from '../auth/AuthContext'

export default function Projects() {
  const { can } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<NewProject>({
    name: '', district: '', state: 'FCT', city: 'Abuja', metric_crs_epsg: 32632,
  })

  const reload = () =>
    api.listProjects().then(setProjects)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))

  useEffect(() => { void reload() }, [])

  async function create(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await api.createProject(form)
      setCreating(false)
      setForm({ name: '', district: '', state: 'FCT', city: 'Abuja', metric_crs_epsg: 32632 })
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the project.')
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl text-navy">Projects</h1>
          <p className="text-sm text-steel">Geographic projects in your organisation.</p>
        </div>
        {can('project:create') && (
          <button className="btn-primary" onClick={() => setCreating((v) => !v)}>
            {creating ? 'Cancel' : 'New project'}
          </button>
        )}
      </div>

      {error && (
        <p className="mb-4 rounded border-l-2 border-brand bg-lightgrey px-3 py-2 text-sm">
          {error}
        </p>
      )}

      {creating && (
        <form onSubmit={create} className="card mb-6 grid grid-cols-2 gap-4 p-5">
          <div>
            <label className="label">Project name</label>
            <input required className="field" value={form.name}
                   onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <label className="label">District</label>
            <input required className="field" placeholder="Wuye" value={form.district}
                   onChange={(e) => setForm({ ...form, district: e.target.value })} />
          </div>
          <div>
            <label className="label">City</label>
            <input className="field" value={form.city ?? ''}
                   onChange={(e) => setForm({ ...form, city: e.target.value })} />
          </div>
          <div>
            <label className="label">Metric CRS (EPSG)</label>
            <select className="field" value={form.metric_crs_epsg}
                    onChange={(e) => setForm({ ...form, metric_crs_epsg: Number(e.target.value) })}>
              <option value={32632}>32632 — UTM 32N (FCT default)</option>
              <option value={26392}>26392 — Minna / Nigeria Mid Belt</option>
            </select>
            <p className="mt-1 text-xs text-steel">
              Geometry is stored in EPSG:4326. This is used for measurement only.
            </p>
          </div>
          <div className="col-span-2">
            <button className="btn-primary" type="submit">Create project</button>
          </div>
        </form>
      )}

      {loading ? (
        <p className="text-sm text-steel">Loading…</p>
      ) : projects.length === 0 ? (
        <div className="card p-10 text-center">
          <p className="text-steel">No projects yet.</p>
        </div>
      ) : (
        <div className="card divide-y divide-lightgrey">
          {projects.map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`}
                  className="flex items-center justify-between px-5 py-4 hover:bg-lightgrey">
              <div>
                <div className="flex items-center gap-3">
                  <span className="text-navy">{p.name}</span>
                  <span className="badge bg-lightgrey text-steel">{p.code_prefix}</span>
                  <span className="badge bg-navy text-white">{p.status}</span>
                </div>
                <p className="mt-0.5 text-sm text-steel">
                  {[p.district, p.city, p.state].filter(Boolean).join(' · ')}
                  {' — '}{p.project_type.toUpperCase()} / {p.network_technology.toUpperCase()}
                </p>
              </div>
              <div className="text-right font-mono text-xs text-steel">
                {p.has_boundary
                  ? <span className="text-brand">{p.boundary_area_sqkm?.toFixed(2)} km²</span>
                  : <span className="text-midgrey">no boundary</span>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
