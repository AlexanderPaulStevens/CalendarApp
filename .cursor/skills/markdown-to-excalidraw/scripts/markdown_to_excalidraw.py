#!/usr/bin/env python3
"""Bullet list or simple A --> B flow → .excalidraw"""

import json
import random
import re
import sys
import uuid

COLORS = ["#ffd8a8", "#b2f2bb", "#d0bfff", "#ffc9c9", "#fff3bf"]
FONT_SIZE = 22
MIN_W, MIN_H = 260, 100
GAP = 110
PADDING = 28
CHAR_W = 12


def _id() -> str:
    return uuid.uuid4().hex[:12]


def _el(**fields):
    base = {
        "angle": 0,
        "strokeColor": "#1e1e1e",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "seed": random.randint(1, 2**31 - 1),
        "version": 1,
        "versionNonce": random.randint(1, 2**31 - 1),
        "isDeleted": False,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
    }
    base.update(fields)
    return base


def _box_size(label: str) -> tuple[float, float]:
    width = max(MIN_W, len(label) * CHAR_W + PADDING * 2)
    height = max(MIN_H, FONT_SIZE * 3)
    return width, height


def labels(text: str) -> list[str]:
    bullets = re.findall(r"^\s*[-*]\s+(.+)$", text, re.M)
    if bullets:
        return bullets

    ordered: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if "-->" not in line:
            continue
        left, right = line.split("-->", 1)
        left = left.strip()
        right = right.split(":", 1)[0].strip()
        for node in (left, right):
            if node and node not in seen:
                seen.add(node)
                ordered.append(node)

    if ordered:
        return ordered

    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    ]


def build(items: list[str]) -> dict:
    elements = []
    x, y = 60, 100
    prev_right = x

    for i, label in enumerate(items):
        w, h = _box_size(label)
        if i:
            x = prev_right + GAP
        box_id, text_id = _id(), _id()

        elements.append(
            _el(
                id=box_id,
                type="rectangle",
                x=x,
                y=y,
                width=w,
                height=h,
                backgroundColor=COLORS[i % len(COLORS)],
                roundness={"type": 3},
                boundElements=[{"id": text_id, "type": "text"}],
            )
        )
        elements.append(
            _el(
                id=text_id,
                type="text",
                x=x + PADDING,
                y=y + (h - FONT_SIZE * 1.25) / 2,
                width=w - PADDING * 2,
                height=FONT_SIZE * 1.5,
                strokeWidth=1,
                backgroundColor="transparent",
                text=label,
                fontSize=FONT_SIZE,
                fontFamily=5,
                containerId=box_id,
                originalText=label,
                textAlign="center",
                verticalAlign="middle",
                autoResize=True,
                lineHeight=1.25,
            )
        )

        if i:
            elements.append(
                _el(
                    id=_id(),
                    type="arrow",
                    x=prev_right,
                    y=y + h / 2,
                    width=GAP,
                    height=0,
                    backgroundColor="transparent",
                    roundness={"type": 2},
                    endArrowhead="arrow",
                    startArrowhead=None,
                    points=[[0, 0], [GAP, 0]],
                )
            )

        prev_right = x + w

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {
            "gridSize": 20,
            "viewBackgroundColor": "#ffffff",
        },
        "files": {},
    }


def main() -> None:
    out = None
    args = sys.argv[1:]
    if "-o" in args:
        out = args[args.index("-o") + 1]

    inp = next((a for a in args if a not in ("-o", out)), None)
    text = open(inp, encoding="utf-8").read() if inp else sys.stdin.read()
    items = labels(text)
    if not items:
        print("No labels found", file=sys.stderr)
        sys.exit(1)

    data = json.dumps(build(items), indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(data)
        print(f"Saved {out}")
    else:
        print(data)


if __name__ == "__main__":
    main()
