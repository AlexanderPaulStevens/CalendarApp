import type { PlanSnapshot } from '../../lib/types'
import { formatHours, parseIso, sameDay } from '../../lib/dates'

interface Props {
  plan: PlanSnapshot
}

function formatClock(d: Date): string {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** Today's prep: keep each Signal until its linked Event starts. */
function todaysPrepSignals(plan: PlanSnapshot) {
  const now = Date.now()
  const today = new Date()
  const byId = new Map(plan.events.map((e) => [e.id, e]))

  return [...plan.signals]
    .filter((s) => {
      const event = byId.get(s.event_id)
      if (!event) return false
      const eventStart = parseIso(event.start)
      if (!sameDay(eventStart, today)) return false
      // Drop once the Event has started.
      return eventStart.getTime() > now
    })
    .sort((a, b) => parseIso(a.at).getTime() - parseIso(b.at).getTime())
}

export function PlanPanel({ plan }: Props) {
  const w = plan.week_summary
  const progress =
    w.goal_hours > 0
      ? Math.min(100, ((w.completed_hours + w.planned_hours) / w.goal_hours) * 100)
      : 0
  const signals = todaysPrepSignals(plan)

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[var(--color-surface)]/70">
      <div className="min-h-0 flex-1 space-y-5 overflow-auto px-4 py-4">
        <section>
          <h2 className="font-[family-name:var(--font-display)] text-[1.65rem] leading-none tracking-tight">
            This week
          </h2>
          <div className="mt-3 rounded-xl border border-[var(--color-rule-exercise-edge)]/70 bg-[var(--color-rule-exercise)]/40 px-3 py-3">
            <div className="flex items-end justify-between gap-2">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-rule-exercise-ink)]/65">
                  Exercise
                </p>
                <p className="mt-1 text-sm text-[var(--color-rule-exercise-ink)]">
                  <span className="font-semibold tabular-nums">
                    {formatHours(w.completed_hours + w.planned_hours)}
                  </span>
                  <span className="opacity-60"> / {formatHours(w.goal_hours)}</span>
                </p>
              </div>
              <p className="text-right text-xs text-[var(--color-rule-exercise-ink)]/70">
                {formatHours(w.completed_hours)} done
                <br />
                {formatHours(w.remaining_hours)} left
              </p>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/55">
              <div
                className="h-full rounded-full bg-[var(--color-rule-exercise-ink)]/75 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
            {w.sessions_needed > 0 && (
              <p className="mt-2 text-xs text-[var(--color-rule-exercise-ink)]/65">
                ≥{w.sessions_needed} session{w.sessions_needed === 1 ? '' : 's'} still needed
              </p>
            )}
            {!w.feasible && (
              <p className="mt-2 text-xs text-[var(--color-warn)]">
                Target no longer fits this week. Max still possible:{' '}
                {formatHours(w.max_possible_hours)}.
              </p>
            )}
          </div>
        </section>

        {signals.length > 0 && (
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-ink)]/50">
              Today's prep
            </h3>
            <ul className="mt-2 space-y-1.5">
              {signals.map((s) => (
                <li
                  key={s.id}
                  className="rounded-lg border border-[var(--color-signal-edge)] bg-[var(--color-signal-soft)]/90 px-2.5 py-2"
                >
                  <div className="flex items-start gap-2">
                    <span
                      className="mt-1 inline-block h-2 w-2 shrink-0 rotate-45 bg-[var(--color-signal)]"
                      aria-hidden
                    />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-[var(--color-signal)]">
                        {s.title}
                      </p>
                      <p className="mt-0.5 text-xs text-[var(--color-signal)]/70">
                        {formatClock(parseIso(s.at))}
                        {s.body ? ` · ${s.body}` : ''}
                      </p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  )
}
