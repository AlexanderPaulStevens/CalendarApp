import type { CalendarEvent, PlanSnapshot, ShoppingLine } from '../../lib/types'
import { parseIso } from '../../lib/dates'

interface Props {
  plan: PlanSnapshot
}

interface TripGroup {
  key: string
  tripDate: string | null
  event: CalendarEvent | null
  lines: ShoppingLine[]
}

function tripDayKey(isoOrDate: string): string {
  // Accept YYYY-MM-DD or full ISO datetime.
  if (/^\d{4}-\d{2}-\d{2}$/.test(isoOrDate)) return isoOrDate
  const d = parseIso(isoOrDate)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function formatTripHeading(tripDate: string, event: CalendarEvent | null): string {
  const d = parseIso(`${tripDate}T12:00:00`)
  const dayPart = d.toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
  if (!event) return dayPart
  const time = parseIso(event.start).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  })
  return `${dayPart} · ${time}`
}

function groupByTrip(plan: PlanSnapshot): TripGroup[] {
  const shoppingEvents = plan.events.filter((e) => e.type === 'shopping')
  const byDay = new Map<string, CalendarEvent>()
  for (const event of shoppingEvents) {
    const key = tripDayKey(event.start)
    // Prefer Auto trips; keep first if several land on the same day.
    const existing = byDay.get(key)
    if (!existing || (existing.origin !== 'auto' && event.origin === 'auto')) {
      byDay.set(key, event)
    }
  }

  const groups = new Map<string, TripGroup>()
  for (const line of plan.shopping) {
    const key = line.trip_date ? tripDayKey(line.trip_date) : 'unscheduled'
    const current = groups.get(key)
    if (current) {
      current.lines.push(line)
      continue
    }
    groups.set(key, {
      key,
      tripDate: line.trip_date,
      event: line.trip_date ? byDay.get(tripDayKey(line.trip_date)) ?? null : null,
      lines: [line],
    })
  }

  return [...groups.values()].sort((a, b) => {
    if (a.tripDate === b.tripDate) return 0
    if (a.tripDate === null) return 1
    if (b.tripDate === null) return -1
    return a.tripDate.localeCompare(b.tripDate)
  })
}

export function ShoppingPanel({ plan }: Props) {
  const trips = groupByTrip(plan)

  return (
    <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
      {trips.length === 0 && (
        <p className="py-6 text-sm opacity-60">Nothing to buy this week.</p>
      )}

      {trips.length > 1 && (
        <p className="mb-4 text-sm opacity-60">
          {trips.length} store trips this week — each list matches one shopping
          event on the calendar.
        </p>
      )}

      <div className="space-y-5">
        {trips.map((trip, index) => (
          <section
            key={trip.key}
            className="overflow-hidden rounded-xl border border-[var(--color-rule-shopping-edge)] bg-[var(--color-rule-shopping)]/55"
          >
            <header className="border-b border-[var(--color-rule-shopping-edge)] px-3 py-2.5">
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="text-sm font-semibold text-[var(--color-rule-shopping-ink)]">
                  {trip.tripDate
                    ? `Trip ${index + 1} · ${formatTripHeading(trip.tripDate, trip.event)}`
                    : `Trip ${index + 1}`}
                </h3>
                <span className="shrink-0 text-xs tabular-nums text-[var(--color-rule-shopping-ink)]/70">
                  {trip.lines.length} item{trip.lines.length === 1 ? '' : 's'}
                </span>
              </div>
              {trip.event?.title && (
                <p className="mt-1 truncate text-xs text-[var(--color-rule-shopping-ink)]/65">
                  {trip.event.title}
                </p>
              )}
            </header>
            <ul>
              {trip.lines.map((line) => (
                <li
                  key={line.id}
                  className="border-b border-[var(--color-rule-shopping-edge)]/50 px-3 py-2.5 text-sm last:border-b-0"
                >
                  <span className="min-w-0 flex-1">
                    {line.ingredient}
                    <span className="mt-0.5 block text-xs opacity-60">
                      {line.quantity}
                      {line.unit}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}
