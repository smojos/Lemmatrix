# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Tools → Check spelling…: every word in the English glosses and translations that may be misspelled.

A window of its own, beside the main one. The words are listed with how often they occur and
where; the occurrences of the chosen word are listed under them (double-click one to go to its
lemma or token). For each word: Replace everywhere (one undo step), Ignore (kept in the workspace,
idea 36), or Add to the word list (kept in the workspace too).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import spelling
from . import theme


class SpellingWindow(QDialog):
    def __init__(self, main):
        super().__init__(main, Qt.Window)
        self.main = main
        self.doc = main.doc
        self.setWindowTitle("Check spelling")
        self.resize(900, 680)
        self.unknown: list[spelling.Unknown] = []
        self._applying = False

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.title = QLabel("Check spelling")
        f = QFont(self.title.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.45)
        self.title.setFont(f)
        top.addWidget(self.title)
        top.addStretch(1)
        self.count = QLabel()
        top.addWidget(self.count)
        lay.addLayout(top)
        note = QLabel("The English glosses and translations, checked against two English word lists and "
                      "this database's own. Words in brackets, codes in capitals (1SG, PL) and words "
                      "with digits aren't checked.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.muted()};")
        lay.addWidget(note)

        split = QSplitter(Qt.Vertical)
        self.words = QTreeWidget()
        self.words.setRootIsDecorated(False)
        self.words.setHeaderLabels(["Word", "Times", "In", "Suggestion"])
        self.words.setSelectionMode(QAbstractItemView.SingleSelection)
        self.words.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.words.header().setSectionResizeMode(3, QHeaderView.Stretch)
        self.words.currentItemChanged.connect(lambda *_: self._chosen())
        split.addWidget(self.words)

        below = QWidget()
        bl = QVBoxLayout(below)
        bl.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel("Replace with"))
        self.new = QComboBox()
        self.new.setEditable(True)
        self.new.setMinimumWidth(220)
        self.new.setToolTip("Pick a suggestion, or type the right spelling")
        row.addWidget(self.new)
        self.replace_btn = QPushButton("Replace everywhere")
        self.replace_btn.setToolTip("Replace the word in every gloss and translation it's in (one undo step)")
        self.ignore_btn = QPushButton("Ignore")
        self.ignore_btn.setToolTip("Leave it out of this list (remembered in the database's workspace)")
        self.add_btn = QPushButton("Add to word list")
        self.add_btn.setToolTip("Count it as spelled correctly from now on (kept in the database)")
        for b in (self.replace_btn, self.ignore_btn, self.add_btn):
            row.addWidget(b)
        row.addStretch(1)
        bl.addLayout(row)
        self.places = QTreeWidget()
        self.places.setRootIsDecorated(False)
        self.places.setHeaderLabels(["Reference", "Lemma", "Field", "Text"])
        self.places.header().setSectionResizeMode(3, QHeaderView.Stretch)
        self.places.setToolTip("Double-click to go to the lemma or token")
        self.places.itemDoubleClicked.connect(lambda item, _: self._go(item))
        bl.addWidget(self.places, 1)
        split.addWidget(below)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        lay.addLayout(bottom)

        self.replace_btn.clicked.connect(lambda *_: self.replace())
        self.ignore_btn.clicked.connect(lambda *_: self.ignore())
        self.add_btn.clicked.connect(lambda *_: self.add())
        for a in (self.doc.undo.createUndoAction(self, "Undo"), self.doc.undo.createRedoAction(self, "Redo")):
            self.addAction(a)
        self.actions()[0].setShortcut(QKeySequence.Undo)
        self.actions()[1].setShortcut(QKeySequence.Redo)
        self.doc.changed.connect(self._doc_changed)
        self.title.setStyleSheet(f"color: {theme.colour('pitch').name()};")
        self.rescan()

    # ---- the list ------------------------------------------------------
    def rescan(self, keep: str = ""):
        db = self.doc.db
        ignored = self.main.spelling_ignored
        self.unknown = [u for u in spelling.scan(db, self.main.spell_checker)
                        if u.word.lower() not in ignored]
        self.words.blockSignals(True)
        self.words.clear()
        pick = None
        for u in self.unknown:
            sugg = self.main.spell_checker.suggestions(u.word)
            item = QTreeWidgetItem([u.word, str(u.count), u.where(), sugg[0] if sugg else ""])
            item.setData(0, Qt.UserRole, u)
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            self.words.addTopLevelItem(item)
            if keep and u.word.lower() == keep:
                pick = item
        self.words.blockSignals(False)
        n = len(self.unknown)
        if not spelling.places(db):
            self.count.setText("No English gloss or translation to check")
        else:
            self.count.setText(f"{n} word{'s' if n != 1 else ''} may be misspelled" if n else
                               "No words that may be misspelled")
        target = pick or self.words.topLevelItem(0)
        if target is not None:
            self.words.setCurrentItem(target)
        self._chosen()

    def current(self) -> spelling.Unknown | None:
        item = self.words.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def _chosen(self):
        u = self.current()
        self.places.clear()
        self.new.clear()
        for b in (self.replace_btn, self.ignore_btn, self.add_btn):
            b.setEnabled(u is not None)
        if u is None:
            return
        self.new.addItems(self.main.spell_checker.suggestions(u.word, thorough=True))
        db = self.doc.db
        for o in u.occurrences:
            field = o.place.title if o.index is None else \
                f"{o.place.title}: {db.settings.tags.display(o.entry.tokens[o.index].tags)}"
            from ..model import is_utterance
            lemma = f"(utterance) {o.entry.label}" if is_utterance(o.entry) else db.lemma(o.entry)
            item = QTreeWidgetItem([o.entry.ref, lemma, field, o.text])
            item.setData(0, Qt.UserRole, o)
            self.places.addTopLevelItem(item)
        self.places.resizeColumnToContents(0)
        self.places.resizeColumnToContents(1)
        self.places.resizeColumnToContents(2)

    def _go(self, item):
        o = item.data(0, Qt.UserRole)
        if o is not None:
            self.main.go_to(o.entry, o.index)
            self.main.raise_()

    # ---- actions -------------------------------------------------------
    def replace(self):
        u = self.current()
        new = self.new.currentText().strip()
        if u is None or not new or new == u.word:
            return
        pairs = spelling.replacements(self.doc.db, u, new)
        if not pairs:
            return
        self._applying = True
        try:
            self.doc.apply_changes(f"Spelling: {u.word} → {new}", pairs)
        finally:
            self._applying = False
        self.rescan()

    def ignore(self):
        u = self.current()
        if u is not None:
            self.main.ignore_spelling(u.word)
            self.rescan()

    def add(self):
        u = self.current()
        if u is not None:
            self.main.add_spelling_word(u.word)       # rescans through settingsChanged → changed

    def _doc_changed(self):
        if not self._applying:
            u = self.current()
            self.rescan(u.word.lower() if u else "")

    def closeEvent(self, event):
        try:
            self.doc.changed.disconnect(self._doc_changed)
        except (RuntimeError, TypeError):
            pass
        if getattr(self.main, "spelling_window", None) is self:
            self.main.spelling_window = None
        super().closeEvent(event)
        if event.isAccepted():
            self.deleteLater()                    # forgotten by the main window: freed, not kept hidden
