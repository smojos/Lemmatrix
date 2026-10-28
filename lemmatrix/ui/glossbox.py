# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Gloss languages as chips (Josh, 28 October): a search box offering only the languages Lemmatrix
supports (English and the EACW's shipped gloss languages, wordlists.supported_gloss_languages), and a
chip for each language the database has. The first (English, the language of the analysis) is fixed:
a chip with no ✕. A language the database already has but Lemmatrix doesn't offer stays, removable;
it can't be added again. Removing a language leaves the glosses typed in it in the file."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QCompleter, QLineEdit, QToolButton, QVBoxLayout, QWidget

from .. import wordlists
from . import theme
from .widgets import FlowLayout


def language_label(code: str) -> str:
    name = wordlists.supported_gloss_languages().get(code)
    return f"{name} · {code}" if name else code


class GlossLanguagesBox(QWidget):
    changed = Signal()

    def __init__(self, languages, parent=None):
        super().__init__(parent)
        langs = list(dict.fromkeys(l for l in languages if l)) or ["en"]
        self.langs: list[str] = langs
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.holder = QWidget()
        self.flow = FlowLayout(self.holder, spacing=6)
        lay.addWidget(self.holder)
        self.find = QLineEdit()
        self.find.setPlaceholderText("add a gloss language (French, Arabic, Amharic)")
        self.find.setToolTip("The languages glosses and translations are written in. English is the language "
                             "of the analysis; the others are second languages to help speakers understand "
                             "(e.g. in ɛλicit requests), hidden until a column, a cell line or a dialogue's + "
                             "shows them. Only the languages Lemmatrix supports can be added.")
        self.completer = QCompleter([], self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.find.setCompleter(self.completer)
        self.completer.activated.connect(self._chosen)
        self.find.returnPressed.connect(lambda: self._chosen(self.find.text()))
        lay.addWidget(self.find)
        self._show()

    def languages(self) -> list[str]:
        return list(self.langs)

    def offered(self) -> dict[str, str]:
        """{label: code} the supported languages not yet chosen."""
        return {language_label(c): c for c in wordlists.supported_gloss_languages() if c not in self.langs}

    def add(self, code: str) -> bool:
        if code in self.langs or code not in wordlists.supported_gloss_languages():
            return False
        self.langs.append(code)
        self._show()
        self.changed.emit()
        return True

    def remove(self, code: str) -> bool:
        if code not in self.langs or code == self.langs[0]:      # the first is fixed
            return False
        self.langs.remove(code)
        self._show()
        self.changed.emit()
        return True

    def _chosen(self, text: str):
        text = text.strip()
        if not text:
            return
        offered = self.offered()
        code = offered.get(text)
        if code is None:
            low = text.casefold()
            hits = [c for label, c in offered.items() if low in label.casefold()]
            code = hits[0] if len(hits) == 1 else None
        if code is not None and self.add(code):
            QTimer.singleShot(0, self.find.clear)                 # after the completer writes its text

    def _show(self):
        while self.flow.count():
            item = self.flow.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        supported = wordlists.supported_gloss_languages()
        for i, code in enumerate(self.langs):
            fixed = i == 0
            b = QToolButton()
            b.setText(language_label(code) + ("" if fixed else "  ✕"))
            b.setProperty("code", code)
            if fixed:
                b.setToolTip("The language of the analysis: always there")
            elif code in supported:
                b.setToolTip("Click to remove (the glosses already typed in it stay in the file)")
            else:
                b.setToolTip("Not a gloss language Lemmatrix supports: it can be removed but not added again "
                             "(the glosses typed in it stay in the file)")
            colour = theme.accent().name() if fixed else theme.colour("pitch").name()
            b.setStyleSheet("QToolButton { border: 1px solid %s; border-radius: 10px; padding: 2px 8px; %s}"
                            % (colour, "font-weight: bold; " if fixed else ""))
            if not fixed:
                b.clicked.connect(lambda *_, c=code: self.remove(c))
            self.flow.addWidget(b)
        self.completer.model().setStringList(list(self.offered()))
        self.find.setEnabled(bool(self.offered()))
        self._fit()
        QTimer.singleShot(0, self._fit)

    def _fit(self):
        w = max(120, self.width() or self.holder.width())
        self.holder.setMinimumHeight(self.flow.heightForWidth(w))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()
