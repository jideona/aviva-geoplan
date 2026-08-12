import { useRef, useState } from 'react'
import { api, StockComparisonLine, StockUploadResult } from '../api/client'

interface Props {
  projectId: string
  hasDesign: boolean
  // Grabs a PNG data URL of exactly what's on screen right now (pan/zoom/
  // layers as the user left them) for the Word report's aerial view. Returns
  // null if the map hasn't rendered a first frame yet.
  captureAerial: () => string | null
}

/**
 * Design pack, schematics and per-area exports — split out of DesignPanel
 * so "generate/tune the design" and "download what came out of it" are two
 * different places, matching Design vs. Reports in the rail.
 */
export default function ReportsPanel({ projectId, hasDesign, captureAerial }: Props) {
  const [dl, setDl] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [wordDl, setWordDl] = useState(false)
  const [wordError, setWordError] = useState<string | null>(null)

  const stockFileRef = useRef<HTMLInputElement>(null)
  const [stockUploading, setStockUploading] = useState(false)
  const [stockUploadResult, setStockUploadResult] = useState<StockUploadResult | null>(null)
  const [stockError, setStockError] = useState<string | null>(null)
  const [comparisonLoading, setComparisonLoading] = useState(false)
  const [comparison, setComparison] = useState<StockComparisonLine[] | null>(null)
  const [comparisonWarnings, setComparisonWarnings] = useState<string[]>([])

  async function downloadPack() {
    setDl(true); setError(null)
    try {
      await api.download(api.designPackUrl(projectId), 'network_design_pack.xlsx')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed.')
    } finally { setDl(false) }
  }

  async function downloadWordReport() {
    setWordDl(true); setWordError(null)
    try {
      // Whatever's on screen right now — pan/zoom/satellite toggle as the
      // user left it. null just means no aerial image gets embedded; the
      // rest of the report still generates.
      const aerial = captureAerial()
      await api.wordReport(projectId, aerial, 'network_design_report.docx')
    } catch (err) {
      setWordError(err instanceof Error ? err.message : 'Export failed.')
    } finally { setWordDl(false) }
  }

  async function onStockFileChosen(file: File) {
    setStockUploading(true); setStockError(null); setStockUploadResult(null)
    try {
      const result = await api.uploadStock(file)
      setStockUploadResult(result)
      setComparison(null)          // stale after a new upload — force a reload
    } catch (err) {
      setStockError(err instanceof Error ? err.message : 'Upload failed.')
    } finally {
      setStockUploading(false)
      if (stockFileRef.current) stockFileRef.current.value = ''
    }
  }

  async function loadComparison() {
    setComparisonLoading(true); setStockError(null)
    try {
      const result = await api.stockComparison(projectId)
      setComparison(result.stock_comparison)
      setComparisonWarnings(result.warnings)
    } catch (err) {
      setStockError(err instanceof Error ? err.message : 'Could not load stock comparison.')
    } finally { setComparisonLoading(false) }
  }

  const stockSection = (
    <div className="mt-2 border-t border-lightgrey pt-2">
      <p className="font-mono text-[10px] uppercase tracking-wide text-brand">
        Warehouse stock
      </p>
      <p className="mt-0.5 text-[10px] text-steel">
        Shared across your organisation's projects — upload once, every
        project's Stock Comparison uses the same snapshot. Uploading REPLACES
        the current stock, it doesn't merge with it.
      </p>
      <input ref={stockFileRef} type="file" accept=".csv,.xlsx,.xlsm" className="hidden"
             onChange={(e) => { const f = e.target.files?.[0]; if (f) void onStockFileChosen(f) }} />
      <button className="btn-ghost mt-1 w-full py-1 font-mono text-[10px] disabled:opacity-40"
              onClick={() => stockFileRef.current?.click()} disabled={stockUploading}>
        {stockUploading ? 'Uploading…' : 'Upload stock sheet (.csv / .xlsx)'}
      </button>
      {stockUploadResult && (
        <p className="mt-1 text-[10px] text-navy">
          {stockUploadResult.inserted} stock lines loaded
          {stockUploadResult.replaced > 0 && ` (replaced ${stockUploadResult.replaced} previous)`}.
          {stockUploadResult.warnings.length > 0 && (
            <span className="block text-amber-600">
              {stockUploadResult.warnings.join(' ')}
            </span>
          )}
        </p>
      )}
      {stockError && (
        <p className="mt-1 rounded border-l-2 border-brand bg-lightgrey px-2 py-1 text-[10px]">
          {stockError}
        </p>
      )}

      {hasDesign && (
        <>
          <button className="btn-ghost mt-2 w-full py-1 font-mono text-[10px] disabled:opacity-40"
                  onClick={() => void loadComparison()} disabled={comparisonLoading}>
            {comparisonLoading ? 'Comparing…' : 'View stock vs. design requirement'}
          </button>
          {comparisonWarnings.length > 0 && (
            <p className="mt-1 text-[10px] text-amber-600">{comparisonWarnings.join(' ')}</p>
          )}
          {comparison && (
            <div className="mt-1 max-h-64 overflow-y-auto">
              {Object.entries(
                comparison.reduce<Record<string, StockComparisonLine[]>>((acc, l) => {
                  (acc[l.section] ??= []).push(l); return acc
                }, {})
              ).map(([section, lines]) => (
                <div key={section} className="mt-1">
                  <p className="font-mono text-[9px] uppercase tracking-wide text-steel">{section}</p>
                  {lines.map((l, i) => (
                    <div key={i} className="flex items-center gap-1 text-[10px]">
                      <span className="flex-1 truncate text-navy" title={l.item}>{l.item}</span>
                      <span className="text-steel">{l.required}{l.uom}</span>
                      {l.in_stock === null ? (
                        <span className="w-16 text-right italic text-steel">no data</span>
                      ) : (
                        <span className={`w-16 text-right ${
                          l.shortfall ? 'font-semibold text-amber-600' : 'text-teal'}`}>
                          {l.shortfall ? `buy ${l.shortfall}` : 'covered'}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )

  if (!hasDesign) {
    return (
      <div>
        <p className="text-[11px] text-steel">
          No design run yet — the design pack, schematics and area exports
          become available once you run a design under Design.
        </p>
        {stockSection}
      </div>
    )
  }

  return (
    <div>
      <button className="btn-primary w-full py-1.5 text-xs disabled:opacity-40"
              onClick={() => void downloadPack()} disabled={dl}>
        {dl ? 'Building pack…' : 'Download design pack — report · SOM · BOQ · port schedules (.xlsx)'}
      </button>

      {error && (
        <p className="mt-2 rounded border-l-2 border-brand bg-lightgrey px-2 py-1 text-xs">
          {error}
        </p>
      )}

      <button className="btn-primary mt-2 w-full py-1.5 text-xs disabled:opacity-40"
              onClick={() => void downloadWordReport()} disabled={wordDl}>
        {wordDl ? 'Building report…' : 'Export full report (.docx) — incl. aerial view + diagrams'}
      </button>
      <p className="mt-1 text-[10px] text-steel">
        Captures whatever's on screen right now as the aerial view — position,
        zoom and layers (e.g. satellite) as you like before exporting.
      </p>

      {wordError && (
        <p className="mt-2 rounded border-l-2 border-brand bg-lightgrey px-2 py-1 text-xs">
          {wordError}
        </p>
      )}

      <div className="mt-3 border-t border-lightgrey pt-2">
        <p className="font-mono text-[10px] uppercase tracking-wide text-brand">
          Schematics
        </p>
        {([['Topology diagram', api.designTopologyUrl, 'network_topology'],
           ['Line schematic (SLD)', api.designSchematicUrl, 'network_sld']] as const)
          .map(([label, urlFn, fname]) => (
          <div key={label} className="mt-1 flex items-center gap-1">
            <span className="flex-1 text-[11px] text-navy">{label}</span>
            <button className="btn-ghost px-2 py-0.5 font-mono text-[10px]"
                    onClick={() => void api.openInTab(urlFn(projectId, 'svg'))
                      .catch((e) => setError(e instanceof Error ? e.message : 'Failed'))}>
              SVG
            </button>
            <button className="btn-ghost px-2 py-0.5 font-mono text-[10px]"
                    onClick={() => void api.download(urlFn(projectId, 'png'), `${fname}.png`)
                      .catch((e) => setError(e instanceof Error ? e.message : 'Failed'))}>
              PNG
            </button>
            <button className="btn-ghost px-2 py-0.5 font-mono text-[10px]"
                    onClick={() => void api.download(urlFn(projectId, 'pdf'), `${fname}.pdf`)
                      .catch((e) => setError(e instanceof Error ? e.message : 'Failed'))}>
              PDF
            </button>
          </div>
        ))}
      </div>

      <div className="mt-2 border-t border-lightgrey pt-2">
        <p className="font-mono text-[10px] uppercase tracking-wide text-brand">
          Area export — N / S / E / W
        </p>
        <p className="mt-0.5 text-[10px] text-steel">
          Each FAT (and all its buildings) belongs to one area by bearing
          from the district centre. Turn on the "Design areas" layer under
          Design → Layer to see the split.
        </p>
        <div className="mt-1 flex gap-1">
          {(['north', 'south', 'east', 'west'] as const).map((q) => (
            <button key={q} className="btn-ghost flex-1 py-1 font-mono text-[10px] uppercase"
                    onClick={() => void api.download(api.areaPackUrl(projectId, q),
                        `${q}_area_pack.xlsx`)
                      .catch((e) => setError(e instanceof Error ? e.message : 'Failed'))}>
              {q[0].toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {stockSection}
    </div>
  )
}
