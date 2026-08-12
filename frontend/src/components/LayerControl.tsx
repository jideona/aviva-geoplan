/**
 * Layer groups, not individual MapLibre layers. Geometry and its labels are
 * separate entries deliberately: on a dense map the usual need is to keep a
 * feature visible while silencing its text.
 */
export interface LayerGroup {
  key: string
  label: string
  layers: string[]
  isLabel?: boolean
}

export const LAYER_GROUPS: LayerGroup[] = [
  { key: 'satellite', label: 'Satellite imagery (Esri)', layers: ['satellite'] },
  { key: 'boundary', label: 'District boundary',
    layers: ['boundary-fill', 'boundary-line'] },
  { key: 'parcels', label: 'Estate perimeters',
    layers: ['parcel-fill', 'parcel-line', 'parcel-selected'] },
  { key: 'parcelLabels', label: 'Estate names',
    layers: ['parcel-label'], isLabel: true },
  { key: 'buildings', label: 'Buildings',
    layers: ['buildings-fill', 'buildings-line'] },
  { key: 'streets', label: 'Streets',
    layers: ['streets-line', 'streets-selected'] },
  { key: 'streetLabels', label: 'Street names',
    layers: ['streets-label'], isLabel: true },
  { key: 'streetCodes', label: 'Provisional codes',
    layers: ['streets-code'], isLabel: true },
  { key: 'zones', label: 'Serving zones',
    layers: ['zone-extent', 'zone-outline', 'zone-selected'] },
  { key: 'fdhs', label: 'FDH cabinets', layers: ['fdh-point'] },
  { key: 'fdhLabels', label: 'FDH codes', layers: ['fdh-label'], isLabel: true },
  { key: 'noc', label: 'NOC / OLT',
    layers: ['noc-halo', 'noc-point', 'noc-label'] },
  { key: 'routes', label: 'Cable routes',
    layers: ['route-feeder', 'route-feeder-case', 'route-distribution',
             'route-distribution-case', 'route-noc', 'route-noc-label'] },
  { key: 'areas', label: 'Design areas (N/S/E/W)',
    layers: ['area-line', 'area-label'] },
  { key: 'ring', label: 'Feeder ring (resilience option)',
    layers: ['ring-case', 'ring-line'] },
  { key: 'corridors', label: 'Drop corridors',
    layers: ['corridor-line'] },
  { key: 'drops', label: 'Drops (serviceability)',
    layers: ['drop-case', 'drop-line', 'drop-unserved'] },
  { key: 'fats', label: 'FAT positions', layers: ['fat-point'] },
  { key: 'fatLabels', label: 'FAT codes',
    layers: ['fat-label'], isLabel: true },
  { key: 'manholes', label: 'Manholes / chambers',
    layers: ['manhole-point'] },
]

export const DEFAULT_VISIBILITY: Record<string, boolean> =
  Object.fromEntries(LAYER_GROUPS.map(
    (g) => [g.key,
            g.key !== 'satellite' && g.key !== 'drops' && g.key !== 'ring'
            && g.key !== 'areas']))

interface Props {
  visibility: Record<string, boolean>
  onChange: (next: Record<string, boolean>) => void
}

/**
 * Renders bare — no collapsible chrome of its own. It used to float over the
 * map as its own panel with a "Layers" header/toggle; it now lives inside
 * the Design section's Layer tab, so the accordion supplies that framing.
 */
export default function LayerControl({ visibility, onChange }: Props) {
  const set = (key: string, on: boolean) =>
    onChange({ ...visibility, [key]: on })

  const setMany = (keys: string[], on: boolean) =>
    onChange({ ...visibility, ...Object.fromEntries(keys.map((k) => [k, on])) })

  const labelKeys = LAYER_GROUPS.filter((g) => g.isLabel).map((g) => g.key)
  const anyLabelOn = labelKeys.some((k) => visibility[k])
  const allKeys = LAYER_GROUPS.map((g) => g.key)

  return (
    <div>
      <div className="mb-1.5 flex gap-1">
        <button className="flex-1 rounded bg-navy px-1 py-0.5 font-mono text-[9px] uppercase text-white hover:bg-navy-mid"
                onClick={() => setMany(allKeys, true)}>
          select all
        </button>
        <button className="flex-1 rounded bg-lightgrey px-1 py-0.5 font-mono text-[9px] uppercase text-steel hover:text-navy"
                onClick={() => setMany(allKeys, false)}>
          deselect all
        </button>
      </div>
      <div className="mb-1.5 flex gap-1 border-b border-lightgrey pb-1.5">
        <button className="flex-1 rounded bg-lightgrey px-1 py-0.5 font-mono text-[9px] uppercase text-steel hover:text-navy"
                onClick={() => setMany(labelKeys, !anyLabelOn)}>
          {anyLabelOn ? 'hide all text' : 'show all text'}
        </button>
        <button className="flex-1 rounded bg-lightgrey px-1 py-0.5 font-mono text-[9px] uppercase text-steel hover:text-navy"
                onClick={() => onChange({ ...DEFAULT_VISIBILITY })}>
          reset
        </button>
      </div>

      {LAYER_GROUPS.map((g) => (
        <label key={g.key}
               className="flex cursor-pointer items-center gap-2 py-0.5">
          <input type="checkbox" className="h-3 w-3"
                 checked={visibility[g.key] ?? true}
                 onChange={(e) => set(g.key, e.target.checked)} />
          <span className={`text-[11px] ${
            g.isLabel ? 'text-steel' : 'text-navy'}`}>
            {g.label}
          </span>
        </label>
      ))}
    </div>
  )
}
