# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Hiding the pitch system (IDEAS.md idea 9; DESIGN.md section 3.5).

Settings → Pitch → **Hide the pitch system** (and View → Hide pitch system) hides everything to do
with the pitch trace data: the Pitch field, the pitch drawing, pitch playback, Raise and Lower pitch,
Bulk edit's Pitch shortcut, the pitch-looking-text warning and the pitch scratchpads. It never hides
tone data (Tone Class and the like), and it **never changes the data**: Pitch stays in the file as it
is, and every configuration (columns, cells, views) keeps its pitch lines, which come back exactly
as they were when pitch is shown again (Josh, 23 October: *preserve and protect the data*).

It is a view setting of the open database, kept in its workspace (``pitch/shown``), so it never
marks the database unsaved and is not an undo step.

Underneath, the system is in three parts. The database's **pitch kind** (``pitchkind``: tonal,
intonational, unspecified) says which parts it has at all; the checkbox hides the parts it has. No Qt
here.
"""
from __future__ import annotations

KEY = "pitch/shown"            # the workspace's value (absent: shown)

TOKENS = "tokens"              # lemma tokens: All data, the matrices, the token dialogue
UTTERANCES = "utterances"      # utterances (and a text's lines): their grid, dialogue and cells
SCRATCHPADS = "scratchpads"    # the pitch scratchpads of the phonetics scratchpads (α and β)
PARTS = (TOKENS, UTTERANCES, SCRATCHPADS)

DRAWING = "drawing"            # the key of the pitch drawing in columns and cell views

_tick = True                   # Show the pitch system: the open database's, from its workspace
_parts = set(PARTS)            # the parts its pitch kind has (pitchkind.PARTS; tonal: all three)


def load(ws) -> None:
    """Take the open database's checkbox from its workspace (None: shown)."""
    global _tick
    _tick = True if ws is None else ws.get_bool(KEY, True)


def set_kind(kind: str) -> None:
    """Take the open database's pitch kind (tonal, intonational, unspecified; idea 9): which parts
    of the pitch system it has at all."""
    from .pitchkind import PARTS as KIND_PARTS, DEFAULT
    global _parts
    _parts = set(KIND_PARTS.get(kind, KIND_PARTS[DEFAULT]))


def store(ws, on: bool) -> None:
    """Show (True) or hide (False) the pitch system: written into the workspace and taken at once.
    Shown is the default, so it is written only when hidden."""
    global _tick
    if ws is not None:
        ws.set(KEY, None if on else False)
    _tick = on


def tick() -> bool:
    """Settings → Pitch → Show the pitch system, as selected."""
    return _tick


def has(part: str | None = None) -> bool:
    """Whether the database's pitch kind has this part of the pitch system (any part: None)."""
    return bool(_parts) if part is None else part in _parts


def shown(part: str | None = None) -> bool:
    """Whether a part of the pitch system is shown: the kind has it and the checkbox is on. With no
    part, whether any of it is shown."""
    if part is None:
        return _tick and bool(_parts)
    return _tick and part in _parts


def hidden(part: str | None = None) -> bool:
    return not shown(part)


def pitch_names(settings) -> set[str]:
    """The names of the token fields that hold pitch (role pitch)."""
    return {f.name for f in settings.token_fields if f.role == "pitch"}


def is_pitch_key(key: str, settings) -> bool:
    """Whether a column or cell-line key is the pitch's: the drawing, or the Pitch field
    (as a column key ``f:Pitch`` or a cell key ``Pitch``)."""
    if key == DRAWING:
        return True
    name = key[2:] if key.startswith("f:") else key
    return name.partition(":")[0] in pitch_names(settings)


def visible(keys, settings, part: str = TOKENS) -> list[str]:
    """The keys to show: the pitch's left out while the part is hidden."""
    keys = list(keys)
    if shown(part):
        return keys
    return [k for k in keys if not is_pitch_key(k, settings)]


def keep_hidden(saved, chosen, settings, part: str = TOKENS) -> list[str]:
    """What to store when a configuration is chosen with pitch hidden: the chosen keys, with the
    pitch keys of the saved configuration put back where they were (after the same key they
    followed), so showing pitch again brings them back as they were. With pitch shown, the chosen
    keys as they are."""
    chosen = list(chosen)
    if shown(part):
        return chosen
    saved = list(saved)
    out = [k for k in chosen if not is_pitch_key(k, settings)]
    for i, k in enumerate(saved):
        if not is_pitch_key(k, settings) or k in out:
            continue
        before = next((saved[j] for j in range(i - 1, -1, -1) if saved[j] in out), None)
        out.insert(0 if before is None else out.index(before) + 1, k)
    return out


def columns(cols, settings, part: str = TOKENS) -> list:
    """A grid's columns (objects with a ``key``), the pitch's left out while the part is hidden:
    so Configure columns doesn't offer them either."""
    if shown(part):
        return list(cols)
    return [c for c in cols if not is_pitch_key(c.key, settings)]
