import MediaGallery from './MediaGallery'

export interface InspectorRow { label: string; value: string }

export interface InspectorData {
  title: string
  subtitle?: string
  rows: InspectorRow[]
  note?: string
  actions?: { label: string; onClick: () => void }[]
  /** When set, shows a photo/video strip for this entity — the same survey
   * media captured on the mobile app or imported from a field survey. */
  media?: { projectId: string; entityType: string; entityId: string }
}

interface Props {
  data: InspectorData | null
  onClose: () => void
}

/**
 * Right-side panel that opens when something is selected on the map (a FAT,
 * FDH, street, building or parcel). Replaces the maplibre Popup pattern for
 * those layers, so there is one place to look for "what did I just click"
 * instead of a floating tooltip plus a pile of always-visible edit tools.
 */
export default function InspectorDrawer({ data, onClose }: Props) {
  if (!data) return null
  return (
    <div className="pointer-events-auto absolute right-0 top-0 z-20 h-full w-72
                     border-l border-lightgrey bg-white shadow-lg">
      <div className="flex items-center justify-between border-b border-lightgrey
                       px-3 py-2.5">
        <div className="min-w-0">
          <p className="truncate text-sm text-navy">{data.title}</p>
          {data.subtitle && (
            <p className="truncate text-[11px] text-steel">{data.subtitle}</p>
          )}
        </div>
        <button className="ml-2 shrink-0 text-midgrey hover:text-navy" onClick={onClose}
                aria-label="Close">
          ✕
        </button>
      </div>
      <div className="px-3 py-3">
        <dl className="space-y-1.5 text-[12px]">
          {data.rows.map((r) => (
            <div key={r.label} className="flex justify-between gap-3">
              <dt className="text-steel">{r.label}</dt>
              <dd className="text-right text-navy">{r.value}</dd>
            </div>
          ))}
        </dl>
        {data.media && (
          <MediaGallery projectId={data.media.projectId}
                        entityType={data.media.entityType}
                        entityId={data.media.entityId} />
        )}
        {data.note && (
          <p className="mt-3 rounded border-l-2 border-brand bg-lightgrey px-2.5 py-1.5
                         text-[11px] text-navy">
            {data.note}
          </p>
        )}
        {data.actions && data.actions.length > 0 && (
          <div className="mt-3 space-y-1.5">
            {data.actions.map((a) => (
              <button key={a.label} className="btn-ghost w-full py-1.5 text-[11px]"
                      onClick={a.onClick}>
                {a.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
