import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { MealEditor, type RecipeFormValues } from '../recipes/MealEditor'
import * as api from '../../lib/api'
import type { PlanSnapshot, Recipe } from '../../lib/types'

interface Props {
  plan: PlanSnapshot
  onPlan: (plan: PlanSnapshot) => void
}

function RecipeCard({
  recipe,
  onEdit,
  onDelete,
}: {
  recipe: Recipe
  onEdit?: () => void
  onDelete?: () => void
}) {
  return (
    <li className="border-b border-[var(--color-line)]/80 pb-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-[family-name:var(--font-display)] text-2xl">{recipe.name}</h3>
        <div className="flex shrink-0 gap-3">
          {onEdit && (
            <button
              type="button"
              className="text-sm font-medium text-[var(--color-moss)] underline decoration-[var(--color-moss-edge)] underline-offset-2"
              onClick={onEdit}
            >
              Edit
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              className="text-sm text-[var(--color-warn)] underline underline-offset-2"
              onClick={onDelete}
            >
              Remove
            </button>
          )}
        </div>
      </div>
      <p className="mt-1 text-sm opacity-70">
        {recipe.calories} kcal · P {recipe.protein_g}g · C {recipe.carbohydrates_g}g · F{' '}
        {recipe.fat_g}g
      </p>
      <ul className="mt-2 text-sm opacity-80">
        {recipe.ingredients.map((ing) => (
          <li key={`${ing.name}-${ing.quantity}`}>
            {ing.quantity}
            {ing.unit} {ing.name}
          </li>
        ))}
      </ul>
    </li>
  )
}

function recipeBody(values: RecipeFormValues): Record<string, unknown> {
  return { ...values }
}

export function MealsPanel({ plan, onPlan }: Props) {
  const [message, setMessage] = useState('')
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Recipe | null>(null)
  const [creating, setCreating] = useState(false)

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteRecipe(id),
    onSuccess: onPlan,
  })

  const draftMut = useMutation({
    mutationFn: (text: string) => api.draftRecipe(text),
    onSuccess: (result) => {
      setDraft(result)
      setError(null)
    },
    onError: (err: Error) => {
      setError(err.message)
      setDraft(null)
    },
  })

  const saveMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.createRecipe(body),
    onSuccess: (next) => {
      setDraft(null)
      setMessage('')
      setCreating(false)
      onPlan(next)
    },
    onError: (err: Error) => setError(err.message),
  })

  const updateMut = useMutation({
    mutationFn: (args: { id: string; body: Record<string, unknown> }) =>
      api.updateRecipe(args.id, args.body),
    onSuccess: (next) => {
      setEditing(null)
      onPlan(next)
    },
    onError: (err: Error) => setError(err.message),
  })

  const draftAsRecipe = draft
    ? ({
        id: 'draft',
        name: String(draft.name ?? 'Draft'),
        ingredients: (draft.ingredients as Recipe['ingredients']) ?? [],
        calories: Number(draft.calories ?? 0),
        protein_g: Number(draft.protein_g ?? 0),
        carbohydrates_g: Number(draft.carbohydrates_g ?? 0),
        fat_g: Number(draft.fat_g ?? 0),
        fiber_g: Number(draft.fiber_g ?? 0),
        preparation_time_min: Number(draft.preparation_time_min ?? 0),
        cuisine: String(draft.cuisine ?? ''),
        meal_type: String(draft.meal_type ?? ''),
        portion_size: String(draft.portion_size ?? ''),
        storage_requirements: String(draft.storage_requirements ?? ''),
        shelf_life_days: (draft.shelf_life_days as number | null) ?? null,
        freezer_suitable: Boolean(draft.freezer_suitable),
      } satisfies Recipe)
    : null

  return (
    <div className="min-h-0 flex-1 overflow-auto px-4 py-4">
      <section className="mb-8 rounded-xl border border-[var(--color-rule-meals-edge)] bg-[var(--color-rule-meals)]/40 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-[family-name:var(--font-display)] text-2xl text-[var(--color-rule-meals-ink)]">
            Add a meal
          </h3>
          <button
            type="button"
            className="text-sm font-medium text-[var(--color-rule-meals-ink)] underline decoration-[var(--color-rule-meals-edge)] underline-offset-2"
            onClick={() => setCreating(true)}
          >
            Add manually
          </button>
        </div>
        <p className="mt-1 text-sm text-[var(--color-rule-meals-ink)]/70">
          Describe a meal in chat, or add one by hand. Chat returns a structured draft you can
          edit before saving.
        </p>
        <form
          className="mt-3 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (!message.trim()) return
            draftMut.mutate(message.trim())
          }}
        >
          <textarea
            className="field min-h-24 text-sm"
            placeholder="e.g. Lentil curry with 200g cooked lentils, coconut milk, spinach…"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          <button type="submit" disabled={draftMut.isPending} className="btn-primary self-start">
            {draftMut.isPending ? 'Drafting…' : 'Draft recipe'}
          </button>
        </form>
        {error && (
          <p className="mt-2 text-sm whitespace-pre-wrap text-[var(--color-warn)]">{error}</p>
        )}
        {draftAsRecipe && (
          <div className="mt-4 border-t border-[var(--color-line)] pt-4">
            <p className="text-xs uppercase tracking-wide opacity-60">Draft</p>
            <ul className="mt-2">
              <RecipeCard recipe={draftAsRecipe} onEdit={() => setEditing(draftAsRecipe)} />
            </ul>
            <div className="mt-3 flex gap-3">
              <button
                type="button"
                className="btn-primary"
                disabled={saveMut.isPending}
                onClick={() => saveMut.mutate(recipeBody(draftAsRecipe))}
              >
                Save to library
              </button>
              <button type="button" className="btn-ghost" onClick={() => setDraft(null)}>
                Discard
              </button>
            </div>
          </div>
        )}
      </section>

      <h3 className="font-[family-name:var(--font-display)] text-2xl">Your meals</h3>
      {plan.recipes.length === 0 && (
        <p className="mt-2 text-sm opacity-60">No meals yet. Add one above.</p>
      )}
      <ul className="mt-4 space-y-4">
        {plan.recipes.map((r) => (
          <RecipeCard
            key={r.id}
            recipe={r}
            onEdit={() => setEditing(r)}
            onDelete={() => {
              if (window.confirm(`Remove “${r.name}” from the library?`)) {
                deleteMut.mutate(r.id)
              }
            }}
          />
        ))}
      </ul>

      {creating && (
        <MealEditor
          title="New meal"
          submitLabel="Save"
          busy={saveMut.isPending}
          onCancel={() => setCreating(false)}
          onSubmit={(values) => saveMut.mutate(recipeBody(values))}
        />
      )}

      {editing && (
        <MealEditor
          key={editing.id}
          initial={editing}
          title={editing.id === 'draft' ? 'Edit draft' : 'Edit meal'}
          submitLabel="Save changes"
          busy={updateMut.isPending || saveMut.isPending}
          onCancel={() => setEditing(null)}
          onSubmit={(values) => {
            if (editing.id === 'draft') {
              setDraft({ ...values })
              setEditing(null)
              return
            }
            updateMut.mutate({ id: editing.id, body: recipeBody(values) })
          }}
        />
      )}
    </div>
  )
}
