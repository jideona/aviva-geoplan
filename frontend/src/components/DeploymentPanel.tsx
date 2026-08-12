import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import {
  api, TASK_AREAS, TASK_STATUSES, type DeploymentAssignee, type DeploymentSummary,
  type DeploymentTask, type TaskArea, type TaskStatus,
} from '../api/client'
import MediaGallery from './MediaGallery'

const AREA_LABEL: Record<TaskArea, string> = {
  ug_network: 'UG Network', access: 'Access', other: 'Other',
}
const STATUS_LABEL: Record<TaskStatus, string> = {
  not_started: 'Not started', in_progress: 'In progress', blocked: 'Blocked', done: 'Done',
}
const STATUS_COLOR: Record<TaskStatus, string> = {
  not_started: '#8FA3BF', in_progress: '#4BAADF', blocked: '#DC2626', done: '#00C9A7',
}

interface Props { projectId: string }

const emptyDraft = {
  title: '', area: 'other' as TaskArea, status: 'not_started' as TaskStatus,
  assignee_id: '' as string, start_date: '', end_date: '', updates: '', issues: '',
}

export default function DeploymentPanel({ projectId }: Props) {
  const { user, can } = useAuth()
  const manage = can('task:manage')

  const [tasks, setTasks] = useState<DeploymentTask[]>([])
  const [summary, setSummary] = useState<DeploymentSummary | null>(null)
  const [assignees, setAssignees] = useState<DeploymentAssignee[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [areaFilter, setAreaFilter] = useState<TaskArea | 'all'>('all')
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all')

  const [openId, setOpenId] = useState<string | null>(null)
  const [draft, setDraft] = useState(emptyDraft)
  const [saving, setSaving] = useState(false)

  const [showCreate, setShowCreate] = useState(false)
  const [createDraft, setCreateDraft] = useState(emptyDraft)
  const [creating, setCreating] = useState(false)

  async function reload() {
    setError(null)
    try {
      const [t, s] = await Promise.all([
        api.deploymentTasks(projectId), api.deploymentSummary(projectId),
      ])
      setTasks(t.tasks); setSummary(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load deployment tasks.')
    } finally { setLoading(false) }
  }

  useEffect(() => {
    void reload()
    if (manage) api.deploymentAssignees(projectId).then((r) => setAssignees(r.users)).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  const visible = useMemo(() => tasks.filter((t) =>
    (areaFilter === 'all' || t.area === areaFilter) &&
    (statusFilter === 'all' || t.status === statusFilter)), [tasks, areaFilter, statusFilter])

  function openRow(t: DeploymentTask) {
    setOpenId(openId === t.id ? null : t.id)
    setDraft({
      title: t.title, area: t.area, status: t.status,
      assignee_id: t.assignee?.id ?? '',
      start_date: t.start_date ?? '', end_date: t.end_date ?? '',
      updates: t.updates ?? '', issues: t.issues ?? '',
    })
  }

  function canEditRow(t: DeploymentTask): 'full' | 'own' | 'none' {
    if (manage) return 'full'
    if (user && t.assignee?.id === user.id) return 'own'
    return 'none'
  }

  async function saveEdit(t: DeploymentTask) {
    const mode = canEditRow(t)
    if (mode === 'none') return
    setSaving(true); setError(null)
    try {
      const payload = mode === 'full'
        ? { title: draft.title.trim(), area: draft.area, status: draft.status,
            assignee_id: draft.assignee_id || null,
            start_date: draft.start_date || null, end_date: draft.end_date || null,
            updates: draft.updates || null, issues: draft.issues || null }
        : { status: draft.status, updates: draft.updates || null, issues: draft.issues || null }
      const updated = await api.updateDeploymentTask(projectId, t.id, payload)
      setTasks((prev) => prev.map((x) => (x.id === t.id ? updated : x)))
      setOpenId(null)
      void api.deploymentSummary(projectId).then(setSummary).catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save this task.')
    } finally { setSaving(false) }
  }

  async function remove(t: DeploymentTask) {
    if (!confirm(`Delete "${t.title}"? This cannot be undone.`)) return
    setError(null)
    try {
      await api.deleteDeploymentTask(projectId, t.id)
      setTasks((prev) => prev.filter((x) => x.id !== t.id))
      setOpenId(null)
      void api.deploymentSummary(projectId).then(setSummary).catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete this task.')
    }
  }

  async function create() {
    if (createDraft.title.trim().length < 2) return
    setCreating(true); setError(null)
    try {
      const created = await api.createDeploymentTask(projectId, {
        title: createDraft.title.trim(), area: createDraft.area, status: createDraft.status,
        assignee_id: createDraft.assignee_id || null,
        start_date: createDraft.start_date || null, end_date: createDraft.end_date || null,
        updates: createDraft.updates || null, issues: createDraft.issues || null,
      })
      setTasks((prev) => [...prev, created])
      setCreateDraft(emptyDraft); setShowCreate(false)
      void api.deploymentSummary(projectId).then(setSummary).catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create the task.')
    } finally { setCreating(false) }
  }

  if (loading) return <p className="mt-4 text-xs text-steel">Loading deployment tasks…</p>

  return (
    <div>
      {summary && summary.total > 0 && (
        <div className="mb-3 rounded bg-lightgrey/60 px-2.5 py-2">
          <div className="flex items-center justify-between">
            <p className="font-mono text-[10px] uppercase tracking-wide text-brand">
              {summary.total} tasks · {summary.percent_done}% done
            </p>
            {(summary.overdue > 0 || summary.open_issues > 0) && (
              <p className="font-mono text-[10px] text-red-600">
                {summary.overdue > 0 && `${summary.overdue} overdue`}
                {summary.overdue > 0 && summary.open_issues > 0 && ' · '}
                {summary.open_issues > 0 && `${summary.open_issues} open issue${summary.open_issues === 1 ? '' : 's'}`}
              </p>
            )}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-steel">
            {(Object.keys(STATUS_LABEL) as TaskStatus[]).map((s) => (
              <span key={s}>
                <span className="mr-1 inline-block h-2 w-2 rounded-sm"
                      style={{ background: STATUS_COLOR[s] }} />
                {STATUS_LABEL[s]} {summary.by_status[s] ?? 0}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-1">
        {(['all', ...TASK_AREAS] as const).map((a) => (
          <button key={a}
                  className={`flex-1 rounded px-1.5 py-1 font-mono text-[10px] uppercase ${
                    areaFilter === a ? 'bg-navy text-white' : 'bg-lightgrey text-steel'}`}
                  onClick={() => setAreaFilter(a)}>
            {a === 'all' ? 'all' : AREA_LABEL[a]}
          </button>
        ))}
      </div>
      <div className="mt-1 flex gap-1">
        {(['all', ...TASK_STATUSES] as const).map((s) => (
          <button key={s}
                  className={`flex-1 rounded px-1.5 py-1 font-mono text-[10px] uppercase ${
                    statusFilter === s ? 'bg-navy text-white' : 'bg-lightgrey text-steel'}`}
                  onClick={() => setStatusFilter(s)}>
            {s === 'all' ? 'all' : STATUS_LABEL[s].split(' ')[0]}
          </button>
        ))}
      </div>

      {error && (
        <p className="mt-2 rounded border-l-2 border-brand bg-lightgrey px-2 py-1 text-xs">
          {error}
        </p>
      )}

      {manage && (
        <button className="btn-ghost mt-2 w-full py-1 text-[11px]"
                onClick={() => setShowCreate((v) => !v)}>
          {showCreate ? 'Cancel' : '+ New task'}
        </button>
      )}

      {showCreate && (
        <div className="mt-1 rounded border border-lightgrey p-2">
          <input className="field py-1 text-xs" placeholder="Task title"
                 value={createDraft.title}
                 onChange={(e) => setCreateDraft((d) => ({ ...d, title: e.target.value }))} />
          <div className="mt-1 flex gap-1">
            <select className="field py-1 text-xs" value={createDraft.area}
                    onChange={(e) => setCreateDraft((d) => ({ ...d, area: e.target.value as TaskArea }))}>
              {TASK_AREAS.map((a) => <option key={a} value={a}>{AREA_LABEL[a]}</option>)}
            </select>
            <select className="field py-1 text-xs" value={createDraft.status}
                    onChange={(e) => setCreateDraft((d) => ({ ...d, status: e.target.value as TaskStatus }))}>
              {TASK_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
            </select>
          </div>
          <select className="field mt-1 py-1 text-xs" value={createDraft.assignee_id}
                  onChange={(e) => setCreateDraft((d) => ({ ...d, assignee_id: e.target.value }))}>
            <option value="">Unassigned</option>
            {assignees.map((a) => (
              <option key={a.id} value={a.id}>{a.full_name}</option>
            ))}
          </select>
          <div className="mt-1 flex gap-1">
            <input type="date" className="field py-1 text-xs" value={createDraft.start_date}
                   onChange={(e) => setCreateDraft((d) => ({ ...d, start_date: e.target.value }))} />
            <input type="date" className="field py-1 text-xs" value={createDraft.end_date}
                   onChange={(e) => setCreateDraft((d) => ({ ...d, end_date: e.target.value }))} />
          </div>
          <button className="btn-primary mt-1 w-full py-1 text-xs disabled:opacity-40"
                  disabled={creating || createDraft.title.trim().length < 2}
                  onClick={() => void create()}>
            {creating ? 'Adding…' : 'Add task'}
          </button>
        </div>
      )}

      <div className="mt-2 max-h-[28rem] space-y-1 overflow-auto">
        {visible.map((t) => {
          const open = openId === t.id
          const editMode = canEditRow(t)
          return (
            <div key={t.id}
                 className={`rounded border px-2 py-1.5 ${
                   open ? 'border-brand bg-lightgrey' : 'border-transparent hover:bg-lightgrey'}`}>
              <button className="w-full text-left" onClick={() => openRow(t)}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-xs text-navy">{t.title}</span>
                  <span className="font-mono text-[9px] uppercase text-steel">
                    {AREA_LABEL[t.area]}
                  </span>
                </div>
                <div className="mt-0.5 flex items-center justify-between">
                  <span className="flex items-center gap-1 text-[10px] text-steel">
                    <span className="inline-block h-2 w-2 rounded-sm"
                          style={{ background: STATUS_COLOR[t.status] }} />
                    {STATUS_LABEL[t.status]}
                    {t.assignee && ` · ${t.assignee.full_name}`}
                  </span>
                  <span className="flex items-center gap-1">
                    {t.overdue && <span className="font-mono text-[9px] text-red-600">overdue</span>}
                    {t.has_issue && <span className="font-mono text-[9px] text-red-600">⚠ issue</span>}
                  </span>
                </div>
              </button>

              {open && (
                <div className="mt-2 border-t border-pale pt-2">
                  {t.entity_type && t.entity_id && (
                    <MediaGallery projectId={projectId} entityType={t.entity_type}
                                  entityId={t.entity_id} hideWhenEmpty={false} compact />
                  )}
                  {editMode === 'full' && (
                    <>
                      <input className="field py-1 text-xs" value={draft.title}
                             onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))} />
                      <div className="mt-1 flex gap-1">
                        <select className="field py-1 text-xs" value={draft.area}
                                onChange={(e) => setDraft((d) => ({ ...d, area: e.target.value as TaskArea }))}>
                          {TASK_AREAS.map((a) => <option key={a} value={a}>{AREA_LABEL[a]}</option>)}
                        </select>
                        <select className="field py-1 text-xs" value={draft.assignee_id}
                                onChange={(e) => setDraft((d) => ({ ...d, assignee_id: e.target.value }))}>
                          <option value="">Unassigned</option>
                          {assignees.map((a) => <option key={a.id} value={a.id}>{a.full_name}</option>)}
                        </select>
                      </div>
                      <div className="mt-1 flex gap-1">
                        <input type="date" className="field py-1 text-xs" value={draft.start_date}
                               onChange={(e) => setDraft((d) => ({ ...d, start_date: e.target.value }))} />
                        <input type="date" className="field py-1 text-xs" value={draft.end_date}
                               onChange={(e) => setDraft((d) => ({ ...d, end_date: e.target.value }))} />
                      </div>
                    </>
                  )}

                  <select className="field mt-1 py-1 text-xs" value={draft.status}
                          onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value as TaskStatus }))}>
                    {TASK_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                  </select>
                  <textarea className="field mt-1 h-14 text-xs" placeholder="Updates"
                            value={draft.updates}
                            onChange={(e) => setDraft((d) => ({ ...d, updates: e.target.value }))} />
                  <textarea className="field mt-1 h-14 text-xs" placeholder="Issues (blank = none)"
                            value={draft.issues}
                            onChange={(e) => setDraft((d) => ({ ...d, issues: e.target.value }))} />

                  <div className="mt-1 flex gap-1">
                    <button className="btn-primary flex-1 py-1 text-xs disabled:opacity-40"
                            disabled={saving || (editMode === 'full' && draft.title.trim().length < 2)}
                            onClick={() => void saveEdit(t)}>
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                    <button className="btn-ghost py-1 text-xs" onClick={() => setOpenId(null)}>
                      Cancel
                    </button>
                    {editMode === 'full' && (
                      <button className="rounded px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                              onClick={() => void remove(t)}>
                        Delete
                      </button>
                    )}
                  </div>
                  {editMode === 'own' && (
                    <p className="mt-1 text-[10px] text-steel">
                      Assigned to you — you can update status, updates and issues.
                    </p>
                  )}
                </div>
              )}
            </div>
          )
        })}
        {visible.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-steel">
            {tasks.length === 0
              ? (manage ? 'No tasks yet — add the first one above.' : 'No tasks yet.')
              : 'Nothing matches this filter.'}
          </p>
        )}
      </div>
    </div>
  )
}
