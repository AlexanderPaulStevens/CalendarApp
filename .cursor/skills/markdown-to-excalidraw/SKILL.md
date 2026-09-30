---
name: markdown-to-excalidraw
description: >-
  Turn markdown bullets or simple A-to-B flow lines into one .excalidraw file.
  Use when the user wants a simple diagram from markdown bullets or flow lines.
---

1. Run the converter from the repository root:

   ```bash
   python .cursor/skills/markdown-to-excalidraw/scripts/markdown_to_excalidraw.py -o docs/diagram.excalidraw
   ```

   Pass markdown on stdin, or pass an existing markdown file path as the argument before `-o`.

2. **Write exactly one `.excalidraw` file** to the current project repo, e.g. `docs/diagram.excalidraw`.
3. **Do not** create companion `.md` files, summaries, or `-v2` / duplicate excalidraw files. If a diagram already exists, overwrite it in place.
4. Pass markdown via stdin or read from an existing file the user points at — don't author a new markdown doc.

Input: bullet lists (`- item`) or flow lines (`A --> B`). Output opens in excalidraw.com or VS Code.
