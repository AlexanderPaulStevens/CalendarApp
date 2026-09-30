---
name: google-python-style
description: >-
  Review or fix Python against the Google Python Style Guide, especially
  imports (sections 2.2, 3.13, and 3.19.12–13). Use when the user mentions
  Google style, pyguide, import cleanup, or a Python style review.
---

# Google Python Style

Apply the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html). Emphasis: **imports** ([§2.2](https://google.github.io/styleguide/pyguide.html#s2.2-imports), [§3.13](https://google.github.io/styleguide/pyguide.html#s3.13-imports-formatting), [§3.19.12–13](https://google.github.io/styleguide/pyguide.html#s3.19.12-imports-for-typing)).

**Precedence:** project `AGENTS.md` files override this guide. Call out intentional deviations.

## Usage

Apply to the scope the user names: a file, a directory, or changed files only. If no scope is given, use the files touched in the current task.

## Workflow

1. **Scope** — Use the path the user names, `@` mentions, or recent edits. Read project `AGENTS.md` if present.
2. **Imports first** — Run the checklist on every file in scope.
3. **Fix in place** — Minimal diffs.
4. **Broader pass** — Only if imports are clean or the user asked; see [style-checklist.md](style-checklist.md).
5. **Report** — Use the output format below.

## Import checklist

```
Import audit:
- [ ] All imports at top (after docstring, before globals)
- [ ] No imports inside functions, loops, or methods
- [ ] One import per line (exception: typing / collections.abc / typing_extensions)
- [ ] Grouped: __future__ → stdlib → third-party → repo/local
- [ ] Blank line between groups (preferred)
- [ ] Sorted lexicographically within each group (full package path, case-insensitive)
- [ ] Packages/modules imported, not individual functions/classes
- [ ] Exemptions only: typing, collections.abc, typing_extensions
- [ ] No relative imports (from . import x)
- [ ] Full package paths for repo modules
- [ ] from x import y as z only when justified
- [ ] TYPE_CHECKING block after normal imports (if needed)
- [ ] Prefer collections.abc over concrete types in annotations
```

## Quick rules

**Import modules, not symbols** (except typing exemptions):

```python
import os
from doctor.who import jodie

from collections.abc import Mapping, Sequence
from typing import Any, Protocol
```

**Top-of-file order:**

```python
from __future__ import annotations

import json
import os
from typing import Any

import requests
from mistralai.client import Mistral

from myproject.backend import service
```

## Common fixes

| Problem | Fix | Section |
|--------|-----|---------|
| `import json` inside a function | Move to top | §3.13 |
| `load_dotenv()` in app code | Use project settings module | project AGENTS.md |
| `from typing import List` | Use `list` or `collections.abc.Sequence` | §3.19.12 |
| `import os, sys` | Split to separate lines | §3.13 |

## Output format

```markdown
## Google style pass — [scope]

### Fixed
- [file:line] — [change] (§section)

### Suggestions (not applied)
- [file:line] — [issue] — [recommended fix]

### Repo overrides kept
- [AGENTS.md rule and why]
```

## References

- [imports-reference.md](imports-reference.md) — import edge cases
- [style-checklist.md](style-checklist.md) — broader pyguide pass
- https://google.github.io/styleguide/pyguide.html
