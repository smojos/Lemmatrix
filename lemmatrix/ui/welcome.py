# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The welcome window, shown when no database is open at start-up (so also on the very first
start). Josh's question comes first, with Yes (a copy of the sample) as the big default button
(IDEAS.md idea 52, 23 October); opening a database, making a new one and the databases opened
recently stay within reach underneath."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout)

from . import theme
from .icons import app_icon

QUESTION = "Would you like to load the sample database to see its capabilities?"
SLOGAN = "Human readable, machine processable, ethically collected and shared linguistic data."

SAMPLE, OPEN, NEW, RECENT, CLOSE = "sample", "open", "new", "recent", "close"


def _split_title(title: str, path: str) -> tuple[str, str]:
    """A recent database's title (Language - Variety - Name) as its name and a second line."""
    parts = [p.strip() for p in (title or "").split(" - ") if p.strip()]
    if not parts:
        return Path(path).stem, ""
    return parts[-1], " · ".join(parts[:-1])


class RecentButton(QPushButton):
    """One database opened recently: its name in bold, its language and variety under it, the
    path in the hover; flat, with the accent's wash on hover (Qt's command links draw a black
    arrow that disappears on the dark theme)."""

    def __init__(self, name: str, description: str, path: str, parent=None):
        super().__init__(parent)
        self.name, self.description_text = name, description
        self.setToolTip(path)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(0)
        top = QLabel(name)
        top.setStyleSheet("font-weight: 600; background: transparent;")
        lay.addWidget(top)
        if description:
            sub = QLabel(description)
            sub.setStyleSheet(f"color: {theme.muted()}; background: transparent;")
            lay.addWidget(sub)
        for w in self.findChildren(QLabel):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setMinimumHeight(lay.sizeHint().height())
        self.setStyleSheet(
            "QPushButton { text-align: left; border: none; border-radius: 6px; background: transparent; }"
            f"QPushButton:hover {{ background: {theme.wash(0.82).name()}; }}"
            f"QPushButton:focus {{ background: {theme.wash(0.88).name()}; }}")

    def description(self) -> str:
        return self.description_text


class WelcomeDialog(QDialog):
    def __init__(self, parent=None, recent: list[dict] | None = None, sample_exists: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Lemmatrix")
        self.setWindowIcon(app_icon())
        self.choice, self.path = CLOSE, ""
        accent = theme.colour("pitch").name()          # the accent, lightened on the dark theme
        on_accent = theme.text_on(theme.accent()).name()
        muted = theme.muted()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(16)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(64, 64))
        logo.setFixedSize(64, 64)
        head.addWidget(logo)
        words = QVBoxLayout()
        words.setSpacing(2)
        title = QLabel("Welcome to Lemmatrix")
        title.setStyleSheet(f"font-size: 20pt; font-weight: 600; color: {accent};")
        slogan = QLabel(SLOGAN)
        slogan.setWordWrap(True)
        slogan.setStyleSheet(f"font-style: italic; color: {muted};")
        words.addWidget(title)
        words.addWidget(slogan)
        head.addLayout(words, 1)
        lay.addLayout(head)

        self.question = QLabel(QUESTION)
        self.question.setWordWrap(True)
        self.question.setStyleSheet("font-size: 12pt;")
        lay.addSpacing(4)
        lay.addWidget(self.question)

        self.sample = QPushButton("Yes, load the sample")
        self.sample.setDefault(True)
        self.sample.setMinimumHeight(40)
        self.sample.setCursor(Qt.PointingHandCursor)
        self.sample.setStyleSheet(
            f"QPushButton {{ background: {theme.accent().name()}; color: {on_accent}; border: none;"
            " border-radius: 6px; font-size: 11pt; font-weight: 600; padding: 6px 18px; }"
            f"QPushButton:hover {{ background: {theme.mix(theme.accent(), QColor('black'), 0.12).name()}; }}"
            f"QPushButton:disabled {{ background: {muted}; }}")
        self.sample.setEnabled(sample_exists)
        if not sample_exists:
            self.sample.setToolTip("The sample database isn't in this copy of Lemmatrix.")
        self.sample.clicked.connect(lambda: self._done(SAMPLE))
        lay.addWidget(self.sample)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.opened = QPushButton("Open a database…")
        self.new = QPushButton("New database…")
        for b in (self.opened, self.new):
            b.setMinimumHeight(32)
            row.addWidget(b, 1)
        self.opened.clicked.connect(lambda: self._done(OPEN))
        self.new.clicked.connect(lambda: self._done(NEW))
        lay.addLayout(row)

        self.recent: dict[RecentButton, str] = {}
        recent = recent or []
        if recent:
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet(f"color: {muted};")
            lay.addSpacing(4)
            lay.addWidget(line)
            label = QLabel("Opened recently")
            label.setStyleSheet(f"font-weight: 600; color: {accent};")
            lay.addWidget(label)
            rows = QVBoxLayout()
            rows.setSpacing(2)
            rows.setContentsMargins(0, 0, 0, 0)
            for r in recent:
                name, sub = _split_title(r.get("title", ""), r["path"])
                b = RecentButton(name, sub, r["path"])
                b.clicked.connect(lambda _=False, p=r["path"]: self._done(RECENT, p))
                self.recent[b] = r["path"]
                rows.addWidget(b)
            lay.addLayout(rows)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        bottom.addWidget(self.close_button)
        lay.addSpacing(4)
        lay.addLayout(bottom)

        self.setMinimumWidth(580)
        self.sample.setFocus() if sample_exists else self.opened.setFocus()

    def _done(self, choice: str, path: str = ""):
        self.choice, self.path = choice, path
        self.accept()
