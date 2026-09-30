# Imports — Google Python Style Reference

Source: [§2.2 Imports](https://google.github.io/styleguide/pyguide.html#s2.2-imports), [§3.13 Imports formatting](https://google.github.io/styleguide/pyguide.html#s3.13-imports-formatting), [§3.19.12–13 Typing imports](https://google.github.io/styleguide/pyguide.html#s3.19.12-imports-for-typing).

## §2.2 — What to import

**Decision:** Use `import` for packages and modules. Do not import individual types, classes, or functions from application code.

**Exemptions** (may import symbols directly):

- `typing`
- `collections.abc`
- `typing_extensions`

### `from x import y as z` — allowed when

1. Two different modules both named `y` are imported
2. `y` conflicts with a name in the current module
3. `y` conflicts with a public API parameter name
4. `y` is inconveniently long
5. `y` is too generic in context (e.g. `options` → `fs_options`)

### Relative imports

**Do not use** relative imports (`from . import foo`). Use the full package path.

## §2.3 — Full pathname

```python
# Yes
from doctor.who import jodie

# No — unclear which jodie
import jodie
```

## §3.13 — Formatting and placement

1. Top of file, after module comments/docstring, before globals
2. One per line except `typing` / `collections.abc` multi-imports
3. Groups: `__future__` → stdlib → third-party → repo/local
4. Sort lexicographically within each group (case-insensitive, full path)
5. Optional blank line between groups

## §3.19.12 — Typing imports

- Multi-import on one line OK for `typing` / `collections.abc`
- Prefer abstract containers: `Sequence[tuple[float, float]]` over `List[Tuple[...]]`
- With `from __future__ import annotations`, use lowercase builtins where appropriate

## §3.19.13 — Conditional imports

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sketch

def f(x: "sketch.Sketch") -> None: ...
```

Block immediately after normal imports; no blank lines inside; typing-only symbols.

## Project overrides

Check `AGENTS.md` in the repo — common rules: no `load_dotenv`, no `os.getenv` in app code, use a central settings module instead.
