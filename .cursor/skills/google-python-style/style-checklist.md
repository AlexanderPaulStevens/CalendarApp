# Broader Google Python Style Checklist

Use after import cleanup, or when the user requests a full style pass.  
Source: [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).

**Repo precedence:** project `AGENTS.md` files override this list.

## Language & layout

- [ ] **§2.1** — `pylint` disables only with comment explaining why
- [ ] **§2.20** — `from __future__ import annotations` when using forward refs
- [ ] **§3.2** — Max line length 80 (match project formatter if configured)
- [ ] **§3.4** — 4 spaces, no tabs
- [ ] **§3.14** — One statement per line

## Naming (§3.16)

- [ ] `module_name`, `function_name`, `ClassName`, `GLOBAL_CONSTANT_NAME`
- [ ] Internal helpers: `_leading_underscore`

## Docstrings (§3.8)

- [ ] Public modules, classes, functions documented
- [ ] Imperative one-line summary

## Type annotations (§2.21, §3.19)

- [ ] Public APIs annotated
- [ ] Avoid `Any` unless at boundaries

## What not to over-enforce

- Rewriting all docstrings in legacy files
- Naming-only public API renames
- 80-char reflow in unrelated code
