import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from 'react'
import type { CalendarEvent, PlanSignal } from '../../lib/types'
import { eventPastelClass } from '../../lib/ruleColors'
import { addDays, parseIso, sameDay, startOfWeek } from '../../lib/dates'

const HOUR_START = 7
const HOUR_END = 22
const HOURS = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i)
const PX_PER_HOUR = 56
const SNAP_MINUTES = 15

interface Props {
  weekAnchor: Date
  events: CalendarEvent[]
  signals?: PlanSignal[]
  draft?: { start: Date; end: Date } | null
  onSelect: (event: CalendarEvent) => void
  onCreate: (start: Date, end: Date, anchor?: { x: number; y: number }) => void
  onMove: (id: string, start: Date, end: Date) => void
}

interface DragState {
  day: Date
  startY: number
  currentY: number
  pointerId: number
}

function clampHour(hour: number): number {
  return Math.min(HOUR_END, Math.max(HOUR_START, hour))
}

function yToSnappedDate(day: Date, y: number): Date {
  const rawHour = HOUR_START + y / PX_PER_HOUR
  const totalMinutes = Math.round((clampHour(rawHour) * 60) / SNAP_MINUTES) * SNAP_MINUTES
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  const d = new Date(day)
  d.setHours(hours, minutes, 0, 0)
  if (d.getHours() >= HOUR_END && d.getMinutes() > 0) {
    d.setHours(HOUR_END, 0, 0, 0)
  }
  return d
}

function topFor(d: Date): number {
  const h = d.getHours() + d.getMinutes() / 60
  return (h - HOUR_START) * PX_PER_HOUR
}

function heightFor(start: Date, end: Date): number {
  const hours = Math.max((end.getTime() - start.getTime()) / 3600000, SNAP_MINUTES / 60)
  return Math.max(hours * PX_PER_HOUR, 18)
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function WeekView({ weekAnchor, events, signals = [], draft, onSelect, onCreate, onMove }: Props) {
  const weekStart = startOfWeek(weekAnchor)
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))
  const today = new Date()
  const [now, setNow] = useState(() => new Date())
  const [drag, setDrag] = useState<DragState | null>(null)
  const [hoverDay, setHoverDay] = useState<string | null>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const didDragRef = useRef(false)

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 60_000)
    return () => window.clearInterval(id)
  }, [])

  function rangeFromDrag(state: DragState): { start: Date; end: Date } {
    const a = yToSnappedDate(state.day, Math.min(state.startY, state.currentY))
    let b = yToSnappedDate(state.day, Math.max(state.startY, state.currentY))
    if (b.getTime() <= a.getTime()) {
      b = new Date(a.getTime() + 60 * 60 * 1000)
    }
    return { start: a, end: b }
  }

  function onPointerDown(day: Date, e: ReactPointerEvent<HTMLDivElement>) {
    if (e.button !== 0) return
    const target = e.target as HTMLElement
    if (target.closest('[data-event]')) return
    const rect = e.currentTarget.getBoundingClientRect()
    const y = e.clientY - rect.top
    didDragRef.current = false
    e.currentTarget.setPointerCapture(e.pointerId)
    setDrag({ day, startY: y, currentY: y, pointerId: e.pointerId })
  }

  function onPointerMove(e: ReactPointerEvent<HTMLDivElement>) {
    if (!drag || drag.pointerId !== e.pointerId) return
    const rect = e.currentTarget.getBoundingClientRect()
    const y = Math.min(Math.max(e.clientY - rect.top, 0), (HOUR_END - HOUR_START) * PX_PER_HOUR)
    if (Math.abs(y - drag.startY) > 6) didDragRef.current = true
    setDrag({ ...drag, currentY: y })
  }

  function finishDrag(e: ReactPointerEvent<HTMLDivElement>) {
    if (!drag || drag.pointerId !== e.pointerId) return
    const { start, end } = rangeFromDrag(drag)
    const anchor = { x: e.clientX, y: e.clientY }
    setDrag(null)
    if (!didDragRef.current) {
      // Click: default 1-hour block from snapped start
      const clickEnd = new Date(start.getTime() + 60 * 60 * 1000)
      onCreate(start, clickEnd, anchor)
      return
    }
    onCreate(start, end, anchor)
  }

  function onDragStartEvent(ev: React.DragEvent, event: CalendarEvent) {
    ev.dataTransfer.setData('text/event-id', event.id)
    ev.dataTransfer.setData(
      'text/duration',
      String(parseIso(event.end).getTime() - parseIso(event.start).getTime()),
    )
    ev.dataTransfer.effectAllowed = 'move'
  }

  function onDrop(day: Date, e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    const id = e.dataTransfer.getData('text/event-id')
    const duration = Number(e.dataTransfer.getData('text/duration') || 3600000)
    if (!id) return
    const rect = e.currentTarget.getBoundingClientRect()
    const y = e.clientY - rect.top
    const start = yToSnappedDate(day, y)
    const end = new Date(start.getTime() + duration)
    onMove(id, start, end)
  }

  const dragRange = drag ? rangeFromDrag(drag) : null
  const showNow = sameDay(now, today) && days.some((d) => sameDay(d, today))
  const nowTop = topFor(now)

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--color-line)]/90 bg-[var(--color-surface)]/55 shadow-[0_1px_0_rgba(44,50,46,0.04),0_12px_32px_-18px_rgba(42,77,60,0.18)] backdrop-blur-[2px]">
      {/* Day headers */}
      <div
        className="grid shrink-0 border-b border-[var(--color-line)]/80 bg-[var(--color-paper)]/90"
        style={{ gridTemplateColumns: '3.75rem repeat(7, 1fr)' }}
      >
        <div />
        {days.map((d) => {
          const isToday = sameDay(d, today)
          return (
            <div
              key={d.toISOString()}
              className={`flex flex-col items-center gap-0.5 px-1 py-2.5 ${
                isToday ? 'bg-[var(--color-moss-soft)]/35' : ''
              }`}
            >
              <span
                className={`text-[11px] font-medium uppercase tracking-wide ${
                  isToday ? 'text-[var(--color-moss)]' : 'text-[var(--color-ink)]/45'
                }`}
              >
                {d.toLocaleDateString(undefined, { weekday: 'short' })}
              </span>
              <span
                className={`flex h-9 w-9 items-center justify-center text-lg font-medium tabular-nums ${
                  isToday
                    ? 'rounded-full bg-[var(--color-moss-soft)] text-[var(--color-moss)] ring-1 ring-[var(--color-moss-edge)]'
                    : 'text-[var(--color-ink)]'
                }`}
              >
                {d.getDate()}
              </span>
            </div>
          )
        })}
      </div>

      {/* All-day row */}
      <div
        className="grid shrink-0 border-b border-[var(--color-line)] bg-[var(--color-paper)]/70"
        style={{ gridTemplateColumns: '3.75rem repeat(7, 1fr)' }}
      >
        <div className="flex items-start justify-end px-1.5 py-2 text-[10px] uppercase tracking-wide text-[var(--color-ink)]/40">
          All day
        </div>
        {days.map((day) => {
          const allDay = events.filter((ev) => ev.all_day && sameDay(parseIso(ev.start), day))
          const earlySignals = signals.filter((s) => {
            const at = parseIso(s.at)
            if (!sameDay(at, day)) return false
            const h = at.getHours() + at.getMinutes() / 60
            return h < HOUR_START || h >= HOUR_END
          })
          const isToday = sameDay(day, today)
          return (
            <div
              key={`allday-${day.toISOString()}`}
              className={`min-h-9 border-l border-[var(--color-line)]/80 px-1 py-1 ${
                isToday ? 'bg-[var(--color-moss-soft)]/25' : ''
              }`}
            >
              {allDay.map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  data-event
                  className={`mb-0.5 w-full truncate rounded-md px-1.5 py-0.5 text-left text-xs ${eventPastelClass(ev)}`}
                  onClick={() => onSelect(ev)}
                >
                  {ev.title}
                </button>
              ))}
              {earlySignals.map((s) => (
                <div
                  key={s.id}
                  title={`${s.title} · ${formatTime(parseIso(s.at))}\n${s.body}`}
                  className="mb-0.5 flex w-full items-center gap-1 truncate rounded-md border border-[var(--color-signal-edge)] bg-[var(--color-signal-soft)] px-1.5 py-0.5 text-left text-[10px] text-[var(--color-signal)]"
                >
                  <span
                    className="inline-block h-1.5 w-1.5 shrink-0 rotate-45 bg-[var(--color-signal)]"
                    aria-hidden
                  />
                  <span className="truncate">{s.title}</span>
                </div>
              ))}
            </div>
          )
        })}
      </div>

      {/* Timed grid */}
      <div className="min-h-0 flex-1 overflow-auto" ref={gridRef}>
        <div
          className="grid relative"
          style={{
            gridTemplateColumns: '3.75rem repeat(7, 1fr)',
            height: (HOUR_END - HOUR_START) * PX_PER_HOUR,
          }}
        >
          {/* Hour labels */}
          <div className="relative border-r border-[var(--color-line)]">
            {HOURS.map((h) => (
              <div
                key={h}
                className="absolute right-2 -translate-y-1/2 text-[11px] tabular-nums text-[var(--color-ink)]/40"
                style={{ top: (h - HOUR_START) * PX_PER_HOUR }}
              >
                {`${h.toString().padStart(2, '0')}:00`}
              </div>
            ))}
          </div>

          {days.map((day) => {
            const dayEvents = events.filter(
              (ev) => !ev.all_day && sameDay(parseIso(ev.start), day),
            )
            const daySignals = signals.filter((s) => {
              const at = parseIso(s.at)
              if (!sameDay(at, day)) return false
              const h = at.getHours() + at.getMinutes() / 60
              return h >= HOUR_START && h < HOUR_END
            })
            const isToday = sameDay(day, today)
            const dayKey = day.toISOString()
            const showDraft =
              draft && sameDay(draft.start, day) && !dragRange
            const showDragGhost = dragRange && sameDay(drag!.day, day)

            return (
              <div
                key={dayKey}
                className={`relative cursor-crosshair border-r border-[var(--color-line)]/80 last:border-r-0 ${
                  isToday ? 'bg-[var(--color-moss-soft)]/20' : ''
                } ${hoverDay === dayKey && !drag ? 'bg-[var(--color-moss-soft)]/10' : ''}`}
                onPointerDown={(e) => onPointerDown(day, e)}
                onPointerMove={onPointerMove}
                onPointerUp={finishDrag}
                onPointerCancel={() => setDrag(null)}
                onMouseEnter={() => setHoverDay(dayKey)}
                onMouseLeave={() => setHoverDay((h) => (h === dayKey ? null : h))}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => onDrop(day, e)}
              >
                {HOURS.map((h) => (
                  <div
                    key={h}
                    className="pointer-events-none absolute inset-x-0 border-t border-[var(--color-line)]/50"
                    style={{ top: (h - HOUR_START) * PX_PER_HOUR }}
                  />
                ))}
                {/* Half-hour guides */}
                {HOURS.map((h) => (
                  <div
                    key={`half-${h}`}
                    className="pointer-events-none absolute inset-x-0 border-t border-dashed border-[var(--color-line)]/30"
                    style={{ top: (h - HOUR_START) * PX_PER_HOUR + PX_PER_HOUR / 2 }}
                  />
                ))}

                {showNow && isToday && nowTop >= 0 && nowTop <= (HOUR_END - HOUR_START) * PX_PER_HOUR && (
                  <div
                    className="pointer-events-none absolute inset-x-0 z-30 flex items-center"
                    style={{ top: nowTop }}
                  >
                    <span className="absolute -left-1.5 h-2.5 w-2.5 rounded-full bg-[var(--color-clay)] ring-2 ring-[var(--color-warn-soft)]" />
                    <span className="h-0.5 w-full bg-[var(--color-clay)]/80" />
                  </div>
                )}

                {daySignals.map((s, idx) => {
                  const at = parseIso(s.at)
                  const top = topFor(at)
                  // Nudge stacked Signals that share a minute.
                  const nudge = (idx % 4) * 3
                  return (
                    <div
                      key={s.id}
                      title={`${s.title} · ${formatTime(at)}\n${s.body}`}
                      className="pointer-events-auto absolute left-0 right-0 z-[25] flex items-center"
                      style={{ top: top + nudge }}
                      onPointerDown={(e) => e.stopPropagation()}
                    >
                      <span
                        className="absolute -left-0.5 h-2 w-2 rotate-45 border border-[var(--color-signal-edge)] bg-[var(--color-signal)] shadow-sm"
                        aria-hidden
                      />
                      <span className="ml-2 max-w-[calc(100%-0.5rem)] truncate rounded-sm bg-[var(--color-signal-soft)]/95 px-1 py-px text-[10px] font-medium leading-tight text-[var(--color-signal)] ring-1 ring-[var(--color-signal-edge)]/80">
                        {s.title}
                      </span>
                    </div>
                  )
                })}

                {dayEvents.map((ev) => {
                  const start = parseIso(ev.start)
                  const end = parseIso(ev.end)
                  return (
                    <button
                      key={ev.id}
                      type="button"
                      data-event
                      draggable
                      onDragStart={(e) => onDragStartEvent(e, ev)}
                      className={`absolute left-1 right-1 z-20 overflow-hidden rounded-md px-1.5 py-1 text-left text-xs leading-tight shadow-sm transition-shadow hover:z-40 hover:shadow-md ${eventPastelClass(ev)}`}
                      style={{
                        top: topFor(start),
                        height: heightFor(start, end),
                      }}
                      onClick={(e: ReactMouseEvent) => {
                        e.stopPropagation()
                        onSelect(ev)
                      }}
                      onPointerDown={(e) => e.stopPropagation()}
                    >
                      <div className="truncate font-medium">{ev.title}</div>
                      {heightFor(start, end) > 28 && (
                        <div className="truncate opacity-75">{formatTime(start)}</div>
                      )}
                    </button>
                  )
                })}

                {showDraft && draft && (
                  <div
                    className="pointer-events-none absolute left-1 right-1 z-10 overflow-hidden rounded-md border border-dashed border-[var(--color-moss-edge)] bg-[var(--color-moss-soft)]/75 px-1.5 py-1 text-xs text-[var(--color-moss)]"
                    style={{
                      top: topFor(draft.start),
                      height: heightFor(draft.start, draft.end),
                    }}
                  >
                    <div className="font-medium">New event</div>
                    <div className="opacity-80">
                      {formatTime(draft.start)} – {formatTime(draft.end)}
                    </div>
                  </div>
                )}

                {showDragGhost && dragRange && (
                  <div
                    className="pointer-events-none absolute left-1 right-1 z-10 overflow-hidden rounded-md border border-[var(--color-moss-edge)] bg-[var(--color-moss-soft)]/90 px-1.5 py-1 text-xs text-[var(--color-moss)] shadow-sm"
                    style={{
                      top: topFor(dragRange.start),
                      height: heightFor(dragRange.start, dragRange.end),
                    }}
                  >
                    <div className="font-medium">
                      {formatTime(dragRange.start)} – {formatTime(dragRange.end)}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
