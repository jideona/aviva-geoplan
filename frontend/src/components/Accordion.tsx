import type { ReactNode } from 'react'

interface SectionProps {
  id: string
  title: string
  subtitle?: ReactNode
  open: boolean
  onToggle: (id: string) => void
  children: ReactNode
}

/**
 * One collapsible group in the left rail. Deliberately dumb — open/close
 * state lives in the parent (AccordionRail) so the "which section is open"
 * decision (computed default vs. user click) stays in one place.
 */
export function AccordionSection(
  { id, title, subtitle, open, onToggle, children }: SectionProps,
) {
  return (
    <div className="border-b border-lightgrey last:border-b-0">
      <button
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left hover:bg-lightgrey/60"
        onClick={() => onToggle(id)}
        aria-expanded={open}
      >
        <span className="min-w-0 flex-1">
          <span className="block text-sm text-navy">{title}</span>
          {subtitle && (
            <span className="block truncate text-[11px] text-steel">{subtitle}</span>
          )}
        </span>
        <span className={`font-mono text-[10px] text-midgrey transition-transform ${
          open ? 'rotate-180' : ''}`}>
          ▾
        </span>
      </button>
      {open && (
        <div className="px-3 pb-3">{children}</div>
      )}
    </div>
  )
}

interface RailProps {
  children: ReactNode
}

/**
 * The left rail shell: a bordered white column the AccordionSections live
 * inside. Replaces the old flat, ever-growing <aside> panel stack.
 */
export function AccordionRail({ children }: RailProps) {
  return (
    <div className="flex h-full w-96 shrink-0 flex-col overflow-y-auto border-r
                     border-lightgrey bg-white">
      {children}
    </div>
  )
}
