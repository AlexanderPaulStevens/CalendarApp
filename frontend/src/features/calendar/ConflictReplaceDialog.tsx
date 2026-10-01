import type { CalendarEvent } from '../../lib/types'
import { parseIso } from '../../lib/dates'

interface Props {
  pending: Record<string, unknown>
  overlapping: CalendarEvent[]
  onReplace: (ids: string[]) => void
  onKeepBoth: () => void
  onCancel: () => void
}

export function ConflictReplaceDialog({
  pending,
  overlapping,
  onReplace,
  onKeepBoth,
  onCancel,
}: Props) {
  const title = String(pending.title ?? 'New event')
  const single = overlapping.length === 1

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-[var(--color-ink)]/25 p-4 backdrop-blur-[1px]">
      <div className="w-full max-w-md rounded-2xl border border-[var(--color-line)] bg-[var(--color-paper)] p-5 shadow-xl">
        <h2 className="font-[family-name:var(--font-display)] text-2xl">Replace overlapping event?</h2>
        <p className="mt-2 text-sm opacity-80">
          <span className="font-medium">{title}</span> overlaps{' '}
          {single ? 'this event' : `${overlapping.length} events`}:
        </p>
        <ul className="mt-3 space-y-2 text-sm">
          {overlapping.map((e) => (
            <li
              key={e.id}
              className="rounded-lg border border-[var(--color-line)] bg-[var(--color-surface)] px-3 py-2"
            >
              <div className="font-medium">{e.title}</div>
              <div className="text-xs opacity-60">
                {parseIso(e.start).toLocaleString([], {
                  weekday: 'short',
                  hour: '2-digit',
                  minute: '2-digit',
                })}{' '}
                –{' '}
                {parseIso(e.end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </li>
          ))}
        </ul>
        <div className="mt-5 flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-primary"
            onClick={() => onReplace(overlapping.map((e) => e.id))}
          >
            {single ? 'Replace' : 'Replace all'}
          </button>
          <button type="button" className="btn-ghost border border-[var(--color-line)]" onClick={onKeepBoth}>
            Keep both
          </button>
          <button type="button" className="btn-ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
