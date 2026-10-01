import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import * as api from '../../lib/api'
import type { PlanSnapshot, Unit } from '../../lib/types'

const FRIDGE = 'fridge'

interface Props {
  plan: PlanSnapshot
  onPlan: (plan: PlanSnapshot) => void
}

export function FridgePanel({ plan, onPlan }: Props) {
  const [name, setName] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [unit, setUnit] = useState<Unit>('g')
  const [error, setError] = useState('')

  const fridge = plan.fridge.filter((item) => item.location.toLowerCase() === FRIDGE)

  const add = useMutation({
    mutationFn: async () => {
      const label = name.trim()
      const amount = Number(quantity)
      if (!label) throw new Error('Name what you are putting in the fridge.')
      if (!Number.isFinite(amount) || amount < 0) {
        throw new Error('Amount has to be zero or more.')
      }
      const existing = fridge.find(
        (item) => item.name.toLowerCase() === label.toLowerCase() && item.unit === unit,
      )
      if (existing) {
        return api.updateFridgeItem(existing.id, { quantity: existing.quantity + amount })
      }
      return api.createFridgeItem({
        name: label,
        quantity: amount,
        unit,
        location: FRIDGE,
      })
    },
    onSuccess: (next) => {
      setName('')
      setQuantity('1')
      setError('')
      onPlan(next)
    },
    onError: (err: Error) => setError(err.message),
  })

  const updateQty = useMutation({
    mutationFn: (args: { id: string; quantity: number }) =>
      api.updateFridgeItem(args.id, { quantity: args.quantity }),
    onSuccess: onPlan,
  })

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteFridgeItem(id),
    onSuccess: onPlan,
  })

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-auto px-5">
        {fridge.length === 0 && (
          <p className="py-6 text-sm opacity-60">The fridge is empty.</p>
        )}
        <ul>
          {fridge.map((item) => (
            <li
              key={item.id}
              className="flex items-center gap-3 border-b border-[var(--color-line)]/70 py-3 text-sm"
            >
              <span className="min-w-0 flex-1">{item.name}</span>
              <input
                type="number"
                min={0}
                step="any"
                aria-label={`${item.name} amount`}
                className="field w-20"
                defaultValue={item.quantity}
                key={`${item.id}-${item.quantity}`}
                onBlur={(e) => {
                  const next = Number(e.target.value)
                  if (!Number.isFinite(next) || next < 0 || next === item.quantity) return
                  updateQty.mutate({ id: item.id, quantity: next })
                }}
              />
              <span className="w-6 opacity-70">{item.unit}</span>
              <button
                type="button"
                className="text-[var(--color-warn)] underline underline-offset-2"
                onClick={() => remove.mutate(item.id)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
        {error && <p className="py-2 text-sm text-[var(--color-warn)]">{error}</p>}
      </div>
      <form
        className="flex flex-col gap-2 border-t border-[var(--color-line)] bg-[var(--color-moss-soft)]/20 p-4"
        onSubmit={(e) => {
          e.preventDefault()
          add.mutate()
        }}
      >
        <label className="flex flex-col gap-1 text-sm">
          Item
          <input
            className="field"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Add item…"
          />
        </label>
        <div className="flex items-end gap-2">
          <label className="flex flex-col gap-1 text-sm">
            Amount
            <input
              type="number"
              min={0}
              step="any"
              className="field w-24"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Unit
            <select
              className="field"
              value={unit}
              onChange={(e) => setUnit(e.target.value as Unit)}
            >
              <option value="g">g</option>
              <option value="ml">ml</option>
            </select>
          </label>
          <button type="submit" className="btn-primary" disabled={add.isPending}>
            Add
          </button>
        </div>
      </form>
    </div>
  )
}
