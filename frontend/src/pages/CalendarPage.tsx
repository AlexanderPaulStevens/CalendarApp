import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type ReactNode } from 'react'
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
import { PlanPanel } from '../features/plan-panel/PlanPanel'

type Drawer = 'meals' | 'fridge' | 'shopping' | 'rules'

const DRAWER_TITLE: Record<Drawer, string> = {
  meals: 'Meals',
  fridge: 'Currently in fridge',
  shopping: 'Shopping lists',
  rules: 'Rules',
}

const NAV: {
  id: Drawer
  label: string
  icon: ReactNode
}[] = [
  {
    id: 'meals',
    label: 'Meals',
    icon: (
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M4 11h16M6 11V7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v4M5 11v8h14v-8" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M9 15h6" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'fridge',
    label: 'Fridge',
    icon: (
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.75">
        <rect x="6" y="3" width="12" height="18" rx="2" />
        <path d="M6 11h12M10 7v2M10 14v3" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'shopping',
    label: 'Shopping',
    icon: (
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M6 7h15l-1.5 9h-12L6 7Z" strokeLinejoin="round" />
        <path d="M6 7 5 3H3M9 20a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm9 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'rules',
    label: 'Rules',
    icon: (
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.75">
        <path d="M12 4v4M12 16v4M4 12h4M16 12h4" strokeLinecap="round" />
        <circle cx="12" cy="12" r="3.5" />
      </svg>
    ),
  },
]

const LEGEND = [
  { label: 'Exercise', cls: 'bg-[var(--color-rule-exercise)] border-[var(--color-rule-exercise-edge)]' },
  { label: 'Meal', cls: 'bg-[var(--color-rule-meals)] border-[var(--color-rule-meals-edge)]' },
  { label: 'Work', cls: 'bg-[var(--color-rule-work)] border-[var(--color-rule-work-edge)]' },
  { label: 'Study', cls: 'bg-[var(--color-rule-study)] border-[var(--color-rule-study-edge)]' },
  { label: 'Shop', cls: 'bg-[var(--color-rule-shopping)] border-[var(--color-rule-shopping-edge)]' },
]

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
  const [railOpen, setRailOpen] = useState(true)
  const [summaryOpen, setSummaryOpen] = useState(false)
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

  useEffect(() => {
    if (!toast) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') dismissToast()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toast, dismissToast])

  function setDrawer(next: Drawer | null) {
    if (next) setParams({ panel: next })
    else setParams({})
  }

  function closeEditor() {
    setSelected(null)
    setDraft(null)
    setEditorAnchor(null)
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
    <div className="flex h-full min-h-0">
      {/* Left nav — week controls + tools */}
      <aside className="relative z-30 flex w-[13.5rem] shrink-0 flex-col border-r border-[var(--color-line)]/90 bg-[var(--color-surface)]/80 backdrop-blur-md">
        <div className="border-b border-[var(--color-line)]/80 px-4 pb-4 pt-5">
          <Link
            to="/"
            className="font-[family-name:var(--font-display)] text-[1.85rem] leading-none tracking-tight text-[var(--color-ink)]"
          >
            Planner
          </Link>
        </div>

        <div className="border-b border-[var(--color-line)]/80 px-3 py-3">
          <div className="flex items-center justify-between gap-1">
            <button
              type="button"
              className="btn-ghost px-2 py-1 text-sm"
              aria-label="Previous week"
              onClick={() => setAnchor((a) => addDays(a, -7))}
            >
              ←
            </button>
            <button
              type="button"
              className="min-w-0 flex-1 truncate rounded-lg px-1 py-1 text-center text-xs font-medium tabular-nums text-[var(--color-ink)] transition hover:bg-[var(--color-moss-soft)]/50"
              title="Jump to this week"
              onClick={() => setAnchor(new Date())}
            >
              {weekLabel(anchor)}
            </button>
            <button
              type="button"
              className="btn-ghost px-2 py-1 text-sm"
              aria-label="Next week"
              onClick={() => setAnchor((a) => addDays(a, 7))}
            >
              →
            </button>
          </div>
          <button
            type="button"
            className="btn-primary mt-2 w-full text-center"
            onClick={() => setAnchor(new Date())}
          >
            Today
          </button>
        </div>

        <nav className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-auto px-2 py-3">
          {NAV.map((item) => {
            const active = drawer === item.id
            const badge = item.id === 'shopping' && toBuy > 0 ? toBuy : null
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setDrawer(active ? null : item.id)}
                className={`flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition ${
                  active
                    ? 'bg-[var(--color-moss-soft)] text-[var(--color-moss)] shadow-sm ring-1 ring-[var(--color-moss-edge)]/50'
                    : 'text-[var(--color-ink)]/75 hover:bg-black/[0.035] hover:text-[var(--color-ink)]'
                }`}
              >
                <span
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border ${
                    active
                      ? 'border-[var(--color-moss-edge)] bg-white/50'
                      : 'border-[var(--color-line)] bg-[var(--color-paper)]/70'
                  }`}
                >
                  {item.icon}
                </span>
                <span className="min-w-0 flex-1 text-sm font-medium">{item.label}</span>
                {badge != null && (
                  <span className="rounded-md bg-[var(--color-rule-shopping)] px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-[var(--color-rule-shopping-ink)]">
                    {badge}
                  </span>
                )}
              </button>
            )
          })}
        </nav>

        <div className="border-t border-[var(--color-line)]/80 px-3 py-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-ink)]/40">
            Legend
          </p>
          <ul className="space-y-1.5">
            {LEGEND.map((item) => (
              <li key={item.label} className="flex items-center gap-2 text-[11px] text-[var(--color-ink)]/65">
                <span className={`h-2.5 w-2.5 rounded-sm border ${item.cls}`} />
                {item.label}
              </li>
            ))}
          </ul>
        </div>
      </aside>

      {/* Main calendar column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="relative z-20 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-[var(--color-line)]/80 bg-[var(--color-paper)]/75 px-4 py-3 backdrop-blur-md">
          <div className="min-w-0">
            <h1 className="font-[family-name:var(--font-display)] text-2xl leading-none tracking-tight">
              Week plan
            </h1>
            <p className="mt-1 text-xs text-[var(--color-ink)]/50">
              Drag empty time to add · click a block to edit · drag to reschedule
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {mutate.isPending && (
              <span className="text-xs text-[var(--color-ink)]/45">Updating…</span>
            )}
            <button
              type="button"
              className="btn-ghost text-sm lg:hidden"
              onClick={() => setSummaryOpen(true)}
            >
              Week summary
            </button>
            <button
              type="button"
              className="btn-ghost hidden text-sm lg:inline-flex"
              onClick={() => setRailOpen((v) => !v)}
              aria-pressed={railOpen}
              title={railOpen ? 'Hide week summary' : 'Show week summary'}
            >
              {railOpen ? 'Hide summary' : 'Show summary'}
            </button>
          </div>
        </header>

        <main className="min-h-0 flex-1 p-3 sm:p-4">
          {planQuery.isLoading && (
            <div className="flex h-full items-center justify-center text-sm text-[var(--color-ink)]/50">
              Loading plan…
            </div>
          )}
          {planQuery.isError && (
            <div className="flex h-full items-center justify-center p-4 text-sm text-[var(--color-warn)]">
              Could not load plan. Is the API running on port 8000?
            </div>
          )}
          {plan && (
            <WeekView
              weekAnchor={anchor}
              events={plan.events}
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

      {/* Right productivity rail */}
      {plan && railOpen && (
        <div className="hidden w-[20rem] shrink-0 border-l border-[var(--color-line)]/90 lg:block">
          <PlanPanel plan={plan} />
        </div>
      )}

      {toast && (
        <div
          className="signal-alert-backdrop fixed inset-0 z-[70] flex items-center justify-center bg-[var(--color-ink)]/45 p-4 backdrop-blur-[3px]"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="signal-alert-title"
          aria-describedby="signal-alert-body"
          onClick={dismissToast}
        >
          <div
            className="signal-alert-card w-full max-w-md rounded-2xl border-2 border-[var(--color-signal-edge)] bg-[var(--color-signal-soft)] px-6 py-7 text-[var(--color-signal)] shadow-[0_28px_64px_-20px_rgba(44,50,46,0.45)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2.5">
              <span
                className="inline-block h-3.5 w-3.5 shrink-0 rotate-45 border-2 border-[var(--color-signal)] bg-[var(--color-signal)]"
                aria-hidden
              />
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-signal)]/70">
                Prep now
              </p>
            </div>
            <h2
              id="signal-alert-title"
              className="mt-3 font-[family-name:var(--font-display)] text-[2rem] leading-tight tracking-tight text-[var(--color-signal)]"
            >
              {toast.title}
            </h2>
            {toast.body && (
              <p
                id="signal-alert-body"
                className="mt-2 text-base leading-relaxed text-[var(--color-signal)]/85"
              >
                {toast.body}
              </p>
            )}
            <button
              type="button"
              className="mt-6 w-full rounded-xl border border-[var(--color-signal)] bg-[var(--color-signal)] px-4 py-3 text-sm font-semibold text-[var(--color-signal-soft)] transition hover:brightness-110"
              onClick={dismissToast}
              autoFocus
            >
              Got it
            </button>
          </div>
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

      {summaryOpen && plan && (
        <SlideOver title="Week summary" onClose={() => setSummaryOpen(false)}>
          <PlanPanel plan={plan} />
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
