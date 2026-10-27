# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""🐕 linguist's best friend as you type (IDEAS.md idea 21, Josh, 27 October): one app-wide filter
over the typed characters of text boxes whose field is Phonetic or Phonemic (the dialogues, the
grids' in-place editors, edit mode), corrected by the rules turned on (`lemmatrix/bestfriend.py`).
**Backspace or Ctrl+Z straight after** a correction puts back what was typed (as Word does); any
other key, and they work as usual. Pasting never passes through here.

The same filter **decomposes precomposed characters as they are typed** (é → e + ◌́) in a database
whose transcriptions are decomposed (Settings → General; ideas 18 and 21, format 14), whether or not
the dog is on: that is the database's promise, not a typing aid (`lemmatrix/decompose.py`).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QLineEdit

from .. import advanced, bestfriend as bf, decompose
from . import fastpaste, keyboards


class BestFriendFilter(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last = None        # (box, cursor after, text put in, what it replaced + what was typed)

    @staticmethod
    def _decomposing() -> bool:
        db = fastpaste.database()
        return db is not None and db.settings.decomposed

    def _role(self, ed) -> str | None:
        """phonetic or phonemic for a Phonetic or Phonemic box, else None (left alone)."""
        return fastpaste.role(fastpaste.database(), keyboards.field_key(ed))

    def _take_back(self, ed) -> bool:
        last, self._last = self._last, None
        if last is None:
            return False
        box, pos, put, original = last
        if box is not ed or ed.cursorPosition() != pos or ed.hasSelectedText():
            return False
        if ed.text()[pos - len(put):pos] != put:
            return False
        ed.setSelection(pos - len(put), len(put))
        ed.insert(original)
        return True

    def _correct(self, ed: QLineEdit, typed: str) -> bool:
        role = None if ed.isReadOnly() else self._role(ed)
        if role is None:
            return False
        sel = ed.hasSelectedText()
        start = ed.selectionStart() if sel else ed.cursorPosition()
        dog = advanced.best_friend()
        got = bf.correct(ed.text()[:start], typed, lambda rule: advanced.on(rule.key), role) if dog else None
        if self._decomposing():
            if got is None:
                if not decompose.precomposed(typed):
                    return False
                ed.insert(decompose.nfd(typed))          # é typed: e + ◌́ stored (not a correction:
                self._last = None                        # Backspace deletes the mark, as usual)
                return True
            got = (got[0], decompose.nfd(got[1]))
        if got is None:
            return False
        back, put = got
        if back and sel:                                  # typing over a selection: no looking back
            return False
        replaced = ed.text()[start - back:start]
        if back:
            ed.setSelection(start - back, back)
        ed.insert(put)                                    # replaces a selection, as typing does
        self._last = (ed, ed.cursorPosition(), put, replaced + typed)
        return True

    def eventFilter(self, obj, event):
        t = event.type()
        if t not in (QEvent.KeyPress, QEvent.InputMethod):
            return False
        if not advanced.best_friend() and not self._decomposing():
            return False
        if not isinstance(obj, QLineEdit):
            return False
        try:
            if t == QEvent.InputMethod:                   # a keyboard typing through an input method
                if event.preeditString() or event.replacementLength():
                    self._last = None
                    return False
                text = event.commitString()
                if len(text) != 1:
                    self._last = None
                    if (text and decompose.precomposed(text) and self._decomposing()
                            and not obj.isReadOnly() and self._role(obj)):
                        obj.insert(decompose.nfd(text))  # a keyboard committing several at once
                        return True
                    return False
                return self._correct(obj, text)
            key, mods = event.key(), event.modifiers() & ~Qt.KeypadModifier
            if key == Qt.Key_Backspace and mods == Qt.NoModifier or \
                    key == Qt.Key_Z and mods == Qt.ControlModifier:
                return self._take_back(obj)
            if key in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr):
                return False                              # a modifier alone isn't the next key
            text = event.text()
            ctrl_only = mods & Qt.ControlModifier and not mods & Qt.AltModifier   # AltGr is Ctrl+Alt
            if len(text) == 1 and text.isprintable() and not ctrl_only and not mods & Qt.MetaModifier:
                if self._correct(obj, text):
                    return True
            self._last = None
            return False
        except Exception:                                 # never in the way of typing
            self._last = None
            return False


def install(app) -> BestFriendFilter:
    f = BestFriendFilter(app)
    app.installEventFilter(f)
    return f
