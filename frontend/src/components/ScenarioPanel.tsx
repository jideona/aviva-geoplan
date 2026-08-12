import { useState } from 'react'
import { api, type ScenarioResult } from '../api/client'

interface Scenario {
  label: string
  fat_port_count: number
  spare_port_ratio: number
  max_drop_length_m: number
  min_premises_per_fat: number
  max_fdh_distribution_m: number
  noc_anchored: boolean
}

const DEFAULTS: Scenario[] = [
  { label: 'A — current rules', fat_port_count: 16, spare_port_ratio: 0.20,
    max_drop_length_m: 150, min_premises_per_fat: 4,
    max_fdh_distribution_m: 2000, noc_anchored: true },
  { label: 'B — 24-port FATs', fat_port_count: 24, spare_port_ratio: 0.20,
    max_drop_length_m: 150, min_premises_per_fat: 4,
    max_fdh_distribution_m: 2000, noc_anchored: true },
  { label: 'C — 24-port + 180 m', fat_port_count: 24, spare_port_ratio: 0.20,
    max_drop_length_m: 180, min_premises_per_fat: 4,
    max_fdh_distribution_m: 2000, noc_anchored: true },
]

const km = (m: number) => `${(m / 1000).toFixed(1)} km`

/**
 * Dry-run comparison of up to three rule sets. Nothing is persisted — the
 * committed design stays exactly as it is; this only answers "what would the
 * quantities be if the rules were different?".
 */
export default function ScenarioPanel({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(false)
  const [scenarios, setScenarios] = useState<Scenario[]>(DEFAULTS)
  const [results, setResults] = useState<ScenarioResult[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function set(i: number, field: keyof Scenario, value: string | boolean) {
    setScenarios((prev) => prev.map((s, j) => {
      if (j !== i) return s
      if (field === 'label') return { ...s, label: String(value) }
      if (field === 'noc_anchored') return { ...s, noc_anchored: Boolean(value) }
      const n = Number(value)
      return Number.isFinite(n) ? { ...s, [field]: n } : s
    }))
  }

  async function run() {
    setBusy(true); setError(null); setResults(null)
    try {
      const payload = scenarios.map((s) => ({
        ...s,
        // spare ratio entered as %, API takes a fraction
        spare_port_ratio: s.spare_port_ratio > 1
          ? s.spare_port_ratio / 100 : s.spare_port_ratio,
      }))
      const r = await api.designScenarios(projectId, payload)
      setResults(r.scenarios)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Comparison failed.')
    } finally { setBusy(false) }
  }

  const fields: [keyof Scenario, string][] = [
    ['fat_port_count', 'FAT ports'],
    ['spare_port_ratio', 'Spare ratio'],
    ['max_drop_length_m', 'Max drop m'],
    ['min_premises_per_fat', 'Min prem/FAT'],
    ['max_fdh_distribution_m', 'FDH reach m'],
  ]

  const rows: [string, (r: ScenarioResult) => string][] = [
    ['FATs', (r) => String(r.fats)],
    ['FDHs', (r) => String(r.fdhs)],
    ['Splitters', (r) => String(r.splitters)],
    ['Avg FAT util', (r) => `${r.avg_fat_utilisation_pct.toFixed(0)}%`],
    ['Trench', (r) => km(r.trench_m)],
    ['Feeder cable', (r) => km(r.feeder_cable_m)],
    ['Dist. cable', (r) => km(r.distribution_cable_m)],
    ['Drop cable', (r) => km(r.drop_cable_m)],
    ['Chambers', (r) => String(r.chambers.handholes + r.chambers.manholes_at_fdh
                               + r.chambers.manholes_on_runs)],
    ['Unassigned bldgs', (r) => String(r.unassigned_buildings)],
    ['Warnings', (r) => String(r.warnings)],
  ]

  return (
    <div className="card mt-2 p-3">
      <button className="flex w-full items-center justify-between"
              onClick={() => setOpen((v) => !v)}>
        <span className="font-mono text-[10px] uppercase tracking-wide text-brand">
          Scenario compare
        </span>
        <span className="font-mono text-[10px] text-steel">{open ? '−' : '+'}</span>
      </button>

      {open && (
        <>
          <p className="mt-1 text-[10px] text-steel">
            Dry-run up to three rule sets. The committed design is untouched —
            re-run the design with a winning rule set to adopt it.
          </p>

          <table className="mt-2 w-full text-[10px]">
            <thead>
              <tr>
                <th className="text-left font-mono text-steel">RULE</th>
                {scenarios.map((s, i) => (
                  <th key={i} className="px-0.5">
                    <input className="field w-full py-0.5 text-center text-[10px]"
                           value={s.label}
                           onChange={(e) => set(i, 'label', e.target.value)} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fields.map(([f, label]) => (
                <tr key={f}>
                  <td className="py-0.5 text-steel">{label}</td>
                  {scenarios.map((s, i) => (
                    <td key={i} className="px-0.5">
                      <input className="field w-full py-0.5 text-center text-[10px]"
                             inputMode="decimal"
                             value={String(s[f])}
                             onChange={(e) => set(i, f, e.target.value)} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          <button className="btn-primary mt-2 w-full py-1.5 text-xs disabled:opacity-40"
                  onClick={() => void run()} disabled={busy}>
            {busy ? 'Planning + routing 3 designs… (may take a minute)'
                  : 'Run comparison'}
          </button>
          {error && <p className="mt-1 text-[10px] text-red-700">{error}</p>}

          {results && (
            <table className="mt-2 w-full text-[10px]">
              <thead>
                <tr>
                  <th className="text-left font-mono text-steel">RESULT</th>
                  {results.map((r, i) => (
                    <th key={i} className="px-1 text-center font-mono text-navy">
                      {r.label.split('—')[0].trim()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(([label, get]) => {
                  const vals = results.map((r) => (r.error ? '—' : get(r)))
                  return (
                    <tr key={label} className="border-t border-lightgrey">
                      <td className="py-0.5 text-steel">{label}</td>
                      {vals.map((v, i) => (
                        <td key={i} className="px-1 text-center font-mono text-navy">
                          {v}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
          {results?.some((r) => r.error) && (
            <p className="mt-1 text-[10px] text-red-700">
              {results.filter((r) => r.error)
                      .map((r) => `${r.label}: ${r.error}`).join(' · ')}
            </p>
          )}
        </>
      )}
    </div>
  )
}
