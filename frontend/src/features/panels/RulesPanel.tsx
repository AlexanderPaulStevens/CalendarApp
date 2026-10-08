import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import * as api from '../../lib/api'
import { rulePastelClass } from '../../lib/ruleColors'
import type { PlanSnapshot, Rule, RuleKey } from '../../lib/types'

interface Props {
  plan: PlanSnapshot
  onPlan: (plan: PlanSnapshot) => void
}

const PARAM_LABELS: Record<string, string> = {
  goal_hours: 'Weekly goal (hours)',
  session_min_hours: 'Session min (hours)',
  session_max_hours: 'Session max (hours)',
  exercise_earliest_hour: 'Earliest hour',
  max_exercise_blocks_per_day: 'Max sessions per day',
  max_exercise_hours_per_day: 'Max exercise hours per day',
  weekend_min_hours: 'Weekend exercise min (hours)',
  morning_end_hour: 'Morning ends (hour)',
  evening_start_hour: 'Evening starts (hour)',
  cycling_latest_end_hour: 'Cycling latest end (hour)',
  breakfast_hour: 'Breakfast hour',
  lunch_hour: 'Lunch hour',
  dinner_hour: 'Dinner hour',
  meal_duration_min: 'Meal duration (min)',
  lunch_duration_min: 'Lunch duration (min)',
  activity_threshold_hours: 'Activity threshold (hours)',
  protein_target_g: 'Protein target (g)',
  carbohydrate_target_g: 'Carb target (g)',
  shopping_duration_min: 'Trip duration (min)',
  weekend_goal_hours: 'Weekend study goal (hours)',
  weekend_earliest_hour: 'Weekend study earliest hour',
  weekend_latest_hour: 'Weekend study latest hour',
  weekend_block_min_hours: 'Weekend study block min (hours)',
  weekend_block_max_hours: 'Weekend study block max (hours)',
}

const RULE_ORDER: RuleKey[] = [
  'weekly_exercise_goal',
  'daily_meals',
  'work_schedule',
  'study_schedule',
  'batch_shopping',
]

function paramEntries(rule: Rule): [string, unknown][] {
  return Object.entries(rule.parameters).filter(
    ([key]) => key !== 'work_blocks' && key !== 'study_blocks' && key !== 'no_morning_weekdays',
  )
}

function ParamsEditor({
  rule,
  busy,
  onSave,
  onCancel,
}: {
  rule: Rule
  busy?: boolean
  onSave: (parameters: Record<string, unknown>) => void
  onCancel: () => void
}) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    for (const [k, v] of paramEntries(rule)) {
      init[k] = v === null || v === undefined ? '' : String(v)
    }
    return init
  })

  return (
    <form
      className="mt-3 space-y-2 border-t border-[var(--color-line)] pt-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault()
        const parameters: Record<string, unknown> = {}
        for (const [k, raw] of Object.entries(values)) {
          const trimmed = raw.trim()
          if (trimmed === '') {
            parameters[k] = null
            continue
          }
          const asNum = Number(trimmed)
          parameters[k] = Number.isFinite(asNum) ? asNum : trimmed
        }
        onSave(parameters)
      }}
    >
      {paramEntries(rule).map(([key]) => (
        <label key={key} className="block">
          <span className="text-xs uppercase tracking-wide opacity-60">
            {PARAM_LABELS[key] ?? key}
          </span>
          <input
            className="field mt-1"
            value={values[key] ?? ''}
            onChange={(e) =>
              setValues((prev) => ({ ...prev, [key]: e.target.value }))
            }
          />
        </label>
      ))}
      {rule.rule_key === 'work_schedule' && (
        <p className="text-xs opacity-60">
          Work blocks are configured in rule parameters as structured data;
          toggle the rule to place or clear Auto work events.
        </p>
      )}
      {rule.rule_key === 'study_schedule' && (
        <p className="text-xs opacity-60">
          Study blocks are configured in rule parameters as structured data;
          toggle the rule to place or clear Auto study events.
        </p>
      )}
      <div className="flex gap-3 pt-1">
        <button type="submit" disabled={busy} className="btn-primary">
          Save parameters
        </button>
        <button type="button" className="btn-ghost" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

export function RulesPanel({ plan, onPlan }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null)

  const updateMut = useMutation({
    mutationFn: (args: { id: string; body: Record<string, unknown> }) =>
      api.updateRule(args.id, args.body),
    onSuccess: (next) => {
      setEditingId(null)
      onPlan(next)
    },
  })

  const ordered = [...plan.rules].sort(
    (a, b) => RULE_ORDER.indexOf(a.rule_key) - RULE_ORDER.indexOf(b.rule_key),
  )

  const exercise = plan.rules.find((r) => r.rule_key === 'weekly_exercise_goal')
  const goal = Number(exercise?.parameters.goal_hours ?? plan.week_summary.goal_hours)
  const sessionMin = Number(exercise?.parameters.session_min_hours ?? 1.0)
  const sessionMax = Number(exercise?.parameters.session_max_hours ?? 3.0)

  return (
    <div className="min-h-0 flex-1 overflow-auto px-4 py-4">
      <p className="mb-4 text-sm opacity-70">
        Turn rules on or off to reshape this week&apos;s Auto blocks. Edit
        parameters to change goals, meal times, and placement constraints.
      </p>

      <ul className="space-y-3">
        {ordered.map((rule) => (
          <li
            key={rule.id}
            className={`rounded-xl border px-3.5 py-3.5 ${rulePastelClass(rule.rule_key)}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-medium">{rule.name}</div>
                <div className="mt-0.5 text-xs uppercase tracking-wide opacity-50">
                  {rule.rule_key}
                </div>
                {rule.explanation && (
                  <p className="mt-2 text-sm opacity-70">{rule.explanation}</p>
                )}
              </div>
              <label className="flex shrink-0 items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={rule.enabled}
                  disabled={updateMut.isPending}
                  onChange={(e) =>
                    updateMut.mutate({
                      id: rule.id,
                      body: { enabled: e.target.checked },
                    })
                  }
                />
                On
              </label>
            </div>
            <div className="mt-2 flex gap-3 text-sm">
              <button
                type="button"
                className="font-medium text-[var(--color-moss)] underline decoration-[var(--color-moss-edge)] underline-offset-2"
                onClick={() =>
                  setEditingId((id) => (id === rule.id ? null : rule.id))
                }
              >
                {editingId === rule.id ? 'Close' : 'Parameters'}
              </button>
            </div>
            {editingId === rule.id && (
              <ParamsEditor
                rule={rule}
                busy={updateMut.isPending}
                onCancel={() => setEditingId(null)}
                onSave={(parameters) =>
                  updateMut.mutate({ id: rule.id, body: { parameters } })
                }
              />
            )}
          </li>
        ))}
      </ul>

      <p className="mt-6 text-xs opacity-50">
        Goal {goal}h/week · sessions {sessionMin}–{sessionMax}h · timezone{' '}
        {plan.timezone}
      </p>
    </div>
  )
}
