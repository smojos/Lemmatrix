# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""📋 fast paste (IDEAS.md idea 79, Josh, 27 October; Settings → Advanced, off on a new computer):
typing in Phonetic or Phonemic, Shift+Down or Shift+Up copies the field into the other
transcription, replacing what's there, and moves the cursor there.

**The arrow points to the other field on the screen** (Josh: someone who puts Phonemic above
Phonetic shouldn't get it backwards): where the two are stacked (the token and utterance dialogues,
a matrix cell or the utterance cell in edit mode, a text's lines in edit mode) Shift+Down copies to
the field below and Shift+Up to the field above, only when that field is the other transcription;
in a grid's in-place editor (All data, Utterances), where they sit side by side, either arrow
copies into the other column of the same row. Anything else passes through untouched (Shift+Up
and Shift+Down select as usual).

Views with in-place editors answer `fast_paste(editor, up, other_role, db)` themselves (FilterTable,
MatrixView, LinesView); a dialogue's text boxes are found here by their field key and place.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QLineEdit

from .. import advanced
from . import keyboards

PHONETIC, PHONEMIC = "phonetic", "phonemic"
OTHER = {PHONETIC: PHONEMIC, PHONEMIC: PHONETIC}

_context = None                     # () → the open database


def set_context(fn):
    global _context
    _context = fn


def role(db, key) -> str | None:
    """phonetic or phonemic for a field key ("Phonetic", "f:Phonemic"), else None."""
    if db is None or not key:
        return None
    k = key[2:] if key.startswith("f:") else key
    name = k.partition(":")[0]
    s = db.settings
    f = s.token_field(name) or s.entry_field(name) or s.text_field(name)
    return f.role if f is not None and f.role in OTHER else None


def _dialog_paste(ed: QLineEdit, db, other_role: str, up: bool) -> bool:
    """A dialogue's text boxes: the other transcription's box above (Shift+Up) or below (Shift+Down)."""
    win = ed.window()
    y = ed.mapToGlobal(ed.rect().center()).y()
    best = None
    for w in win.findChildren(QLineEdit):
        if w is ed or not w.isVisible() or not w.isEnabled() or w.isReadOnly():
            continue
        if role(db, keyboards.field_key(w)) != other_role:
            continue
        wy = w.mapToGlobal(w.rect().center()).y()
        if (wy < y) if up else (wy > y):
            d = abs(wy - y)
            if best is None or d < best[0]:
                best = (d, w)
    if best is None:
        return False
    target = best[1]
    text = ed.text()
    target.setFocus()
    target.selectAll()
    target.insert(text)                  # one step of the box's own undo (Ctrl+Z there brings it back)
    target.end(False)
    return True


def paste(ed, up: bool) -> bool:
    """Fast-paste from the text box `ed`; True when it did (the key is then taken)."""
    db = _context() if _context is not None else None
    key = keyboards.field_key(ed)
    mine = role(db, key)
    if mine is None:
        return False
    other = OTHER[mine]
    w = ed.parentWidget()
    while w is not None:                 # a view that edits in place answers for itself
        fn = getattr(w, "fast_paste", None)
        if callable(fn):
            return bool(fn(ed, up, other, db))
        w = w.parentWidget()
    return _dialog_paste(ed, db, other, up)


class FastPasteFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress or not advanced.fast_paste():
            return False
        if event.key() not in (Qt.Key_Up, Qt.Key_Down):
            return False
        if (event.modifiers() & ~Qt.KeypadModifier) != Qt.ShiftModifier:
            return False
        if not isinstance(obj, QLineEdit) or obj is not QApplication.focusWidget():
            return False
        try:
            return paste(obj, event.key() == Qt.Key_Up)
        except Exception:                # never in the way of typing
            return False


def install(app) -> FastPasteFilter:
    f = FastPasteFilter(app)
    app.installEventFilter(f)
    return f
