# Calendar Planner

Personal planning calendar: events, meals, shopping, Rules that the plan engine continuously enforces, and Signals that prepare for upcoming Events.

## Language

**Rule**:
A named planner policy identified by a stable `rule_key` (for example `weekly_exercise_goal`). The key implies both when it applies and how the engine enforces it. Parameters, enablement, and UI name/explanation hang off that key. When enabled, the engine enforces it on every recalculation.
_Avoid_: Setting (for policies/goals), preference, config, condition_key, action_key

**Scheduling Rule**:
A Rule whose enforcement maintains calendar blocks (for example a weekly exercise goal that auto-places exercise). When disabled, recalculation removes the Auto events it owns; User events are left alone. `daily_meals` owns Auto meal slots and recipe choice: after exercise on the calendar, it may swap the recipe on the next Auto meal; User meals are never changed.
_Avoid_: Replan, rebuild auto blocks (as a separate user action)

**Auto event**:
An event with origin auto, owned by a Scheduling Rule; recalculation may create, move, or delete it.
_Avoid_: Suggested event

**User event**:
An event with origin user. Rules never move, resize, or delete it. Editing an Auto event claims it as a User event; Scheduling Rules then reflow only remaining Auto events around it.
_Avoid_: manual event, pinned event, override (as a separate entity)

**Signal**:
A derived prep marker for an upcoming Event: an instant before the Event, shown on the calendar (not as a duration block) and eligible to notify. Default timing is Event start minus a lead time; morning gym prep prefers the evening before. Every Signal is pinned into a work, study, or cooking (meal) block — never during a sporting Event — and omitted if no such host window exists. Signals may overlap those host Events; they are not Events and do not participate in placement or the non-overlap invariant. The engine emits them on every plan snapshot from the closed Signal template catalog; users do not create or edit Signals. When the owning Event moves or disappears, its Signals follow.
_Avoid_: Reminder event, advisory event, soft event, overlapping event, notification (as the entity itself)

**Signal template**:
A closed catalog entry that says when to emit a Signal: match on Event type and optional activity, plus optional recipe id or tag (for example overnight oats). It defines title/body and lead time before Event start. Templates live in code, not as Rule parameters or user-authored rows.
_Avoid_: Manual signal, per-event signal editor, Advisory Rule, settings knob for prep lists

**Rule parameter**:
A typed value that belongs on exactly one owning Rule (for example weekly hours on the exercise Scheduling Rule). Other Rules may read an owner's parameters only while that owner is enabled; parameters are never duplicated across Rules. Planner configuration lives only as Rule parameters — there is no separate settings object.
_Avoid_: AppSettings, settings, config knobs, shared settings bag

**Placement constraint**:
A Rule parameter that shapes how a Scheduling Rule may place Auto events (for example session min/max on `weekly_exercise_goal`, or trip duration on `batch_shopping`). It is not a Rule of its own. The engine applies it only when placing Auto events; User events are not checked against it. Free-time placement still obeys the non-overlap planner invariant. Farm Leuven open hours for shopping are fixed in code, not Rule parameters.
_Avoid_: nested rule, soft setting, config knob, session_too_short / session_too_long / walking_over_cap (as catalog Rules)

**Plan week**:
The Mon–Sun local calendar week that `recalculate` rewrites for a given anchor date. Other weeks' Auto events stay as persisted until that week is fetched. There is no multi-week planning horizon or preload window.
_Avoid_: planning horizon, preload weeks

**rule_key**:
The stable identity of a Rule type. One key maps to one evaluation and one enforcement behavior in the engine. The catalog of keys is closed: the API may create an instance of a known key (for example when a new Rule is introduced), but cannot invent unknown keys. At most one Rule instance per `rule_key` exists in state.
_Avoid_: condition_key, action_key, open-ended custom rules, multiple instances of the same key

**Rule instance**:
The persisted Rule row for one `rule_key`: stable `id`, display name/explanation, enablement, and that key's parameters. The catalog supplies defaults and if→then semantics; state holds the configured instances. The API only patches enablement and parameters; it does not create or delete instances. Missing catalog keys are merged into state on load.
_Avoid_: rules map keyed only by rule_key (no id), settings overlay, user-authored create/delete

**Planner invariant**:
A constraint the engine always applies; it is not a catalog Rule and cannot be disabled. Non-overlap of timed Events is a planner invariant: Auto placement never stacks, and conflicting User events are marked, not moved. Signals are outside this invariant.
_Avoid_: overlap rule, resolve_overlap (as a user-facing Rule)

**Shelf life**:
How many days after purchase an ingredient stays usable (buy day through buy date plus those days). Stored on the fridge item; `null` means pantry or freezer with no buy-ahead limit. Shopping only assigns a perishable to a store trip when the meal falls inside that window.
_Avoid_: expiration alone (as the buy-ahead policy), recipe leftover days (cooked `shelf_life_days` on a Recipe)

**Work event**:
An Event with type `work`. Hours count toward the `work_schedule` weekly goal; User work hours reduce how much Auto work the engine places that Plan week.
_Avoid_: personal event titled Work, meeting-as-work without the work type

**Study event**:
An Event with type `study`. Weekday User study claims that day's Auto study; weekend User study hours count toward `weekend_goal_hours` packing.
_Avoid_: personal event titled Study
