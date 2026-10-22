# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""From (Josh, 22 October): beside a lemma's Origin, what it comes from, as chips: the lemmas it
is built from (complex lemmas) and the languages it was borrowed from (loans), in one box. The
search finds lemmas by reference, form or gloss and the world's languages by name or ISO 639-3
code (lemmatrix/languages.py); text that matches nothing is kept as a language name, for a
proto-language or a dialect the standard lacks."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCompleter, QLineEdit, QToolButton, QVBoxLayout, QWidget

from .. import languages
from ..model import Database, Entry, nfc
from . import theme
from .widgets import FlowLayout, ipa_font, meaning

LEMMA, LANGUAGE = "lemma", "language"


def from_text(db: Database, e: Entry) -> str:
    """From as plain text, for the lemma list's column: "D009 dɪɪr, Standard Arabic · arb"."""
    out = []
    for ident in e.from_lemmas:
        x = db.entry_by_id(ident)
        out.append(f"{x.ref} {db.lemma(x)}".strip() if x else "(lemma deleted)")
    out += [languages.label(c) for c in e.from_languages]
    return ", ".join(out)


class FromBox(QWidget):
    def __init__(self, db: Database, entry: Entry | None, prefs=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.entry = entry
        self.items: list[tuple[str, str]] = ([(LEMMA, i) for i in entry.from_lemmas] +
                                             [(LANGUAGE, c) for c in entry.from_languages]) if entry else []
        size = prefs.ipa_size if prefs is not None else 13
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.holder = QWidget()
        self.flow = FlowLayout(self.holder, spacing=6)
        lay.addWidget(self.holder)
        self.find = QLineEdit()
        self.find.setFont(ipa_font(size))
        self.find.setPlaceholderText("a lemma (reference, form, gloss) or a language (name or code)")
        self.find.setToolTip("What this lemma comes from: the lemmas it's built from, or the language it was "
                             "borrowed from (any of the ISO 639-3 languages). A name that isn't in the list, "
                             "e.g. a proto-language, is kept as typed when you press Enter. Click a chip to "
                             "remove it.")
        self.choices: dict[str, tuple[str, str]] = {}
        for e in db.entries:
            if entry is not None and e.id == entry.id:
                continue
            text = " ".join(x for x in (e.ref, db.lemma(e), meaning(db.gloss(e))) if x)
            self.choices[text] = (LEMMA, e.id)
        for code in languages.search("", limit=10000) + sorted(languages._all()):
            label = f"{languages.label(code)} (language)"
            self.choices.setdefault(label, (LANGUAGE, code))
        self.completer = QCompleter(list(self.choices), self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.completer.setMaxVisibleItems(12)
        self.find.setCompleter(self.completer)
        self.completer.activated.connect(self._chosen)
        self.find.returnPressed.connect(lambda: self._chosen(self.find.text(), typed=True))
        lay.addWidget(self.find)
        self._show()

    def lemmas(self) -> list[str]:
        return [v for k, v in self.items if k == LEMMA]

    def languages(self) -> list[str]:
        return [v for k, v in self.items if k == LANGUAGE]

    def add(self, kind: str, value: str):
        if value and (kind, value) not in self.items:
            self.items.append((kind, value))
            self._show()

    def _chosen(self, text: str, typed: bool = False):
        text = nfc(text.strip())
        if not text:
            return
        hit = self.choices.get(text)
        if hit is None:
            low = text.lower()
            hits = [v for t, v in self.choices.items() if low in t.lower()]
            if len(hits) == 1:
                hit = hits[0]
            elif languages.is_code(low):
                hit = (LANGUAGE, low)
            elif typed:
                hit = (LANGUAGE, text)            # Add other: a language the list doesn't have
        if hit is None:
            return
        self.add(*hit)
        self.find.clear()

    def _show(self):
        while self.flow.count():
            item = self.flow.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        db = self.db
        for kind, value in self.items:
            if kind == LEMMA:
                e = db.entry_by_id(value)
                text = f"{e.ref} {db.lemma(e)}".strip() if e else "(lemma deleted)"
                tip = f"{e.ref} {db.lemma(e)} {meaning(db.gloss(e))}" if e else ""
            else:
                text = languages.label(value)
                tip = "Language (ISO 639-3)" if languages.is_code(value) else "Language (as typed)"
            b = QToolButton()
            b.setText(text + "  ✕")
            b.setFont(ipa_font(12))
            b.setToolTip(tip + "\nClick to remove")
            b.setStyleSheet("QToolButton { border: 1px solid %s; border-radius: 10px; padding: 2px 8px; }"
                            % theme.colour("pitch").name())
            b.clicked.connect(lambda *_, k=kind, v=value: self._remove(k, v))
            self.flow.addWidget(b)
        self.holder.setVisible(bool(self.items))
        self._fit()
        QTimer.singleShot(0, self._fit)          # once the chips have their final sizes

    def _fit(self):
        """The chips wrap to the box's width (a form row doesn't ask the flow on its own)."""
        w = max(120, self.width() or self.holder.width())
        self.holder.setMinimumHeight(self.flow.heightForWidth(w) if self.items else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    def _remove(self, kind, value):
        self.items = [x for x in self.items if x != (kind, value)]
        self._show()
