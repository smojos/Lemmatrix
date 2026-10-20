# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Move token to another lemma: pick the lemma (IDEAS.md idea 11). The moving is in move.py."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QVBoxLayout)

from .. import matrix as mx
from ..filters import fold_diacritics
from ..model import Database, Entry
from .widgets import ipa_font, meaning


def _fold(text: str) -> str:
    return fold_diacritics(text or "").lower()


class MoveTokenDialog(QDialog):
    """A search over the lemmas (reference, form or gloss), those of the token's own word class
    first; the lemma the token is in now isn't offered."""

    def __init__(self, parent, db: Database, source: Entry, index: int, ipa_size: int = 13):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Move token to another lemma")
        self.resize(460, 480)
        t = source.tokens[index]
        what = " + ".join(mx.chips(db, t.tags)) or "citation"
        lay = QVBoxLayout(self)
        head = QLabel(f"Move the {what} token of {source.ref} {db.lemma(source)} {meaning(db.gloss(source))} to:")
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
        note = QLabel("It keeps its tags, fields and recording. Tags that aren't usual for the new lemma's "
                      "word class are marked, as anywhere.")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Move")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        own = db.word_class(source)
        others = [e for e in db.entries if e is not source]
        self.entries = [e for e in others if own and db.word_class(e) == own] + \
                       [e for e in others if not own or db.word_class(e) != own]
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
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None
