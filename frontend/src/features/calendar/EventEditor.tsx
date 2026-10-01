import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CalendarEvent, EventType, Recipe } from '../../lib/types'
import { parseIso } from '../../lib/dates'

interface Props {
  event: CalendarEvent | null
  recipes: Recipe[]
  draftStart?: Date
  draftEnd?: Date
  /** Screen coords for popover placement (from calendar click). */
  anchor?: { x: number; y: number } | null
  onClose: () => void
  onSave: (body: Record<string, unknown>) => void
  onDelete?: () => void
  onDuplicate?: () => void
}

const TYPE_CHIPS: { type: EventType; label: string; pastel: string }[] = [
  {
    type: 'personal',
    label: 'Event',
    pastel: 'bg-[var(--color-moss-soft)] text-[var(--color-ink)] border-[var(--color-line)]',
  },
  {
    type: 'exercise',
    label: 'Exercise',
    pastel:
      'bg-[var(--color-rule-exercise)] text-[var(--color-rule-exercise-ink)] border-[var(--color-rule-exercise-edge)]',
  },
  {
    type: 'meal',
    label: 'Meal',
    pastel:
      'bg-[var(--color-rule-meals)] text-[var(--color-rule-meals-ink)] border-[var(--color-rule-meals-edge)]',
  },
  {
    type: 'shopping',
    label: 'Shop',
    pastel:
      'bg-[var(--color-rule-shopping)] text-[var(--color-rule-shopping-ink)] border-[var(--color-rule-shopping-edge)]',
  },
  {
    type: 'rest',
    label: 'Rest',
    pastel: 'bg-[var(--color-rule-study)] text-[var(--color-rule-study-ink)] border-[var(--color-rule-study-edge)]',
  },
]

function toLocalInput(d: Date): string {
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatWhen(start: Date, end: Date): string {
  const day = start.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
  const t = (d: Date) => d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return `${day} · ${t(start)} – ${t(end)}`
}

function RecipePreview({ recipe, portions }: { recipe: Recipe; portions: number }) {
  return (
    <div className="rounded-lg border border-[var(--color-rule-meals-edge)] bg-[var(--color-rule-meals)]/50 p-2.5">
      <div className="font-medium text-[var(--color-rule-meals-ink)]">{recipe.name}</div>
      <p className="mt-0.5 text-xs text-[var(--color-ink)]/65">
        {recipe.meal_type || 'meal'}
        {recipe.cuisine ? ` · ${recipe.cuisine}` : ''}
        {recipe.preparation_time_min ? ` · ${recipe.preparation_time_min} min` : ''}
      </p>
      <p className="mt-0.5 text-xs text-[var(--color-ink)]/65">
        {Math.round(recipe.calories * portions)} kcal · P {Math.round(recipe.protein_g * portions)}g · C{' '}
        {Math.round(recipe.carbohydrates_g * portions)}g · F {Math.round(recipe.fat_g * portions)}g
        {portions !== 1 ? ` · ×${portions}` : ''}
      </p>
    </div>
  )
}

export function EventEditor({
  event,
  recipes,
  draftStart,
  draftEnd,
  anchor,
  onClose,
  onSave,
  onDelete,
  onDuplicate,
}: Props) {
  const isNew = !event
  const initialStart = event ? parseIso(event.start) : (draftStart ?? new Date())
  const initialEnd = event ? parseIso(event.end) : (draftEnd ?? new Date(Date.now() + 3600000))
  const [title, setTitle] = useState(event?.title ?? '')
  const [type, setType] = useState<EventType>(event?.type ?? 'personal')
  const [start, setStart] = useState(toLocalInput(initialStart))
  const [end, setEnd] = useState(toLocalInput(initialEnd))
  const [activity, setActivity] = useState(event?.activity ?? 'cycling')
  const [recipeId, setRecipeId] = useState(event?.recipe_id ?? recipes[0]?.id ?? '')
  const [portions, setPortions] = useState(event?.portions ?? 1)
  const [showDetails, setShowDetails] = useState(!isNew)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const titleRef = useRef<HTMLInputElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const selectedRecipe = recipes.find((r) => r.id === recipeId) ?? null
  const isMeal = type === 'meal'
  const mealChoices = [...recipes].sort((a, b) => a.name.localeCompare(b.name))
  const usePopover = Boolean(anchor)

  useEffect(() => {
    titleRef.current?.focus()
    titleRef.current?.select()
  }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useLayoutEffect(() => {
    if (!usePopover || !anchor || !panelRef.current) {
      setPos(null)
      return
    }
    const panel = panelRef.current
    const w = panel.offsetWidth
    const h = panel.offsetHeight
    const pad = 12
    let left = anchor.x + 8
    let top = anchor.y - 12
    if (left + w > window.innerWidth - pad) left = anchor.x - w - 8
    if (left < pad) left = pad
    if (top + h > window.innerHeight - pad) top = window.innerHeight - h - pad
    if (top < pad) top = pad
    setPos({ top, left })
  }, [anchor, usePopover, showDetails, type, isMeal])

  function selectRecipe(id: string) {
    setRecipeId(id)
    const recipe = recipes.find((r) => r.id === id)
    if (recipe) setTitle(recipe.name)
  }

  function save() {
    const resolvedTitle =
      isMeal && selectedRecipe
        ? selectedRecipe.name
        : title.trim() || (type === 'personal' ? 'Untitled' : type)
    const body: Record<string, unknown> = {
      title: resolvedTitle,
      type,
      start: new Date(start).toISOString(),
      end: new Date(end).toISOString(),
      all_day: false,
    }
    if (type === 'exercise') body.activity = activity
    if (type === 'meal') {
      body.recipe_id = recipeId || null
      body.portions = portions
    }
    onSave(body)
  }

  const whenLabel = formatWhen(new Date(start), new Date(end))
  const activeChip = TYPE_CHIPS.find((c) => c.type === type)

  const panel = (
    <div
      ref={panelRef}
      className={`w-full max-w-sm overflow-hidden rounded-xl border border-[var(--color-line)] bg-[var(--color-paper)] shadow-xl ${
        usePopover ? 'max-h-[min(80vh,560px)] overflow-y-auto' : ''
      }`}
      role="dialog"
      aria-label={isNew ? 'Create event' : 'Edit event'}
      style={
        usePopover && pos
          ? { position: 'fixed', top: pos.top, left: pos.left, width: 360, zIndex: 60 }
          : usePopover
            ? { position: 'fixed', top: -9999, left: -9999, width: 360, visibility: 'hidden' }
            : undefined
      }
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* Colored top bar matching type */}
      <div className={`h-1.5 ${activeChip?.pastel.split(' ')[0] ?? 'bg-[var(--color-moss-soft)]'}`} />

      <div className="flex items-start gap-2 px-4 pb-2 pt-3">
        <input
          ref={titleRef}
          className="min-w-0 flex-1 border-0 bg-transparent text-xl font-medium outline-none placeholder:text-[var(--color-ink)]/30"
          value={isMeal && selectedRecipe ? selectedRecipe.name : title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Add title"
          readOnly={isMeal}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              save()
            }
          }}
        />
        <button
          type="button"
          className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-lg leading-none text-[var(--color-ink)]/40 hover:bg-black/5 hover:text-[var(--color-ink)]"
          aria-label="Close"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      <div className="space-y-3 px-4 pb-3 text-sm">
        <div className="flex items-center gap-2 text-[var(--color-ink)]/65">
          <span className="inline-flex h-5 w-5 items-center justify-center text-[var(--color-ink)]/35" aria-hidden>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6.5" stroke="currentColor" />
              <path d="M8 4.5V8l2.5 1.5" stroke="currentColor" strokeLinecap="round" />
            </svg>
          </span>
          <span>{whenLabel}</span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {TYPE_CHIPS.map((chip) => (
            <button
              key={chip.type}
              type="button"
              onClick={() => {
                setType(chip.type)
                if (chip.type === 'meal' && selectedRecipe) setTitle(selectedRecipe.name)
                if (chip.type === 'meal' || chip.type === 'exercise') setShowDetails(true)
              }}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-opacity ${
                type === chip.type ? chip.pastel : 'border-transparent bg-black/[0.04] text-[var(--color-ink)]/55 hover:bg-black/[0.07]'
              }`}
            >
              {chip.label}
            </button>
          ))}
        </div>

        {(showDetails || isMeal || type === 'exercise') && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <span className="text-[10px] uppercase tracking-wide text-[var(--color-ink)]/45">Start</span>
                <input
                  type="datetime-local"
                  className="field mt-1 text-sm"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                />
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-wide text-[var(--color-ink)]/45">End</span>
                <input
                  type="datetime-local"
                  className="field mt-1 text-sm"
                  value={end}
                  onChange={(e) => setEnd(e.target.value)}
                />
              </label>
            </div>

            {type === 'exercise' && (
              <label className="block">
                <span className="text-[10px] uppercase tracking-wide text-[var(--color-ink)]/45">Activity</span>
                <select
                  className="field mt-1"
                  value={activity ?? ''}
                  onChange={(e) => setActivity(e.target.value as 'cycling' | 'gym')}
                >
                  <option value="cycling">Cycling</option>
                  <option value="gym">Gym</option>
                </select>
              </label>
            )}

            {isMeal && (
              <>
                <label className="block">
                  <span className="text-[10px] uppercase tracking-wide text-[var(--color-ink)]/45">Meal</span>
                  <select
                    className="field mt-1"
                    value={recipeId}
                    onChange={(e) => selectRecipe(e.target.value)}
                  >
                    {mealChoices.length === 0 && <option value="">No meals in library</option>}
                    {mealChoices.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                        {r.meal_type ? ` (${r.meal_type})` : ''}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="text-[10px] uppercase tracking-wide text-[var(--color-ink)]/45">Portions</span>
                  <input
                    type="number"
                    min={0.5}
                    step={0.5}
                    className="field mt-1"
                    value={portions}
                    onChange={(e) => setPortions(Number(e.target.value))}
                  />
                </label>
                {selectedRecipe ? (
                  <RecipePreview recipe={selectedRecipe} portions={portions} />
                ) : (
                  <p className="text-sm text-[var(--color-ink)]/55">Add meals in the Meals library to pick one here.</p>
                )}
              </>
            )}
          </>
        )}

        {isNew && !showDetails && type === 'personal' && (
          <button
            type="button"
            className="text-xs text-[var(--color-moss)] hover:underline"
            onClick={() => setShowDetails(true)}
          >
            More options
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-[var(--color-line)] bg-[var(--color-moss-soft)]/25 px-4 py-2.5">
        <button type="button" className="btn-primary" onClick={save}>
          {isNew ? 'Save' : 'Update'}
        </button>
        <button type="button" className="btn-ghost" onClick={onClose}>
          Cancel
        </button>
        {onDuplicate && (
          <button type="button" className="btn-ghost" onClick={onDuplicate}>
            Duplicate
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            className="ml-auto text-sm text-[var(--color-warn)] hover:underline"
            onClick={onDelete}
          >
            Delete
          </button>
        )}
      </div>
    </div>
  )

  if (usePopover) {
    return (
      <div className="fixed inset-0 z-50" onMouseDown={onClose}>
        {panel}
      </div>
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/20 p-4 pt-[10vh] backdrop-blur-[1px]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {panel}
    </div>
  )
}
