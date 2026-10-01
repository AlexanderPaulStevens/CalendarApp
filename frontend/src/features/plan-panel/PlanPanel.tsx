import type { PlanSnapshot } from '../../lib/types'
import { formatHours } from '../../lib/dates'

interface Props {
  plan: PlanSnapshot
}

export function PlanPanel({ plan }: Props) {
  const w = plan.week_summary
  const progress =
    w.goal_hours > 0
      ? Math.min(100, ((w.completed_hours + w.planned_hours) / w.goal_hours) * 100)
      : 0

  return (
    <aside className="flex h-full min-h-0 flex-col gap-6 overflow-auto border-l border-[var(--color-line)] bg-[var(--color-surface)]/50 px-4 py-4">
      <section>
        <h2 className="font-[family-name:var(--font-display)] text-2xl">This week</h2>
        <p className="mt-2 text-sm">
          {formatHours(w.completed_hours)} done · {formatHours(w.planned_hours)} planned
        </p>
        <p className="text-sm text-[var(--color-ink)]/70">
          Remaining {formatHours(w.remaining_hours)} of {formatHours(w.goal_hours)}
          {w.sessions_needed > 0 ? ` · ≥${w.sessions_needed} sessions` : ''}
        </p>
        <div className="mt-3 h-2 overflow-hidden rounded-sm bg-[var(--color-line)]">
          <div
            className="h-full bg-[var(--color-moss-soft)] transition-all ring-1 ring-inset ring-[var(--color-moss-edge)]"
            style={{ width: `${progress}%` }}
          />
        </div>
        {!w.feasible && (
          <p className="mt-2 text-xs text-[var(--color-warn)]">
            Weekly target is no longer achievable without changing existing events. Max still
            possible: {formatHours(w.max_possible_hours)}.
          </p>
        )}
        {w.feasible && w.feasible_days > 0 && w.remaining_hours > 0 && (
          <p className="mt-2 text-xs text-[var(--color-ink)]/60">
            {w.feasible_days} day{w.feasible_days === 1 ? '' : 's'} still able to hold a session.
          </p>
        )}
        <p className="mt-3 text-xs text-[var(--color-ink)]/50">
          Scheduling Rules place Auto events on the calendar; edit an Auto event to claim it as
          yours.
        </p>
      </section>

      <section>
        <h3 className="text-sm font-semibold tracking-wide uppercase text-[var(--color-ink)]/60">
          Shopping
        </h3>
        {plan.shopping.length === 0 && (
          <p className="mt-2 text-sm text-[var(--color-ink)]/50">List is clear.</p>
        )}
        <div className="mt-2 space-y-4">
          {Object.entries(
            plan.shopping.reduce<Record<string, typeof plan.shopping>>((acc, line) => {
              const key = line.trip_date ?? 'unscheduled'
              ;(acc[key] ??= []).push(line)
              return acc
            }, {}),
          )
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([tripDate, lines]) => (
              <div key={tripDate}>
                <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-rule-shopping-ink)]/70">
                  {tripDate === 'unscheduled'
                    ? 'Unscheduled'
                    : new Date(`${tripDate}T12:00:00`).toLocaleDateString(undefined, {
                        weekday: 'short',
                        day: 'numeric',
                        month: 'short',
                      })}{' '}
                  · {lines.length} item{lines.length === 1 ? '' : 's'}
                </p>
                <ul className="mt-1 space-y-1.5 border-l-2 border-[var(--color-rule-shopping-edge)] pl-2.5">
                  {lines.map((line) => (
                    <li key={line.id} className="text-sm">
                      {line.ingredient} — {line.quantity}
                      {line.unit}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
        </div>
      </section>
    </aside>
  )
}
