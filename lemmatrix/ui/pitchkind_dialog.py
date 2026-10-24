# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Converting a database's pitch kind (IDEAS.md idea 9; Josh, 23 October): data the new kind
doesn't show is kept hidden by default; ticked data can be deleted, after the question about a
full backup, for researchers who want a clean XML."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QVBoxLayout)

from .. import pitchkind

KEEP, DELETE, CANCEL = "keep", "delete", "cancel"


class ConvertDialog(QDialog):
    """What holds data the new kind won't show, with a tick each: Keep it hidden (the default),
    Delete the ticked data…, Cancel."""

    def __init__(self, parent, db, new: str, holding: list[pitchkind.Holding]):
        super().__init__(parent)
        self.setWindowTitle(f"Pitch kind: {pitchkind.LABELS[new]}")
        self.answer = CANCEL
        lay = QVBoxLayout(self)
        word = pitchkind.LABELS[new].lower()
        intro = QLabel(f"{'An' if word[0] in 'aeiou' else 'A'} {word} database doesn't show these. Kept, they stay "
                       "in the file, hidden, and come back if you convert back.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.ticks: dict[str, QCheckBox] = {}
        for h in holding:
            box = QCheckBox(h.label)
            box.setToolTip("Selected: deleted with Delete the selected data…; kept hidden otherwise")
            self.ticks[h.key] = box
            lay.addWidget(box)
        added = pitchkind.added(db, new)
        if added:
            lay.addWidget(QLabel("Added, empty: " + ", ".join(added) + "."))
        row = QHBoxLayout()
        keep = QPushButton("Keep it hidden")
        keep.setDefault(True)
        self.delete_btn = QPushButton("Delete the selected data…")
        self.delete_btn.setEnabled(False)
        cancel = QPushButton("Cancel")
        for b in (keep, self.delete_btn, cancel):
            row.addWidget(b)
        lay.addLayout(row)
        keep.clicked.connect(lambda *_: self._done(KEEP))
        self.delete_btn.clicked.connect(lambda *_: self._done(DELETE))
        cancel.clicked.connect(lambda *_: self._done(CANCEL))
        for box in self.ticks.values():
            box.toggled.connect(lambda *_: self.delete_btn.setEnabled(bool(self.ticked())))

    def ticked(self) -> set[str]:
        return {k for k, b in self.ticks.items() if b.isChecked()}

    def _done(self, answer):
        self.answer = answer
        (self.reject if answer == CANCEL else self.accept)()


BACKUP_FIRST, NO_BACKUP = "backup", "no-backup"


def ask_backup(parent) -> str:
    """Before deleting: Back up now, then delete / Delete without a backup / Cancel."""
    box = QMessageBox(QMessageBox.Warning, "Delete pitch data",
                      "Make a full backup first? You can restore it if you change your mind.", parent=parent)
    box.setInformativeText("Ctrl+Z also brings the data back until the database is closed.")
    backup = box.addButton("Back up now, then delete", QMessageBox.AcceptRole)
    none = box.addButton("Delete without a backup", QMessageBox.DestructiveRole)
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(backup)
    box.exec()
    clicked = box.clickedButton()
    return BACKUP_FIRST if clicked is backup else NO_BACKUP if clicked is none else CANCEL
