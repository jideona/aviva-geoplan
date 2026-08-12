import { useEffect, useState } from 'react'
import { api, type Design, type DesignRuleInput, type DesignZone } from '../api/client'

const RATIOS = [8, 16, 32, 64, 128]

const DEFAULTS: DesignRuleInput = {
  split_stage: 'single',
  fdh_split_ratio: 32,
  fat_port_count: 16,
  spare_port_ratio: 0.20,
  max_drop_length_m: 150,
  min_premises_per_fat: 4,
  assumed_premises_per_building: 1,
  max_fat_road_offset_m: 25,
  noc_anchored: false,
  max_fdh_distribution_m: 2000,
}

interface Props {
  projectId: string
  onDesignChanged: () => void
  onZoneSelect: (code: string | null) => void
  selectedZone: string | null
  onDesignLoaded?: (design: Design | null) => void
}

export default function DesignPanel(
  { projectId, onDesignChanged, onZoneSelect, selectedZone, onDesignLoaded }: Props,
) {
  const [rules, setRules] = useState<DesignRuleInput>(DEFAULTS)
  const [design, setDesign] = useState<Design | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showZones, setShowZones] = useState(false)
  const [aerialShare, setAerialShare] = useState('0')
  const [dropMsg, setDropMsg] = useState<string | null>(null)

  async function saveAerialShare() {
    setDropMsg(null)
    try {
      const r = await api.setAerialShare(projectId,
        Math.min(100, Math.max(0, Number(aerialShare))) / 100)
      setDropMsg(`Assumption saved — ${(r.aerial_drop_share * 100).toFixed(0)}% `
        + 'of unflagged drops price as aerial in the SOM/BOQ.')
    } catch (e) {
      setDropMsg(e instanceof Error ? e.message : 'Could not save.')
    }
  }

  async function setZoneDeployment(d: 'aerial' | 'underground' | null) {
    if (!selectedZone) return
    setDropMsg(null)
    try {
      const r = await api.setZoneDropDeployment(projectId, selectedZone, d)
      setDropMsg(`${r.zone_code}: ${r.buildings_updated} building(s) set to `
        + `${d ?? 'unset (assumption applies)'}.`)
    } catch (e) {
      setDropMsg(e instanceof Error ? e.message : 'Could not update zone.')
    }
  }

  const load = () => api.currentDesign(projectId).then(setDesign).catch(() => {})
  useEffect(() => { void load() }, [projectId])

  useEffect(() => {
    if (design?.rules && Object.keys(design.rules).length) {
      setRules((r) => ({ ...r, ...design.rules } as DesignRuleInput))
    }
  }, [design?.design_run_id])

  // Reports (the pack, schematics and area exports) lives in its own rail
  // section and needs to know whether a design exists — hand the loaded
  // design up rather than duplicating the currentDesign() fetch there.
  useEffect(() => { onDesignLoaded?.(design) }, [design, onDesignLoaded])

  async function run() {
    setBusy(true); setError(null)
    try {
      await api.runDesign(projectId, rules)
      await load()
      onDesignChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Design run failed.')
    } finally { setBusy(false) }
  }

  // Passive FAT: usable ports come from the physical drop-port count.
  const usable = Math.max(1, Math.floor(
    rules.fat_port_count * (1 - rules.spare_port_ratio)))
  const s = design?.summary ?? {}
  const zones = design?.zones ?? []

  return (
    <div className="mt-6 border-t border-lightgrey pt-4">
      <h2 className="label">Network design</h2>

      <p className="mb-2 rounded bg-lightgrey px-2 py-1 text-[10px] text-navy">
        Single-stage 1:32 at the FDH, passive FAT — built from stock, no 1:4
        purchase.
      </p>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="label">FDH split</label>
          <select className="field py-1 text-xs" value={rules.fdh_split_ratio}
                  onChange={(e) => setRules({ ...rules,
                    fdh_split_ratio: Number(e.target.value) })}>
            {RATIOS.map((r) => <option key={r} value={r}>1:{r}</option>)}
          </select>
        </div>
        <div>
          <label className="label">FAT drop ports</label>
          <select className="field py-1 text-xs" value={rules.fat_port_count}
                  onChange={(e) => setRules({ ...rules,
                    fat_port_count: Number(e.target.value) })}>
            {[8, 12, 16, 24].map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Spare ports</label>
          <select className="field py-1 text-xs" value={rules.spare_port_ratio}
                  onChange={(e) => setRules({ ...rules,
                    spare_port_ratio: Number(e.target.value) })}>
            {[0, 0.1, 0.2, 0.25, 0.3, 0.4].map((v) => (
              <option key={v} value={v}>{Math.round(v * 100)}%</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Max drop (m)</label>
          <input type="number" className="field py-1 text-xs" min={20} max={1000}
                 value={rules.max_drop_length_m}
                 onChange={(e) => setRules({ ...rules,
                   max_drop_length_m: Number(e.target.value) })} />
        </div>
        <div>
          <label className="label">Premises assumed</label>
          <input type="number" className="field py-1 text-xs" min={1} max={20}
                 value={rules.assumed_premises_per_building}
                 onChange={(e) => setRules({ ...rules,
                   assumed_premises_per_building: Number(e.target.value) })} />
        </div>
      </div>

      <p className="mt-1 font-mono text-[10px] text-steel">
        {usable} usable ports per FAT
      </p>

      <label className="mt-2 flex items-center gap-2 text-xs text-navy">
        <input type="checkbox" checked={rules.noc_anchored ?? false}
               onChange={(e) => setRules({ ...rules, noc_anchored: e.target.checked,
                 max_fdh_distribution_m: e.target.checked ? 250 : 2000 })} />
        Pilot mode — anchor FDHs to the NOC, tight clusters for connectorised reach
      </label>

      <button className="btn-primary mt-2 w-full" onClick={run} disabled={busy}>
        {busy ? 'Running…' : design?.design_run_id ? 'Re-run design' : 'Run design'}
      </button>

      {error && (
        <p className="mt-2 rounded border-l-2 border-brand bg-lightgrey px-2 py-1 text-xs">
          {error}
        </p>
      )}

      {design?.design_run_id && (
        <>
          <div className="card mt-3 p-3 text-xs">
            <Row label="FATs required" value={s.zones} strong />
            <Row label="Buildings served" value={s.buildings_served} />
            <Row label="Premises served" value={s.premises_served} />
            <Row label="Unreachable" value={s.unassigned_buildings} />
            <Row label="Longest drop" value={`${s.max_drop_m} m`} />
            <Row label="Avg per zone" value={s.avg_zone_premises} />
            <p className="mt-1 border-t border-lightgrey pt-1 font-mono text-[10px] text-steel">
              engine {design.engine_version} · {design.ran_at?.slice(0, 16).replace('T', ' ')}
            </p>
          </div>

          <div className="mt-2 border-t border-lightgrey pt-2">
            <p className="font-mono text-[10px] uppercase tracking-wide text-brand">
              Drop deployment — aerial / underground
            </p>
            <div className="mt-1 flex items-center gap-1 text-[11px]">
              <span className="text-steel">Unflagged drops:</span>
              <input className="field w-14 py-0.5 text-center text-[11px]"
                     inputMode="numeric" value={aerialShare}
                     onChange={(e) => setAerialShare(e.target.value)} />
              <span className="text-steel">% aerial</span>
              <button className="btn-ghost ml-auto py-0.5 text-[10px]"
                      onClick={() => void saveAerialShare()}>Save</button>
            </div>
            <p className="mt-0.5 text-[10px] text-steel">
              At 0% every unflagged drop prices as underground. Explicit flags
              (below, or per building from field survey) always win.
            </p>
            {selectedZone ? (
              <div className="mt-1 flex items-center gap-1">
                <span className="font-mono text-[10px] text-navy">{selectedZone}:</span>
                <button className="btn-ghost flex-1 py-0.5 text-[10px]"
                        onClick={() => void setZoneDeployment('aerial')}>Aerial</button>
                <button className="btn-ghost flex-1 py-0.5 text-[10px]"
                        onClick={() => void setZoneDeployment('underground')}>Underground</button>
                <button className="btn-ghost py-0.5 text-[10px]"
                        onClick={() => void setZoneDeployment(null)}>Clear</button>
              </div>
            ) : (
              <p className="mt-1 text-[10px] italic text-steel">
                Click a FAT on the map to set a whole zone's drop type.
              </p>
            )}
            {dropMsg && (
              <p className="mt-1 border-t border-lightgrey pt-1 text-[10px] text-navy">
                {dropMsg}
              </p>
            )}
          </div>

          {design.fdhs && design.fdhs.length > 0 && (
            <div className="card mt-2 p-3 text-xs">
              <div className="flex justify-between font-mono text-[11px]">
                <span className="text-steel">FDHs</span>
                <span className="text-navy">
                  {design.fdhs.length} × {design.fdhs[0].splitters} splitters
                </span>
              </div>
              <p className="mt-1 text-[10px] text-steel">
                {design.fdhs.length} FDHs at {design.fdhs[0].capacity} premises
                each. Your 6-FDH pilot (18 splitters) is the zero-purchase first
                phase; full coverage needs {design.fdhs.length} FDHs.
              </p>
            </div>
          )}

          {design.warnings.map((w) => (
            <p key={w} className="mt-2 rounded border-l-2 border-brand bg-lightgrey px-2 py-1.5 text-[11px] text-navy">
              {w}
            </p>
          ))}

          <button className="btn-ghost mt-2 w-full py-1 text-xs"
                  onClick={() => setShowZones(!showZones)}>
            {showZones ? 'Hide' : 'Show'} {zones.length} zones
          </button>

          {showZones && (
            <div className="mt-1 max-h-72 space-y-1 overflow-auto">
              {zones.map((z) => (
                <ZoneRow key={z.id} zone={z}
                         selected={selectedZone === z.zone_code}
                         onClick={() => onZoneSelect(
                           selectedZone === z.zone_code ? null : z.zone_code)} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ZoneRow({ zone, selected, onClick }:
                 { zone: DesignZone; selected: boolean; onClick: () => void }) {
  const util = zone.utilisation_pct
  return (
    <button onClick={onClick}
            className={`w-full rounded px-2 py-1 text-left text-xs ${
              selected ? 'bg-lightgrey ring-1 ring-brand' : 'hover:bg-lightgrey'}`}>
      <div className="flex justify-between">
        <span className="font-mono text-[10px] text-brand">{zone.zone_code}</span>
        <span className="font-mono text-[10px] text-steel">
          {zone.premises_count}/{zone.usable_ports} ports
        </span>
      </div>
      <div className="mt-0.5 flex items-center gap-2">
        <div className="h-1 flex-1 overflow-hidden rounded bg-lightgrey">
          <div className="h-full"
               style={{ width: `${Math.min(100, util)}%`,
                        background: util > 90 ? '#1A6FA8' : '#00C9A7' }} />
        </div>
        <span className="font-mono text-[10px] text-steel">{util.toFixed(0)}%</span>
      </div>
      <div className="mt-0.5 flex justify-between text-[10px] text-steel">
        <span>{zone.building_count} bldg · drop {zone.max_drop_m.toFixed(0)} m</span>
        {zone.warnings.length > 0 && <span className="text-brand">⚠ review</span>}
      </div>
    </button>
  )
}

function Row({ label, value, strong }:
             { label: string; value: unknown; strong?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-steel">{label}</span>
      <span className={strong ? 'font-mono text-navy' : 'font-mono text-steel'}>
        {typeof value === 'number' ? value.toLocaleString() : String(value ?? '—')}
      </span>
    </div>
  )
}
