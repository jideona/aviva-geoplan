interface Props {
  buildings: number | null
  streets: number | null
  designFeatures: number | null
  zoom: number
  lng: number
  lat: number
}

/**
 * Slim bar under the map: routine counts and position, nothing that needs
 * attention. Exceptions (fetch errors, stale design, map errors) stay as
 * their own loud banners above the map rather than folding in here — an
 * exception buried in a status line is easy to miss.
 */
export default function StatusStrip({ buildings, streets, designFeatures, zoom, lng, lat }: Props) {
  const fmt = (n: number | null) => (n === null ? '…' : n < 0 ? 'FAIL' : n.toLocaleString())
  return (
    <div className="flex items-center gap-4 border-t border-lightgrey bg-navy
                     px-3 py-1 font-mono text-[10px] text-pale">
      <span>{fmt(buildings)} buildings</span>
      <span>{fmt(streets)} streets</span>
      <span>{fmt(designFeatures)} design features</span>
      <span className="ml-auto">zoom {zoom.toFixed(1)}</span>
      <span>{lat.toFixed(5)}, {lng.toFixed(5)}</span>
    </div>
  )
}
