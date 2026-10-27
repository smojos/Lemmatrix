# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Tools → Audits → Find precomposed characters… (IDEAS.md ideas 18 and 21, Josh, 27 October): every
Phonetic and Phonemic value with a precomposed character (é, ã, ǹ…), where it is and which
characters, and **Decompose all**, which also turns on Settings → General → *Decompose Phonetic and
Phonemic* so the database stays decomposed (an NFC database recomposes on saving, so there is no
decomposing part of it). One undo step for the data (`lemmatrix/decompose.py`)."""

from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from .. import decompose as dmod
from . import theme
from .widgets import ipa_font

SHOWN = 2000           # rows listed at most (the count says how many there are)


def _code_points(chars: str) -> str:
    return "  ".join(f"{c} U+{ord(c):04X}" for c in chars.split())


class PrecomposedDialog(QDialog):
    def __init__(self, parent, db, findings, ipa_size: int = 13):
        super().__init__(parent)
        self.db, self.findings = db, findings
        self.setWindowTitle("Find precomposed characters")
        self.resize(720, 540)
        lay = QVBoxLayout(self)
        n = len(findings)
        items = len({id(f.item) for f in findings})
        head = QLabel(f"<b>{n} Phonetic or Phonemic value{'' if n == 1 else 's'}</b> in {items} "
                      f"place{'' if items == 1 else 's'} hold precomposed characters "
                      "(é as one character rather than e + ◌́).")
        head.setWordWrap(True)
        lay.addWidget(head)
        note = QLabel(
            ("<b>Decompose all</b> stores them decomposed (nothing changes on the screen: é and e + ◌́ "
             "look the same) and turns on <i>Decompose Phonetic and Phonemic</i> in Settings → General, "
             "so the database stays decomposed and its file says so.")
            if not db.settings.decomposed else
            "The database is set to decompose; these came in another way (e.g. a file edited by hand). "
            "<b>Decompose all</b> stores them decomposed.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.muted()};")
        lay.addWidget(note)
        self.table = QTableWidget(min(n, SHOWN), 4)
        self.table.setHorizontalHeaderLabels(["Where", "Field", "Value", "Precomposed"])
        self.table.verticalHeader().hide()
        self.table.setFont(ipa_font(ipa_size))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        h = self.table.horizontalHeader()
        for i in range(3):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        for row, f in enumerate(findings[:SHOWN]):
            field = f.field + (f" ({f.lang})" if f.lang else "")
            cells = (f.where, field, f.before, f.chars)
            for col, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if col == 3:
                    it.setToolTip(_code_points(f.chars))
                self.table.setItem(row, col, it)
        lay.addWidget(self.table, 1)
        if n > SHOWN:
            more = QLabel(f"… and {n - SHOWN} more (all are decomposed).")
            more.setStyleSheet(f"color: {theme.muted()};")
            lay.addWidget(more)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.go = self.buttons.addButton("Decompose all", QDialogButtonBox.AcceptRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)


def describe_token(db):
    gf = db.settings.entry_field("gloss")

    def where(e, t):
        gloss = (e.get(gf.name, db.settings.primary_gloss) if gf else "") or e.file_gloss
        tags = ".".join(t.tags)
        return f"{e.ref} ‘{gloss}’" + (f" · {tags}" if tags else "")
    return where


def run(main):
    """Tools → Audits → Find precomposed characters…"""
    from PySide6.QtWidgets import QMessageBox
    db = main.doc.db
    findings = dmod.find(db, describe_token(db))
    if not findings:
        state = ("The database decomposes them (Settings → General)." if db.settings.decomposed else
                 "Settings → General → Decompose Phonetic and Phonemic is off: new precomposed "
                 "characters are kept as they are typed.")
        QMessageBox.information(main, "Find precomposed characters",
                                "No precomposed characters in Phonetic or Phonemic.\n\n" + state)
        return
    dlg = PrecomposedDialog(main, db, findings, main.prefs.ipa_size)
    if not dlg.exec():
        return
    before = main.doc.settings_snapshot() if not db.settings.decomposed else None
    if not db.settings.decomposed:
        db.settings.decomposed = True
    n = main.convert_transcriptions(label="Decompose precomposed characters")
    if before is not None:
        main.doc.settings_changed(before)
    main.statusBar().showMessage(
        f"Decomposed {len(findings)} value(s) in {n} lemma(s) and utterance(s); Phonetic and Phonemic "
        "now stay decomposed (Settings → General).", 8000)
