# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Tools → Copy citation forms to empty lemmas… (IDEAS.md idea 67): the lemmas with an empty
Lemma field and the form each would get from its citation token, each with a checkbox; Copy is one
undo step (lemmatrix/citation_copy.py)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from .. import citation_copy as cc
from . import theme
from .widgets import ipa_font


class CopyCitationDialog(QDialog):
    def __init__(self, parent, db, ipa_size: int = 13):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Copy citation forms to empty lemmas")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Copy from the citation token's"))
        self.order = QComboBox()
        for key, label in cc.LABELS.items():
            self.order.addItem(label, key)
        self.order.currentIndexChanged.connect(lambda *_: self.fill())
        top.addWidget(self.order)
        top.addStretch(1)
        lay.addLayout(top)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color: {theme.muted()};")
        lay.addWidget(self.note)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Reference", "Gloss", "Lemma it gets"])
        self.table.verticalHeader().hide()
        self.table.setFont(ipa_font(ipa_size))
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda *_: self._count())
        lay.addWidget(self.table, 1)
        sel = QHBoxLayout()
        for text, on in (("Select all", True), ("Deselect all", False)):
            b = QPushButton(text)
            b.clicked.connect(lambda *_, on=on: self._select_all(on))
            sel.addWidget(b)
        sel.addStretch(1)
        lay.addLayout(sel)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.go = self.buttons.addButton("Copy", QDialogButtonBox.AcceptRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self.fill()

    def fill(self):
        self.plan = cc.plan(self.db, self.order.currentData())
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.plan.copies))
        for r, (e, form) in enumerate(self.plan.copies):
            ref = QTableWidgetItem(e.ref)
            ref.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            ref.setCheckState(Qt.Checked)
            self.table.setItem(r, 0, ref)
            for c, text in ((1, self.db.gloss(e)), (2, form)):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(r, c, it)
        self.table.blockSignals(False)
        no_form = len(self.plan.no_form)
        self.note.setText(
            f"{len(self.plan.copies) + no_form} lemma{'s' if len(self.plan.copies) + no_form != 1 else ''} "
            f"with an empty Lemma; {no_form} skipped (the citation token has no such form)"
            + (": " + ", ".join(e.ref for e in self.plan.no_form[:8]) + (" …" if no_form > 8 else "") if no_form else "")
            + f". {self.plan.filled} with a Lemma already are left alone. Forms are copied as written.")
        self._count()

    def _select_all(self, on: bool):
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def chosen(self):
        return [pair for r, pair in enumerate(self.plan.copies)
                if self.table.item(r, 0).checkState() == Qt.Checked]

    def _count(self):
        n = len(self.chosen())
        self.go.setText(f"Copy {n} form{'s' if n != 1 else ''}")
        self.go.setEnabled(n > 0)
