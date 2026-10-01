# Calendar Planner

Personal planning calendar: events, meals, shopping, and Rules that the plan engine continuously enforces.

## Language

**Rule**:
A named planner policy identified by a stable `rule_key` (for example `weekly_exercise_goal`). The key implies both when it applies and how the engine enforces it. Parameters, enablement, and UI name/explanation hang off that key. When enabled, the engine enforces it on every recalculation.
_Avoid_: Setting (for policies/goals), preference, config, condition_key, action_key

**Scheduling Rule**:
A Rule whose enforcement maintains calendar blocks (for example a weekly exercise goal that auto-places exercise).
_Avoid_: Replan, rebuild auto blocks (as a separate user action)

**Advisory Rule**:
A Rule whose enforcement produces suggestions or warnings the user can accept, ignore, or suppress — it does not place events by itself.
_Avoid_: Soft setting

**Auto event**:
An event with origin auto, owned by a Scheduling Rule; recalculation may create, move, or delete it. User events are never moved by Rules.
_Avoid_: Suggested event (suggestions are proposals, not placed events)

**Rule parameter**:
A typed value that belongs on exactly one owning Rule (for example weekly hours on the exercise Scheduling Rule). Other Rules may read an owner's parameters only while that owner is enabled; parameters are never duplicated across Rules. Planner configuration lives only as Rule parameters — there is no separate settings object.
_Avoid_: AppSettings, settings, config knobs, shared settings bag

**rule_key**:
The stable identity of a Rule type. One key maps to one evaluation and one enforcement behavior in the engine. The catalog of keys is closed: the API may create an instance of a known key (for example when a new Rule is introduced), but cannot invent unknown keys.
_Avoid_: condition_key, action_key, rule id (id is the instance; rule_key is the type), open-ended custom rules
