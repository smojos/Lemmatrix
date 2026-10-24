# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""A token being saved with the configuration of a token the lemma already has (Josh, 24 October):
switch to editing that token, add an Example tag, or overwrite it. The boxes only; the token
dialogue does the merging (TokenDialog._merge_into)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QToolButton, QVBoxLayout)

from . import theme
from .icons import icon
from .widgets import paint_chips


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def chip_icon(label: str, font) -> QIcon:
    """A tag drawn as a chip, for a button (Add x1)."""
    from .widgets import chip_metrics, chips_width
    _, h = chip_metrics(font)
    w = chips_width([label], font)
    ratio = 2.0
    pm = QPixmap(int((w + 2) * ratio), int((h + 2) * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_chips(p, 1, 1, [label], font)
    p.end()
    return QIcon(pm)


def chip_size(label: str, font) -> QSize:
    from .widgets import chip_metrics, chips_width
    _, h = chip_metrics(font)
    return QSize(chips_width([label], font) + 2, h + 2)


class DuplicateBox(QDialog):
    """A token with this configuration already exists: what found in it, and four choices."""
    SWITCH, ADD, OVERWRITE, CANCEL = "switch", "add", "overwrite", "cancel"

    def __init__(self, parent, found: list[tuple[str, bool]], chip: str):
        """found: (field title, bold) for each core field with data in the existing token."""
        super().__init__(parent)
        self.setWindowTitle("Same configuration")
        self.choice = self.CANCEL
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        head = QLabel("A token with this configuration already exists")
        head.setStyleSheet(f"color: {theme.colour('pitch').name()}; font-weight: bold; font-size: 11pt;")
        lay.addWidget(head)
        if found:
            parts = [f"<b>{_esc(t)}</b>" if bold else _esc(t) for t, bold in found]
            data = QLabel("Data found in: " + ", ".join(parts))
        else:
            data = QLabel("It has no data yet.")
        data.setTextFormat(Qt.RichText)
        data.setWordWrap(True)
        lay.addWidget(data)
        lay.addWidget(QLabel("Would you like to…"))

        def button(text, choice, tip):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setMinimumHeight(30)
            b.clicked.connect(lambda: self._pick(choice))
            lay.addWidget(b)
            return b
        self.switch_btn = button("Switch to editing that token", self.SWITCH,
                                 "Leave this one and edit the token that is already there. What is "
                                 "typed here goes into its empty fields only (a soundfile too).")
        self.add_btn = button("Add", self.ADD, "Make this a new token with the example tag, so its "
                                               "soundfile gets a name of its own.")
        self.add_btn.setIcon(chip_icon(chip, self.add_btn.font()))
        self.add_btn.setIconSize(chip_size(chip, self.add_btn.font()))
        self.add_btn.setLayoutDirection(Qt.RightToLeft)       # Add, then the chip
        self.overwrite_btn = button("⚠️ Overwrite the token ⚠️", self.OVERWRITE,
                                    "Put what is typed here into the token that is already there, over "
                                    "what it has. Empty fields here never erase anything.")
        self.cancel_btn = button("Cancel", self.CANCEL, "Back to the token dialogue.")
        self.switch_btn.setDefault(True)

    def _pick(self, choice: str):
        self.choice = choice
        (self.reject if choice == self.CANCEL else self.accept)()


class SoundfileBox(QDialog):
    """Two soundfiles: which do you want to keep? Each can be played first."""

    def __init__(self, parent, mine: Path, theirs: Path, play):
        super().__init__(parent)
        self.setWindowTitle("Soundfile")
        self.keep = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Which soundfile do you want to keep?</b>"))
        grid = QGridLayout()
        for row, (what, path, key) in enumerate((("This token's", mine, "mine"),
                                                 ("That token's", theirs, "theirs"))):
            pb = QToolButton()
            pb.setIcon(icon("play", 22))
            pb.setIconSize(QSize(22, 22))
            pb.setToolTip(f"Play {path.name}")
            pb.clicked.connect(lambda _=False, p=path: play(p))
            grid.addWidget(pb, row, 0)
            name = QLabel(f"{what}: {_esc(path.name)}")
            name.setToolTip(str(path))
            grid.addWidget(name, row, 1)
            keep = QPushButton("Keep this one")
            keep.clicked.connect(lambda _=False, k=key: self._pick(k))
            grid.addWidget(keep, row, 2)
        lay.addLayout(grid)
        note = QLabel("The other one is put aside with the deleted recordings, so Undo brings it back.")
        note.setStyleSheet(f"color: {theme.muted()};")
        note.setWordWrap(True)
        lay.addWidget(note)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        lay.addLayout(row)

    def _pick(self, key: str):
        self.keep = key
        self.accept()


class OverwriteBox(QDialog):
    """Overwrite: say what will be written over, and the checkbox that must be selected first."""

    def __init__(self, parent, what: str):
        super().__init__(parent)
        self.setWindowTitle("Overwrite the token")
        lay = QVBoxLayout(self)
        head = QLabel("⚠️ Overwrite the token ⚠️")
        head.setStyleSheet("font-weight: bold;")
        lay.addWidget(head)
        self.check = QCheckBox(f"I understand that {what} will be overwritten")
        lay.addWidget(self.check)
        row = QHBoxLayout()
        row.addStretch(1)
        self.go = QPushButton("Overwrite")
        self.go.setEnabled(False)
        self.go.clicked.connect(self.accept)
        self.check.toggled.connect(self.go.setEnabled)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        cancel.setDefault(True)
        row.addWidget(self.go)
        row.addWidget(cancel)
        lay.addLayout(row)


def join(items: list[str]) -> str:
    """a, b and c."""
    items = [x for x in items if x]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]
