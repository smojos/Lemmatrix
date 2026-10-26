# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Asking what to do when the tag structure would give two tokens of a lemma one soundfile name
(lemmatrix/tagclash.py; Josh, 26 October: Add Example tags, Choose for each, or Cancel)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from .. import tagclash
from . import widgets as _w

SHOWN = 12                     # clashes named in the question; the rest counted


def _tags(db, t) -> str:
    return " · ".join(t.tags) if t.tags else "citation (no tags)"


def describe(db, c: tagclash.Clash) -> str:
    return f"{c.entry.ref} {db.gloss(c.entry)}: {_tags(db, c.other)} and {_tags(db, c.keep)}"


def ask(parent, db, clashes: list[tagclash.Clash]) -> dict[int, str] | None:
    """What to do with each clash: {index: EXAMPLE or MERGE}, or None for Cancel."""
    lemmas = len({id(c.entry) for c in clashes})
    lines = "\n".join(describe(db, c) for c in clashes[:SHOWN])
    more = f"\n… and {len(clashes) - SHOWN} more" if len(clashes) > SHOWN else ""
    text = (f"With these changes, {len(clashes)} token{'s' if len(clashes) != 1 else ''} in {lemmas} "
            f"lemma{'s' if lemmas != 1 else ''} would get the same soundfile name as another token of "
            f"{'its' if lemmas == 1 else 'their'} lemma (a group's default adds nothing to file names):\n\n"
            f"{lines}{more}\n\nAdd Example tags gives each the next Example tag (x1, x2…). Choose for each "
            "lets you merge a pair into one token instead, where nothing would be lost.")
    r = _w.choose(parent, "Tag structure", text, ["Add Example tags", "Choose for each…"])
    if r is None:
        return None
    if r == 0:
        return {i: tagclash.EXAMPLE for i in range(len(clashes))}
    dlg = ChooseEach(parent, db, clashes)
    return dlg.choices() if dlg.exec() else None


class ChooseEach(QDialog):
    """One row per clash: Add an Example tag, or Merge into the other token (where it can)."""

    def __init__(self, parent, db, clashes):
        super().__init__(parent)
        self.setWindowTitle("Same soundfile name: choose for each")
        self.resize(860, 480)
        lay = QVBoxLayout(self)
        note = QLabel("Merge keeps the token on the right (fewer tags, the citation token often) and fills "
                      "its empty fields from the one on the left, which then goes. Offered where no field has "
                      "two different values; with two recordings you choose which to keep (the other "
                      "waits in Soundfiles › _Deleted recordings and goes to the Recycle Bin when the "
                      "database is closed). Links to the token that goes (notebook, hypotheses) will say "
                      "it no longer exists.")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.table = QTableWidget(len(clashes), 4)
        self.table.setHorizontalHeaderLabels(["Lemma", "Token", "Same name as", "Do"])
        self.table.verticalHeader().hide()
        self.boxes: list[QComboBox] = []
        for i, c in enumerate(clashes):
            for col, text in enumerate((f"{c.entry.ref} {db.gloss(c.entry)}", _tags(db, c.other), _tags(db, c.keep))):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(i, col, it)
            box = QComboBox()
            box.addItem("Add an Example tag", tagclash.EXAMPLE)
            if c.two_recordings:                  # both recorded: which recording the merge keeps
                box.addItem(f"Merge, keeping {c.keep.file}", tagclash.MERGE)
                box.addItem(f"Merge, keeping {c.other.file}", tagclash.MERGE_THEIRS)
            else:
                box.addItem("Merge into it", tagclash.MERGE)
            problem = c.merge_problem
            if problem:
                for k in range(1, box.count()):
                    box.model().item(k).setEnabled(False)
                    box.setItemData(k, f"Can't merge: {problem}", Qt.ToolTipRole)
                box.setToolTip(f"Merge isn't offered: {problem}")
            self.table.setCellWidget(i, 3, box)
            self.boxes.append(box)
        h = self.table.horizontalHeader()
        for col in range(3):
            h.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def choices(self) -> dict[int, str]:
        return {i: b.currentData() for i, b in enumerate(self.boxes)}
