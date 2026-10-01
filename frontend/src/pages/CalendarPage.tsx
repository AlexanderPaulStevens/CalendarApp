import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import * as api from '../lib/api'
import type { CalendarEvent, PlanSnapshot } from '../lib/types'
import { addDays, toDateParam, weekLabel } from '../lib/dates'
import { findOverlappingEvents } from '../lib/conflicts'
import { useSignalNotifications } from '../lib/useSignalNotifications'
import { WeekView } from '../features/calendar/WeekView'
import { EventEditor } from '../features/calendar/EventEditor'
import { ConflictReplaceDialog } from '../features/calendar/ConflictReplaceDialog'
import { SlideOver } from '../features/panels/SlideOver'
import { FridgePanel } from '../features/panels/FridgePanel'
import { MealsPanel } from '../features/panels/MealsPanel'
import { RulesPanel } from '../features/panels/RulesPanel'
import { ShoppingPanel } from '../features/panels/ShoppingPanel'

type Drawer = 'meals' | 'fridge' | 'shopping' | 'rules'

const DRAWER_TITLE: Record<Drawer, string> = {
  meals: 'Meals',
  fridge: 'Currently in fridge',
  shopping: 'Shopping lists',
  rules: 'Rules',
}

export function CalendarPage() {
  const [params, setParams] = useSearchParams()
  const panel = params.get('panel')
  const drawer: Drawer | null =
    panel === 'meals' || panel === 'fridge' || panel === 'shopping' || panel === 'rules'
      ? panel
      : null
  const [anchor, setAnchor] = useState(() => new Date())
  const [selected, setSelected] = useState<CalendarEvent | null>(null)
  const [draft, setDraft] = useState<{ start: Date; end: Date } | null>(null)
  const [editorAnchor, setEditorAnchor] = useState<{ x: number; y: number } | null>(null)
  const [conflict, setConflict] = useState<{
    body: Record<string, unknown>
    overlapping: CalendarEvent[]
  } | null>(null)
  const qc = useQueryClient()

  const anchorDate = toDateParam(anchor)

  const planQuery = useQuery({
    queryKey: ['plan', 'week', anchorDate],
    queryFn: () => api.fetchPlan(anchorDate),
  })

  const refreshPlan = async () => {
    await qc.invalidateQueries({ queryKey: ['plan'] })
  }

  const setPlan = (_plan: PlanSnapshot) => {
    void refreshPlan()
  }

  const mutate = useMutation({
    mutationFn: async (fn: () => Promise<PlanSnapshot>) => fn(),
    onSuccess: () => {
      void refreshPlan()
    },
  })

  const plan = planQuery.data
  const toBuy = plan?.shopping.length ?? 0
  const { toast, dismissToast } = useSignalNotifications(plan?.signals)

  function setDrawer(next: Drawer | null) {
    if (next) setParams({ panel: next })
    else setParams({})
  }

  function closeEditor() {
    setSelected(null)
    setDraft(null)
    setEditorAnchor(null)
  }

  function openQuickAdd() {
    const start = new Date()
    start.setMinutes(0, 0, 0)
    start.setHours(start.getHours() + 1)
    const end = new Date(start.getTime() + 60 * 60 * 1000)
    setSelected(null)
    setEditorAnchor(null)
    setDraft({ start, end })
  }

  function tryCreate(body: Record<string, unknown>) {
    if (!plan) return
    const start = String(body.start)
    const end = String(body.end)
    const allDay = Boolean(body.all_day)
    if (!allDay) {
      const overlapping = findOverlappingEvents(plan.events, start, end)
      if (overlapping.length > 0) {
        setConflict({ body, overlapping })
        closeEditor()
        return
      }
    }
    mutate.mutate(() => api.createEvent(body))
    closeEditor()
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="relative z-50 border-b border-[var(--color-line)]/80 bg-[var(--color-paper)]/80 px-4 py-3 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 gap-y-2.5">
          <Link
            to="/"
            className="font-[family-name:var(--font-display)] text-[1.65rem] leading-none tracking-tight text-[var(--color-ink)]"
          >
            Planner
          </Link>

          <button
            type="button"
            onClick={openQuickAdd}
            className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-moss-edge)] bg-[var(--color-moss-soft)] px-3.5 py-1.5 text-sm font-medium text-[var(--color-moss)] transition hover:brightness-[0.97]"
            title="Create event"
          >
            <span className="text-base leading-none" aria-hidden>
              +
            </span>
            Create
          </button>

          <div className="flex items-center gap-0.5 rounded-full border border-[var(--color-line)] bg-[var(--color-surface)]/70 p-0.5">
            <button
              type="button"
              className="rounded-full px-3 py-1.5 text-sm text-[var(--color-ink)]/75 transition hover:bg-[var(--color-moss-soft)]/60 hover:text-[var(--color-moss)]"
              title="Jump to this week"
              onClick={() => setAnchor(new Date())}
            >
              Today
            </button>
            <button
              type="button"
              className="rounded-full px-2.5 py-1.5 text-sm text-[var(--color-ink)]/55 transition hover:bg-black/[0.04] hover:text-[var(--color-ink)]"
              aria-label="Previous week"
              onClick={() => setAnchor((a) => addDays(a, -7))}
            >
              ←
            </button>
            <span className="min-w-[9.5rem] px-1 text-center text-sm font-medium tabular-nums text-[var(--color-ink)]">
              {weekLabel(anchor)}
            </span>
            <button
              type="button"
              className="rounded-full px-2.5 py-1.5 text-sm text-[var(--color-ink)]/55 transition hover:bg-black/[0.04] hover:text-[var(--color-ink)]"
              aria-label="Next week"
              onClick={() => setAnchor((a) => addDays(a, 7))}
            >
              →
            </button>
          </div>

          <nav className="ml-auto flex gap-0.5 rounded-full border border-[var(--color-line)] bg-[var(--color-surface)]/70 p-0.5 text-sm">
            {(
              [
                ['meals', 'Meals'],
                ['fridge', 'Fridge'],
                ['shopping', toBuy > 0 ? `Shopping · ${toBuy}` : 'Shopping'],
                ['rules', 'Rules'],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setDrawer(drawer === id ? null : id)}
                className={`rounded-full px-3 py-1.5 transition ${
                  drawer === id
                    ? 'bg-[var(--color-moss-soft)] text-[var(--color-moss)] shadow-sm'
                    : 'text-[var(--color-ink)]/55 hover:bg-black/[0.04] hover:text-[var(--color-ink)]'
                }`}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <div className="min-h-0 flex-1">
        <main className="mx-auto h-full min-h-0 max-w-[1600px] p-3 sm:p-4">
          {planQuery.isLoading && <p className="p-4 text-sm opacity-60">Loading plan…</p>}
          {planQuery.isError && (
            <p className="p-4 text-sm text-[var(--color-warn)]">
              Could not load plan. Is the API running on port 8000?
            </p>
          )}
          {plan && (
            <WeekView
              weekAnchor={anchor}
              events={plan.events}
              signals={plan.signals ?? []}
              draft={draft}
              onSelect={(ev) => {
                setDraft(null)
                setEditorAnchor(null)
                setSelected(ev)
              }}
              onCreate={(start, end, clickAnchor) => {
                setSelected(null)
                setEditorAnchor(clickAnchor ?? null)
                setDraft({ start, end })
              }}
              onMove={(id, start, end) =>
                mutate.mutate(() =>
                  api.updateEvent(id, {
                    start: start.toISOString(),
                    end: end.toISOString(),
                  }),
                )
              }
            />
          )}
        </main>
      </div>

      {toast && (
        <div
          role="status"
          className="fixed bottom-4 left-1/2 z-[60] flex max-w-md -translate-x-1/2 items-start gap-3 rounded-2xl border border-[var(--color-signal-edge)] bg-[var(--color-signal-soft)] px-4 py-3 text-sm text-[var(--color-signal)] shadow-lg"
        >
          <span
            className="mt-1 inline-block h-2.5 w-2.5 shrink-0 rotate-45 bg-[var(--color-signal)]"
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <div className="font-medium">{toast.title}</div>
            <div className="mt-0.5 opacity-80">{toast.body}</div>
          </div>
          <button
            type="button"
            className="shrink-0 rounded-md px-1.5 py-0.5 text-xs hover:bg-black/5"
            onClick={dismissToast}
          >
            Dismiss
          </button>
        </div>
      )}

      {(selected || draft) && plan && (
        <EventEditor
          event={selected}
          recipes={plan.recipes}
          draftStart={draft?.start}
          draftEnd={draft?.end}
          anchor={editorAnchor}
          onClose={closeEditor}
          onSave={(body) => {
            if (selected) {
              mutate.mutate(() => api.updateEvent(selected.id, body))
              closeEditor()
            } else {
              tryCreate(body)
            }
          }}
          onDelete={
            selected
              ? () => {
                  mutate.mutate(() => api.deleteEvent(selected.id))
                  closeEditor()
                }
              : undefined
          }
          onDuplicate={
            selected
              ? () => {
                  mutate.mutate(() => api.duplicateEvent(selected.id))
                  closeEditor()
                }
              : undefined
          }
        />
      )}

      {drawer && plan && (
        <SlideOver
          title={DRAWER_TITLE[drawer]}
          wide={drawer === 'meals'}
          onClose={() => setDrawer(null)}
        >
          {drawer === 'meals' && <MealsPanel plan={plan} onPlan={setPlan} />}
          {drawer === 'fridge' && <FridgePanel plan={plan} onPlan={setPlan} />}
          {drawer === 'shopping' && <ShoppingPanel plan={plan} />}
          {drawer === 'rules' && <RulesPanel plan={plan} onPlan={setPlan} />}
        </SlideOver>
      )}

      {conflict && (
        <ConflictReplaceDialog
          pending={conflict.body}
          overlapping={conflict.overlapping}
          onReplace={(ids) => {
            mutate.mutate(() =>
              api.createEvent({ ...conflict.body, replace_event_ids: ids }),
            )
            setConflict(null)
          }}
          onKeepBoth={() => {
            mutate.mutate(() => api.createEvent(conflict.body))
            setConflict(null)
          }}
          onCancel={() => setConflict(null)}
        />
      )}
    </div>
  )
}
