# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Picking a lemma: for Move token to another lemma (IDEAS.md idea 11; the moving is in move.py)
and for Create token from a text's line (idea 31)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout)

from .. import matrix as mx
from ..filters import fold_diacritics
from ..model import Database, Entry
from .widgets import ipa_font, meaning


def _fold(text: str) -> str:
    return fold_diacritics(text or "").lower()


class LemmaPicker(QDialog):
    """A search over the lemmas (reference, form or gloss; diacritics and capitals ignored).
    first: the lemmas offered at the top of the list (the rest follow in database order)."""

    def __init__(self, parent, db: Database, title: str, heading: str, ok_text: str, note: str,
                 entries: list, ipa_size: int = 13):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(title)
        self.resize(460, 480)
        lay = QVBoxLayout(self)
        head = QLabel(heading)
        head.setWordWrap(True)
        lay.addWidget(head)
        self.find = QLineEdit()
        self.find.setPlaceholderText("Type a reference, form or gloss")
        self.find.setClearButtonEnabled(True)
        self.find.setFont(ipa_font(ipa_size))
        lay.addWidget(self.find)
        self.list = QListWidget()
        self.list.setFont(ipa_font(ipa_size))
        lay.addWidget(self.list, 1)
        if note:
            lbl = QLabel(note)
            lbl.setWordWrap(True)
            lay.addWidget(lbl)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(ok_text)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self.entries = list(entries)
        self.find.textChanged.connect(self._fill)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        self.list.currentRowChanged.connect(self._enable)
        self.find.returnPressed.connect(lambda: self.list.count() and self.accept())
        self._fill()

    def _fill(self, text: str = ""):
        q = _fold(text.strip())
        db = self.db
        self.list.clear()
        for e in self.entries:
            if q and not any(q in _fold(x) for x in (e.ref, db.lemma(e), db.gloss(e))):
                continue
            wc = db.word_class(e)
            it = QListWidgetItem(f"{e.ref}   {db.lemma(e)}   {meaning(db.gloss(e))}" + (f"   {wc}" if wc else ""))
            it.setData(Qt.UserRole, e)
            self.list.addItem(it)
            if self.list.count() >= 500:          # enough to pick from; typing narrows it
                break
        if self.list.count():
            self.list.setCurrentRow(0)
        self._enable()

    def _enable(self, *_):
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(self.list.currentItem() is not None)

    def chosen(self) -> Entry | None:
        if getattr(self, "made", None) is not None:      # New lemma…
            return self.made
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None


class MoveTokenDialog(LemmaPicker):
    """A search over the lemmas (reference, form or gloss), those of the token's own word class
    first; the lemma the token is in now isn't offered."""

    def __init__(self, parent, db: Database, source: Entry, index: int, ipa_size: int = 13):
        t = source.tokens[index]
        what = " + ".join(mx.chips(db, t.tags)) or "citation"
        own = db.word_class(source)
        others = [e for e in db.entries if e is not source]
        entries = [e for e in others if own and db.word_class(e) == own] + \
                  [e for e in others if not own or db.word_class(e) != own]
        super().__init__(parent, db, "Move token to another lemma",
                         f"Move the {what} token of {source.ref} {db.lemma(source)} {meaning(db.gloss(source))} to:",
                         "Move", "It keeps its tags, fields and recording. Tags that aren't usual for the new "
                         "lemma's word class are marked, as anywhere.", entries, ipa_size)


def matching_first(db: Database, words: str) -> list:
    """Every lemma, those whose form or gloss matches the words first (either contains the
    other, diacritics and capitals ignored), then the rest in database order."""
    q = _fold(words.strip())
    if not q:
        return list(db.entries)

    def hit(e):
        return any(x and (q in x or x in q) for x in (_fold(db.lemma(e)), _fold(db.gloss(e))))
    first = [e for e in db.entries if hit(e)]
    return first + [e for e in db.entries if not hit(e)]


class CreateTokenDialog(LemmaPicker):
    """Create token from a text's line (IDEAS.md idea 31): the lemma to put the token under."""

    def __init__(self, parent, db: Database, words: str, field_title: str, ipa_size: int = 13, new_lemma=None):
        super().__init__(parent, db, "Create token",
                         f"Create a token with “{words}” in its {field_title}, under the lemma:",
                         "Create token", "The token dialogue opens next, with only those words filled in. "
                         "None fits? New lemma… makes one, and the words go in its citation token.",
                         matching_first(db, words), ipa_size)
        self.made = None
        self.new_lemma = new_lemma                         # () -> a new Entry, or None if cancelled
        if new_lemma is not None:
            btn = QPushButton("New lemma…")
            btn.setToolTip("No lemma fits: make a new one (the lemma dialogue), and put the words in "
                           "its citation token")
            btn.clicked.connect(self._make)
            self.buttons.addButton(btn, QDialogButtonBox.ActionRole)

    def _make(self):
        e = self.new_lemma()
        if e is not None:
            self.made = e
            self.accept()
