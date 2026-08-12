import { useEffect, useState } from 'react'
import { api, type MediaItem } from '../api/client'

interface Props {
  projectId: string
  entityType: string
  entityId: string
  /** Render nothing at all when there's no media — the default, so this
   * component is safe to drop into any inspector/panel without adding
   * clutter to entities that were never photographed. Set false to show an
   * explicit "no photos" hint instead (used in review-focused lists). */
  hideWhenEmpty?: boolean
  compact?: boolean
}

/**
 * Thumbnail strip for whatever survey media (photos/videos) is attached to a
 * GeoPlan entity — a manhole, a building, a street, a recorded street, a
 * deployment task's linked entity. One component so "click to see the
 * photos" behaves identically everywhere it appears (map inspector, survey
 * panels, project management).
 */
export default function MediaGallery({ projectId, entityType, entityId,
  hideWhenEmpty = true, compact = false }: Props) {
  const [items, setItems] = useState<MediaItem[] | null>(null)
  const [open, setOpen] = useState<MediaItem | null>(null)

  useEffect(() => {
    let cancelled = false
    setItems(null)
    api.media(projectId, entityType, entityId)
      .then((r) => { if (!cancelled) setItems(r.media) })
      .catch(() => { if (!cancelled) setItems([]) })
    return () => { cancelled = true }
  }, [projectId, entityType, entityId])

  if (items === null) {
    return hideWhenEmpty ? null : (
      <p className="mt-1 text-[10px] text-steel">Loading photos…</p>
    )
  }
  if (items.length === 0) {
    return hideWhenEmpty ? null : (
      <p className="mt-1 text-[10px] text-steel">No photos or videos captured yet.</p>
    )
  }

  const size = compact ? 'h-12 w-12' : 'h-16 w-16'

  return (
    <div>
      <p className="mt-2 font-mono text-[10px] uppercase text-brand">
        {items.length} photo{items.length === 1 ? '' : 's'}/video{items.length === 1 ? '' : 's'}
      </p>
      <div className="mt-1 flex flex-wrap gap-1">
        {items.map((m) => (
          <button key={m.id} type="button"
                  className={`relative shrink-0 overflow-hidden rounded ${size} bg-lightgrey`}
                  title={m.caption ?? undefined}
                  onClick={() => setOpen(m)}>
            {m.kind === 'video' ? (
              <div className="flex h-full w-full items-center justify-center text-steel">
                <span className="text-lg">▶</span>
              </div>
            ) : m.view_url ? (
              <img src={m.view_url} alt={m.caption ?? 'survey photo'}
                   className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center
                              text-[8px] text-steel">no preview</div>
            )}
          </button>
        ))}
      </div>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center
                        bg-navy-midnight/80 p-6"
             onClick={() => setOpen(null)}>
          <div className="max-h-full max-w-3xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between text-white">
              <span className="text-xs">{open.caption ?? ''}</span>
              <button className="ml-4 text-lg leading-none" onClick={() => setOpen(null)}
                      aria-label="Close">✕</button>
            </div>
            {open.kind === 'video' ? (
              <video src={open.view_url ?? undefined} controls autoPlay
                     className="max-h-[80vh] max-w-full rounded" />
            ) : (
              <img src={open.view_url ?? undefined} alt={open.caption ?? 'survey photo'}
                   className="max-h-[80vh] max-w-full rounded object-contain" />
            )}
            {open.captured_at && (
              <p className="mt-1 font-mono text-[10px] text-pale">
                captured {new Date(open.captured_at).toLocaleString()}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
