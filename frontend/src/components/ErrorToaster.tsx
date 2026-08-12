import { useEffect, useState } from 'react'
import { onApiError, type ApiError } from '../api/client'

interface Toast { id: number; err: ApiError }

export default function ErrorToaster() {
  const [toasts, setToasts] = useState<Toast[]>([])

  useEffect(() => onApiError((err) => {
    // 401s are handled by the auth flow, not worth toasting.
    if (err.status === 401) return
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, err }])
    // User errors auto-dismiss; admin faults stay until dismissed.
    if (err.kind === 'user') {
      setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 7000)
    }
  }), [])

  if (!toasts.length) return null
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-96 flex-col gap-2">
      {toasts.map(({ id, err }) => {
        const admin = err.kind === 'admin'
        return (
          <div key={id}
               className={`pointer-events-auto rounded-lg border-l-4 bg-white p-3 shadow-lg ${
                 admin ? 'border-red-600' : 'border-brand'}`}>
            <div className="flex items-start justify-between gap-2">
              <p className={`font-mono text-[10px] uppercase tracking-wide ${
                admin ? 'text-red-600' : 'text-brand'}`}>
                {admin ? 'System fault — admin' : 'Action needed'}
              </p>
              <button className="text-steel hover:text-navy"
                      onClick={() => setToasts((t) => t.filter((x) => x.id !== id))}>
                ×
              </button>
            </div>
            <p className="mt-1 text-sm text-navy">{err.message}</p>
            {err.remedy && (
              <p className="mt-1 text-xs text-steel">{err.remedy}</p>
            )}
          </div>
        )
      })}
    </div>
  )
}
