import { useEffect, useState } from 'react'
import { api, type Readiness } from '../api/client'

export default function ReadinessBanner(
  { projectId, refreshKey }: { projectId: string; refreshKey: number },
) {
  const [r, setR] = useState<Readiness | null>(null)

  useEffect(() => {
    api.readiness(projectId).then(setR).catch(() => {})
  }, [projectId, refreshKey])

  if (!r || r.complete || !r.next_step) return null
  const s = r.next_step
  return (
    <div className="pointer-events-auto rounded border-l-2 border-teal bg-white px-2.5 py-2 shadow-sm">
      <p className="font-mono text-[10px] uppercase tracking-wide text-brand">
        Next step
      </p>
      <p className="mt-1 text-[11px] text-navy">{s.action}</p>
      {r.blocked_steps.length > 0 && (
        <p className="mt-1 text-[10px] text-steel">
          Waiting on: {r.blocked_steps.map((b) => b.label).join(', ')}
        </p>
      )}
    </div>
  )
}
