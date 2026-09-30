---
name: create-skill
description: >-
  Create or refine a project Cursor skill that packages a repeatable procedure
  into .cursor/skills/<name>/SKILL.md. Use when the user wants to draft, add,
  or revise a skill in this repository.
---

# Create Skill

Help users create Cursor Agent Skills in this repo.

## Structure

A skill is a folder under `.cursor/skills/<skill-name>/` with `SKILL.md` (metadata + instructions) and optional files (templates, examples, references, scripts). Keep instructions tight; attach files only when a step needs an example.

## Workflow

1. Clarify the repeatable task and expected output.
2. Draft three parts:
   - **Name** — lowercase letters, numbers, and hyphens only (max 64 characters).
   - **Description** — third person. State what the skill does and when to use it. Be specific:
     - Bad: "Helps with meetings."
     - Good: "Summarize meeting notes into an executive summary, action items, and open questions. Use when the user pastes meeting notes and asks for a summary with owners."
   - **SKILL.md body** — the procedure: steps, output format, tone, what to avoid.
3. Write concise instructions. Example:

   ```
   When given meeting notes or a transcript, produce:
   1. A one-paragraph executive summary (max 80 words).
   2. Action items with owners and due dates ([TBD] if missing).
   3. Open questions.
   Tone: professional, concise. Don't invent information not in the source.
   ```

4. Save to `.cursor/skills/<skill-name>/SKILL.md` in this repo. Cursor discovers project skills from that directory. Do not write skills under `~/.cursor/skills-cursor/`.
5. Omit `disable-model-invocation` when the agent should apply the skill from context. Set `disable-model-invocation: true` only when the skill should load when the user names it.
6. Try the skill with a matching prompt and iterate if the format drifts.

## Minimal scaffold

```markdown
---
name: your-skill-name
description: Does X when the user asks for Y. Use when [specific trigger — input, action, expected output].
---

# Your Skill Title

When given [input], produce:

1. [Output section 1]
2. [Output section 2]

**Tone:** [e.g. professional, concise]

**Don't:** invent information not in the source.
```

## Checklist

- Description is a trigger condition, not a vague topic.
- Description is third person and includes both what and when.
- Instructions specify format, tone, and constraints.
- SKILL.md stays under 500 lines.
- Supporting files are one level deep and referenced from SKILL.md when used.
