import { useEffect, useState } from 'react'
import { api, type CurrencyReport } from '../api/client'

const COLOURS: Record<string, string> = {
  current: '#00C9A7', ageing: '#4BAADF', stale: '#1A6FA8',
  obsolete: '#0D1B4B', unknown: '#8FA3BF',
}
const ORDER = ['current', 'ageing', 'stale', 'obsolete', 'unknown']

export default function CurrencyPanel({ projectId }: { projectId: string }) {
  const [report, setReport] = useState<CurrencyReport | null>(null)
  useEffect(() => {
    api.currency(projectId).then(setReport).catch(() => {})
  }, [projectId])

  if (!report || report.total === 0) return null
  const pct = (n: number) => (n / report.total) * 100

  return (
    <div className="mt-6 border-t border-lightgrey pt-4">
      <h2 className="label">Data currency</h2>

      <div className="flex h-2 overflow-hidden rounded">
        {ORDER.filter((k) => report.by_currency[k]).map((k) => (
          <div key={k} title={`${report.bands[k]?.label}: ${report.by_currency[k]}`}
               style={{ width: `${pct(report.by_currency[k])}%`,
                        background: COLOURS[k] }} />
        ))}
      </div>

      <div className="mt-2 space-y-0.5 text-xs">
        {ORDER.filter((k) => report.by_currency[k]).map((k) => (
          <div key={k} className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-steel">
              <span className="inline-block h-2 w-2 rounded-sm"
                    style={{ background: COLOURS[k] }} />
              {report.bands[k]?.label ?? k}
            </span>
            <span className="font-mono text-navy">
              {report.by_currency[k].toLocaleString()} ({pct(report.by_currency[k]).toFixed(0)}%)
            </span>
          </div>
        ))}
      </div>

      <div className="card mt-3 p-3 text-xs">
        <div className="flex justify-between">
          <span className="text-steel">Median source age</span>
          <span className="font-mono text-navy">
            {report.median_age_years?.toFixed(1) ?? '—'} yr
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-steel">Oldest record</span>
          <span className="font-mono text-navy">
            {report.oldest_age_years?.toFixed(1) ?? '—'} yr
          </span>
        </div>
        <div className="mt-1 flex justify-between border-t border-lightgrey pt-1">
          <span className="text-steel">Needs field check</span>
          <span className="font-mono text-navy">
            {report.requires_field_check.toLocaleString()} ({report.requires_field_check_pct}%)
          </span>
        </div>
      </div>

      <p className="mt-2 text-xs text-steel">{report.note}</p>

      <a className="btn-primary mt-3 w-full" href={api.walkthroughPack(projectId)}
         onClick={(e) => {
           e.preventDefault()
           void api.download(api.walkthroughPack(projectId),
                             'walkthrough_pack.xlsx')
         }}>
        Field walkthrough pack
      </a>
      <p className="mt-1 text-xs text-steel">
        Streets to name, areas ranked by staleness, and the unit-count sheet.
      </p>
    </div>
  )
}
