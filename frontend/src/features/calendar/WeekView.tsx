import { useMemo } from 'react'
import FullCalendar from '@fullcalendar/react'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import type { CalendarEvent } from '../../lib/types'
import { eventPastelClass } from '../../lib/ruleColors'
import { sameDay, startOfWeek } from '../../lib/dates'

const HOUR_START_STR = '07:00:00'
const HOUR_END_STR = '22:00:00'
const SNAP_MINUTES = 15

interface Props {
  weekAnchor: Date
  events: CalendarEvent[]
  draft?: { start: Date; end: Date } | null
  onSelect: (event: CalendarEvent) => void
  onCreate: (start: Date, end: Date, anchor?: { x: number; y: number }) => void
  onMove: (id: string, start: Date, end: Date) => void
}

export function WeekView({
  weekAnchor,
  events,
  draft,
  onSelect,
  onCreate,
  onMove,
}: Props) {
  const weekStart = startOfWeek(weekAnchor)
  const byId = useMemo(() => {
    const m = new Map<string, CalendarEvent>()
    for (const e of events) m.set(e.id, e)
    return m
  }, [events])

  const fcEvents = useMemo(() => {
    const mapped = events.map((ev) => ({
      id: ev.id,
      title: ev.title,
      start: ev.start,
      end: ev.end,
      allDay: ev.all_day,
      editable: true,
      classNames: [eventPastelClass(ev), 'fc-app-event'],
      extendedProps: { kind: 'event' as const, event: ev },
    }))
    const draftEvents = draft
      ? [
          {
            id: '__draft__',
            title: 'New',
            start: draft.start.toISOString(),
            end: draft.end.toISOString(),
            allDay: false,
            editable: false,
            classNames: ['fc-app-draft'],
            extendedProps: { kind: 'draft' as const },
          },
        ]
      : []
    return [...mapped, ...draftEvents]
  }, [events, draft])

  return (
    <div className="fc-app-week relative flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--color-line)]/90 bg-[var(--color-surface)]/70 shadow-[0_1px_0_rgba(44,50,46,0.04),0_16px_40px_-24px_rgba(42,77,60,0.22)]">
      <FullCalendar
        plugins={[timeGridPlugin, interactionPlugin]}
        initialView="timeGridWeek"
        initialDate={weekStart}
        headerToolbar={false}
        height="100%"
        allDaySlot
        slotMinTime={HOUR_START_STR}
        slotMaxTime={HOUR_END_STR}
        slotDuration={{ minutes: SNAP_MINUTES }}
        snapDuration={{ minutes: SNAP_MINUTES }}
        slotLabelInterval="01:00:00"
        weekends
        firstDay={1}
        nowIndicator
        selectable
        selectMirror
        editable
        eventStartEditable
        eventDurationEditable={false}
        events={fcEvents}
        select={(arg) => {
          const anchor = {
            x: arg.jsEvent?.clientX ?? 0,
            y: arg.jsEvent?.clientY ?? 0,
          }
          onCreate(arg.start, arg.end, anchor)
          arg.view.calendar.unselect()
        }}
        eventClick={(arg) => {
          if (arg.event.extendedProps.kind !== 'event') return
          const ev = byId.get(arg.event.id)
          if (ev) onSelect(ev)
        }}
        eventDrop={(arg) => {
          const start = arg.event.start
          const end = arg.event.end
          if (!start || !end) {
            arg.revert()
            return
          }
          onMove(arg.event.id, start, end)
        }}
        eventContent={(arg) => (
          <div className="overflow-hidden px-0.5 text-[11px] leading-tight">
            <div className="truncate font-medium">{arg.event.title}</div>
            {!arg.event.allDay && (
              <div className="truncate opacity-70">{arg.timeText}</div>
            )}
          </div>
        )}
        dayHeaderContent={(arg) => {
          const isToday = sameDay(arg.date, new Date())
          return (
            <div className="flex flex-col items-center gap-0.5 py-1.5">
              <span
                className={`text-[11px] font-medium uppercase tracking-wide ${
                  isToday ? 'text-[var(--color-moss)]' : 'opacity-50'
                }`}
              >
                {arg.date.toLocaleDateString(undefined, { weekday: 'short' })}
              </span>
              <span
                className={`flex h-8 w-8 items-center justify-center text-lg font-medium tabular-nums ${
                  isToday
                    ? 'rounded-full bg-[var(--color-moss)] text-[var(--color-surface)]'
                    : ''
                }`}
              >
                {arg.date.getDate()}
              </span>
            </div>
          )
        }}
        key={weekStart.toISOString()}
      />
    </div>
  )
}
