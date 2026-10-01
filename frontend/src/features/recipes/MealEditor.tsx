import { useEffect, useState } from 'react'
import type { IngredientLine, Recipe, Unit } from '../../lib/types'

export type RecipeFormValues = Omit<Recipe, 'id'>

function emptyIngredient(): IngredientLine {
  return { name: '', quantity: 0, unit: 'g' }
}

function toForm(recipe?: Recipe | null): RecipeFormValues {
  if (!recipe) {
    return {
      name: '',
      ingredients: [emptyIngredient()],
      calories: 0,
      protein_g: 0,
      carbohydrates_g: 0,
      fat_g: 0,
      fiber_g: 0,
      preparation_time_min: 0,
      cuisine: '',
      meal_type: '',
      portion_size: '1 serving',
      storage_requirements: '',
      shelf_life_days: null,
      freezer_suitable: false,
    }
  }
  const { id: _id, ...rest } = recipe
  void _id
  return {
    ...rest,
    ingredients:
      rest.ingredients.length > 0
        ? rest.ingredients.map((i) => ({ ...i }))
        : [emptyIngredient()],
  }
}

interface Props {
  initial?: Recipe | null
  title: string
  submitLabel: string
  busy?: boolean
  onCancel: () => void
  onSubmit: (values: RecipeFormValues) => void
}

export function MealEditor({
  initial,
  title,
  submitLabel,
  busy,
  onCancel,
  onSubmit,
}: Props) {
  const [form, setForm] = useState<RecipeFormValues>(() => toForm(initial))

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.stopImmediatePropagation()
      onCancel()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onCancel])

  function setField<K extends keyof RecipeFormValues>(key: K, value: RecipeFormValues[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function setIngredient(index: number, patch: Partial<IngredientLine>) {
    setForm((f) => ({
      ...f,
      ingredients: f.ingredients.map((ing, i) => (i === index ? { ...ing, ...patch } : ing)),
    }))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="max-h-[90vh] w-full max-w-lg overflow-auto rounded-2xl border border-[var(--color-line)] bg-[var(--color-paper)] p-5 shadow-xl">
        <h2 className="font-[family-name:var(--font-display)] text-2xl">{title}</h2>
        <form
          className="mt-4 space-y-3 text-sm"
          onSubmit={(e) => {
            e.preventDefault()
            const cleaned = {
              ...form,
              ingredients: form.ingredients.filter((i) => i.name.trim() && i.quantity > 0),
            }
            if (!cleaned.name.trim()) return
            onSubmit(cleaned)
          }}
        >
          <label className="block">
            <span className="text-xs uppercase tracking-wide opacity-60">Name</span>
            <input
              className="field mt-1"
              value={form.name}
              onChange={(e) => setField('name', e.target.value)}
              required
            />
          </label>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {(
              [
                ['calories', 'Calories'],
                ['protein_g', 'Protein g'],
                ['carbohydrates_g', 'Carbs g'],
                ['fat_g', 'Fat g'],
                ['fiber_g', 'Fiber g'],
                ['preparation_time_min', 'Prep min'],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="block">
                <span className="text-xs uppercase tracking-wide opacity-60">{label}</span>
                <input
                  type="number"
                  min={0}
                  step="any"
                  className="field mt-1"
                  value={form[key]}
                  onChange={(e) => setField(key, Number(e.target.value))}
                />
              </label>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-xs uppercase tracking-wide opacity-60">Cuisine</span>
              <input
                className="field mt-1"
                value={form.cuisine}
                onChange={(e) => setField('cuisine', e.target.value)}
              />
            </label>
            <label className="block">
              <span className="text-xs uppercase tracking-wide opacity-60">Meal type</span>
              <input
                className="field mt-1"
                value={form.meal_type}
                onChange={(e) => setField('meal_type', e.target.value)}
              />
            </label>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide opacity-60">Ingredients</span>
              <button
                type="button"
                className="text-xs font-medium text-[var(--color-moss)] underline decoration-[var(--color-moss-edge)] underline-offset-2"
                onClick={() =>
                  setForm((f) => ({
                    ...f,
                    ingredients: [...f.ingredients, emptyIngredient()],
                  }))
                }
              >
                Add line
              </button>
            </div>
            <ul className="mt-2 space-y-2">
              {form.ingredients.map((ing, index) => (
                <li key={index} className="grid grid-cols-[1fr_4.5rem_3.5rem_auto] gap-1">
                  <input
                    placeholder="Name"
                    className="field"
                    value={ing.name}
                    onChange={(e) => setIngredient(index, { name: e.target.value })}
                  />
                  <input
                    type="number"
                    min={0}
                    step="any"
                    className="field"
                    value={ing.quantity}
                    onChange={(e) =>
                      setIngredient(index, { quantity: Number(e.target.value) })
                    }
                  />
                  <select
                    className="field"
                    value={ing.unit}
                    onChange={(e) =>
                      setIngredient(index, { unit: e.target.value as Unit })
                    }
                  >
                    <option value="g">g</option>
                    <option value="ml">ml</option>
                  </select>
                  <button
                    type="button"
                    className="text-xs text-[var(--color-warn)]"
                    onClick={() =>
                      setForm((f) => ({
                        ...f,
                        ingredients: f.ingredients.filter((_, i) => i !== index),
                      }))
                    }
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="flex flex-wrap gap-2 pt-2">
            <button type="submit" disabled={busy} className="btn-primary">
              {submitLabel}
            </button>
            <button type="button" className="btn-ghost" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
