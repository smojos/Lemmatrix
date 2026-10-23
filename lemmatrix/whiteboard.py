# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The whiteboard (IDEAS.md idea 45, designed with Josh and built 22 October 2026): plain Python, no
Qt; the window is ui/whiteboard.py.

Literally a cheap drawing tool, a bit of an Easter egg (Tools → Whiteboard, no button): four markers
(black, red, blue, green) and an eraser, Blackboard, Wipe, Save, Copy and Link to hypothesis….

- A **stroke** remembers which marker drew it, not a colour, so Blackboard redraws everything
  already there in the blackboard's colours (black → white, blue → cyan, red → pink,
  green → yellow). The eraser's strokes rub out where they pass.
- The board is a **fixed sheet**, landscape A5 in shape (as Josh's mockup) (SHEET_W × SHEET_H on screen); saving and
  copying draw it at SAVE_SCALE, about 190 dpi on A5.
- It is **kept until wiped**, like a real board: the strokes are in the database's workspace
  (`whiteboard`), so closing the window or Lemmatrix keeps the drawing.
- **Saved drawings** go into the main folder's `Whiteboard/` folder as
  `Whiteboard 2026-10-22 12-30.png` (or .jpg). Drawings are the researcher's own work, like the
  notebook (DESIGN.md section 1): in every Full backup, in no archive.
"""

from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path

FOLDER = "Whiteboard"                       # in the main folder (layout.py)
SHEET_W, SHEET_H = 792, 560                 # the sheet on screen: landscape A5 (√2 : 1), as Josh's mockup
SAVE_SCALE = 2                              # saved and copied at 1584 × 1120 (about 190 dpi on A5)

MARKERS = ("black", "red", "blue", "green")
ERASER = "eraser"
TOOLS = MARKERS + (ERASER,)

# what each marker draws with, on the whiteboard and on the blackboard
INK = {"black": "#1b1b1b", "red": "#e0201a", "blue": "#0a5ee8", "green": "#0b9e1c"}
CHALK = {"black": "#f4f4f4", "red": "#ff6fb5", "blue": "#2fd0ff", "green": "#ffe14a"}
BOARD = {False: "#ffffff", True: "#1d1f1e"}

DEFAULT_SIZE = {"black": 4, "red": 4, "blue": 4, "green": 4, ERASER: 40}
SIZE_RANGE = {ERASER: (8, 160)}
MARKER_RANGE = (1, 48)


def size_range(tool: str) -> tuple[int, int]:
    return SIZE_RANGE.get(tool, MARKER_RANGE)


def clamp_size(tool: str, size) -> int:
    lo, hi = size_range(tool)
    try:
        size = int(round(float(size)))
    except (TypeError, ValueError):
        size = DEFAULT_SIZE.get(tool, 4)
    return max(lo, min(hi, size))


def step_size(tool: str, size: int, steps: int) -> int:
    """The mouse wheel: about 12% a notch, at least 1 px, inside the tool's range."""
    s = size
    for _ in range(abs(steps)):
        d = max(1, round(s * 0.12))
        s = s + d if steps > 0 else s - d
    return clamp_size(tool, s)


def colour(tool: str, blackboard: bool) -> str:
    """The colour a marker draws in (the eraser has none: it shows the board)."""
    if tool == ERASER:
        return BOARD[blackboard]
    return (CHALK if blackboard else INK).get(tool, INK["black"])


class Stroke:
    """One stroke: the tool, its size, the points (sheet coordinates) and, from a pen, the pressure
    at each point (0–1; None for the mouse and touch, which draw at full size)."""

    __slots__ = ("tool", "size", "points", "pressure")

    def __init__(self, tool: str, size: int, points=None, pressure=None):
        self.tool = tool if tool in TOOLS else "black"
        self.size = clamp_size(self.tool, size)
        self.points: list[tuple[float, float]] = list(points or [])
        self.pressure: list[float] | None = list(pressure) if pressure is not None else None

    def add(self, x: float, y: float, pressure: float | None = None) -> bool:
        """Add a point, unless it is less than half a pixel from the last (returns whether added)."""
        x, y = round(float(x), 1), round(float(y), 1)
        if self.points:
            px, py = self.points[-1]
            if math.hypot(x - px, y - py) < 0.5:
                if pressure is not None and self.pressure:
                    self.pressure[-1] = max(self.pressure[-1], round(float(pressure), 2))
                return False
        if pressure is not None:
            if self.pressure is None:
                self.pressure = [1.0] * len(self.points)
            self.pressure.append(round(max(0.0, min(1.0, float(pressure))), 2))
        elif self.pressure is not None:
            self.pressure.append(1.0)
        self.points.append((x, y))
        return True

    def width(self, i: int) -> float:
        """The stroke's width at point i (a light touch of the pen draws thinner, down to a quarter)."""
        if self.pressure is None or i >= len(self.pressure):
            return float(self.size)
        return max(0.6, self.size * (0.25 + 0.75 * self.pressure[i]))

    # ---- kept in the workspace -----------------------------------------------------
    def to_json(self) -> dict:
        flat = [v for p in self.points for v in p]
        d = {"t": self.tool, "s": self.size, "p": flat}
        if self.pressure is not None:
            d["q"] = [round(v * 100) for v in self.pressure]
        return d

    @classmethod
    def from_json(cls, d) -> "Stroke | None":
        if not isinstance(d, dict):
            return None
        flat = d.get("p")
        if not isinstance(flat, list) or len(flat) < 2:
            return None
        try:
            pts = [(float(flat[i]), float(flat[i + 1])) for i in range(0, len(flat) - 1, 2)]
        except (TypeError, ValueError):
            return None
        q = d.get("q")
        pressure = None
        if isinstance(q, list) and len(q) == len(pts):
            try:
                pressure = [max(0.0, min(1.0, float(v) / 100)) for v in q]
            except (TypeError, ValueError):
                pressure = None
        return cls(str(d.get("t", "black")), d.get("s", 4), pts, pressure)


class Board:
    """What is on the board, Blackboard or not, each tool's size, and the drawing last saved."""

    def __init__(self):
        self.strokes: list[Stroke] = []
        self.blackboard = False
        self.sizes = dict(DEFAULT_SIZE)
        self.tool = "black"
        self.saved = ""                         # the last drawing saved, relative to the main folder
        self.changed = True                     # strokes changed since then (a link saves first)

    def to_json(self) -> dict:
        return {"strokes": [s.to_json() for s in self.strokes], "blackboard": self.blackboard,
                "sizes": dict(self.sizes), "tool": self.tool, "saved": self.saved,
                "changed": self.changed}

    @classmethod
    def from_json(cls, d) -> "Board":
        b = cls()
        if not isinstance(d, dict):
            return b
        for sd in d.get("strokes") or []:
            s = Stroke.from_json(sd)
            if s is not None:
                b.strokes.append(s)
        b.blackboard = bool(d.get("blackboard", False))
        sizes = d.get("sizes")
        if isinstance(sizes, dict):
            for t in TOOLS:
                if t in sizes:
                    b.sizes[t] = clamp_size(t, sizes[t])
        if d.get("tool") in TOOLS:
            b.tool = d["tool"]
        b.saved = str(d.get("saved") or "")
        b.changed = bool(d.get("changed", True)) or not b.saved
        return b


# ---- saving --------------------------------------------------------------------------

def folder(db_path) -> Path:
    from . import layout
    return layout.main_folder(db_path) / FOLDER


def file_name(when: _dt.datetime | None = None, ext: str = "png", taken=()) -> str:
    """`Whiteboard 2026-10-22 12-30.png`, with (2), (3)… if that is taken (a name in `taken`)."""
    when = when or _dt.datetime.now()
    stem = f"Whiteboard {when:%Y-%m-%d %H-%M}"
    taken = {t.lower() for t in taken}
    name, n = f"{stem}.{ext}", 2
    while name.lower() in taken:
        name, n = f"{stem} ({n}).{ext}", n + 1
    return name


def new_path(db_path, ext: str = "png", when: _dt.datetime | None = None) -> Path:
    """Where the next drawing goes (the folder made if need be)."""
    f = folder(db_path)
    f.mkdir(parents=True, exist_ok=True)
    taken = [p.name for p in f.iterdir()] if f.is_dir() else []
    return f / file_name(when, ext, taken)


def relative(db_path, path) -> str:
    """A saved drawing's place as a link keeps it: relative to the main folder, with / (Whiteboard/…)."""
    from . import layout
    try:
        return Path(path).resolve().relative_to(layout.main_folder(db_path).resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def resolve(db_path, rel: str) -> Path | None:
    """A drawing link's file, or None if it is not there (moved or deleted)."""
    from . import layout
    if not rel or not db_path:
        return None
    p = Path(rel)
    if not p.is_absolute():
        p = layout.main_folder(db_path) / p
    return p if p.is_file() else None
