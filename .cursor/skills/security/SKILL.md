---
name: security
description: >-
  Apply security invariants, self-review, and supply-chain checks when writing,
  reviewing, or refactoring security-sensitive code; handling auth, secrets, or
  user input; adding dependencies; or before marking any change complete.
  Use when the user mentions security review, secrets, auth, injection, or
  dependency adds.
---

# Security

Repo-agnostic security rules. Read project `AGENTS.md` first — it overrides this skill for repo-specific auth, config, and license policy.

## Usage

Apply to the scope the user names: a file, a directory, or changed files only. If no scope is given, use the files touched in the current task.

## Workflow

1. **Read repo context** — `AGENTS.md`, auth patterns, secret/config layout.
2. **Apply invariants** — rules below while writing or editing.
3. **Self-review** — run the reflection loop before reporting done.
4. **Verify dependencies** — if any package was added, complete the supply-chain checklist.

## Invariants (always apply)

- Never hardcode secrets, API keys, or credentials — use env vars or the project's secret config
- Validate all external input at API/service boundaries (schema validation, not raw dict access)
- Parameterized queries only — never build SQL with string interpolation from user input
- Sanitize logs and error responses — no stack traces, internal paths, or credentials to clients
- Don't log sensitive data (tokens, credentials, PII)
- Use the project's existing auth/permissions patterns — don't bypass checks
- Be careful with code execution boundaries (sandboxes, subprocess, `eval`, deserialization)

## Self-reflection loop (before marking task done)

After generating or modifying security-sensitive code, review your own output:

1. **Injection** — string-built SQL, shell commands, or file paths from user input?
2. **Secrets** — hardcoded keys, tokens, or credentials? Secrets in logs/errors?
3. **Auth** — new endpoints or actions protected? Permissions checked?
4. **Input validation** — unvalidated user data reaching services or persistence?
5. **Error leakage** — exceptions exposing internals to API responses?
6. **Deserialization** — unsafe `pickle`, `eval`, or unchecked file parsing?

Fix issues before reporting completion.

## Supply chain vigilance

AI-suggested packages may not exist (slopsquatting) or carry bad licenses. Before adding any dependency:

1. **Verify existence** — confirm the exact package name on the official registry (PyPI, npm, etc.)
2. **Check necessity** — prefer existing project dependencies over new ones
3. **Add via project manifest** — `pyproject.toml`, `package.json`, `go.mod`, etc.
4. **License check** — follow the repo's license policy if one exists
5. **Update lockfile** — keep lockfiles in sync with manifest changes
6. Review transitive dependencies for known issues

## Output format (review mode)

```markdown
## Security pass — [scope]

### Issues fixed
- [file:line] — [change]

### Issues flagged (not fixed)
- [file:line] — [issue] — [recommended fix]

### Repo overrides kept
- [AGENTS.md rule and why]
```
