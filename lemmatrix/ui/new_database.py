# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""File → New database (IDEAS.md idea 9; Josh, 23 October): one window, in sections, with Create
at the bottom: the wordlist, the language and variety, the pitch kind, the database's name and
gloss languages, you as researcher (remembered on this computer), Copy setup from… and the
soundfile names. Where it goes is asked when Create is pressed, as before. The database itself
is made by lemmatrix/newdb.py."""

from __future__ import annotations

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import (QComboBox, QCompleter, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .. import languages, newdb, pitchkind, storage
from . import theme
from .dialogs import NoForbidden, pitch_kind_row
from .wordlist_dialogs import WordlistChoice

CUSTOM = "custom"


class NewDatabaseDialog(QDialog):
    def __init__(self, parent, prefs):
        super().__init__(parent)
        self.prefs = prefs
        self.copy_from = None                     # the database whose setup is copied
        self.setWindowTitle("New database")
        self.resize(880, 800)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        lay = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        def section(title):
            box = QGroupBox(title)
            lay.addWidget(box)
            return box

        # 1. the wordlist (as it was: idea 40)
        box = section("Start with")
        v = QVBoxLayout(box)
        self.lists = WordlistChoice(box)
        v.addWidget(self.lists)

        # 2. the language
        box = section("Language")
        f = QFormLayout(box)
        self.lang_name = QLineEdit()
        self.lang_name.setPlaceholderText("e.g. Fur, Hausa, Nuer, Swahili, Zulu (type to search the ISO 639-3 languages)")
        self.lang_code = NoForbidden()
        self.lang_code.setPlaceholderText("e.g. HAU")
        self.var_name = QLineEdit()
        self.var_name.setPlaceholderText("optional")
        self.var_code = NoForbidden()
        self.var_code.setPlaceholderText("optional")
        labels = [languages.label(c) for c in languages._all()]
        self._languages = QStringListModel(sorted(labels), self)   # kept: the completer needs it alive
        comp = QCompleter(self._languages, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        comp.activated.connect(self._language_chosen)
        self.lang_name.setCompleter(comp)
        f.addRow("Language name", self.lang_name)
        f.addRow("Language code", self.lang_code)
        f.addRow("Variety name", self.var_name)
        f.addRow("Variety code", self.var_code)
        self.pitch_kind, row = pitch_kind_row(pitchkind.DEFAULT)
        f.addRow("Pitch kind", row)

        # 3. the database
        box = section("Database")
        f = QFormLayout(box)
        self.db_name = QLineEdit()
        self.db_name.setPlaceholderText("e.g. Complete Lexicon")
        self.db_name.setToolTip("The database's own name, shown at the top of the window. It isn't the file name.")
        self.glosses = QLineEdit("en")
        self.glosses.setToolTip("Gloss languages, separated by spaces; the first is the primary one (the "
                                "language of the analysis), the others second languages to help speakers "
                                "understand (e.g. en ar, or en am)")
        f.addRow("Database name", self.db_name)
        f.addRow("Gloss languages", self.glosses)
        from .. import wordlists as _wl                 # the EACW's shipped glosses and their status (idea 63)
        shipped = "; ".join(f"{name}, {status[:1].lower()}{status[1:]}"
                            for name, status in _wl.gloss_statuses().values())
        gl_note = QLabel(f"With the EACW, fr, ar or am come filled in: {shipped}.")
        gl_note.setWordWrap(True)
        gl_note.setStyleSheet(f"color: {theme.muted()};")
        f.addRow("", gl_note)

        # 4. you (remembered on this computer)
        box = section("You, as researcher (remembered on this computer)")
        f = QFormLayout(box)
        you = prefs.you
        self.you_name = QLineEdit(you["name"])
        self.you_name.setPlaceholderText("your name")
        self.you_code = NoForbidden(you["code"])
        self.you_code.setPlaceholderText("e.g. JS (RS1 if left empty)")
        self.you_email = QLineEdit(you["email"])
        self.you_email.setPlaceholderText("optional: where ɛλicit's notices go")
        f.addRow("Name", self.you_name)
        f.addRow("Code", self.you_code)
        f.addRow("Email", self.you_email)
        note = QLabel("You are the first researcher and the owner. Other people and places start as "
                      "placeholders (RS2, SP1, SP2, L1, L2) to rename in Edit → Lists.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.muted()};")
        f.addRow(note)

        # 5. copy setup from…
        box = section("Setup")
        h = QHBoxLayout(box)
        self.copy_label = QLabel("Lemmatrix's own fields, lists and tags")
        self.copy_label.setWordWrap(True)
        copy_btn = QPushButton("Copy setup from…")
        copy_btn.setToolTip("Start with another database's fields, lists and tags (lemma, token and text "
                            "fields, closed lists, tag structure, reference categories, tier mapping): "
                            "no data, people, settings or matrices")
        copy_btn.clicked.connect(lambda *_: self._choose_copy())
        self.clear_copy = QPushButton("Lemmatrix's own")
        self.clear_copy.setEnabled(False)
        self.clear_copy.clicked.connect(lambda *_: self._set_copy(None, ""))
        h.addWidget(self.copy_label, 1)
        h.addWidget(copy_btn)
        h.addWidget(self.clear_copy)

        # 6. soundfile names
        box = section("Soundfile names")
        f = QFormLayout(box)
        self.pattern_choice = QComboBox()
        for label, pattern in newdb.PATTERNS:
            self.pattern_choice.addItem(label, pattern)
            self.pattern_choice.setItemData(self.pattern_choice.count() - 1, pattern, Qt.ToolTipRole)
        self.pattern_choice.addItem("Custom…", CUSTOM)
        self.pattern = QLineEdit(newdb.PATTERNS[0][1])
        self.pattern.setToolTip("Placeholders: {language} {variety} {speaker} {reference} {gloss} {tags} "
                                "{date}, or any field name. Changeable later in Settings → Sound.")
        self.pattern.setVisible(False)
        self.example = QLabel()
        self.example.setStyleSheet(f"color: {theme.muted()};")
        f.addRow("Pattern", self.pattern_choice)
        f.addRow("", self.pattern)
        f.addRow("For example", self.example)
        self.pattern_choice.currentIndexChanged.connect(lambda *_: self._pattern_chosen())
        self.pattern.textChanged.connect(lambda *_: self._update_example())
        for w in (self.lang_code, self.var_code):
            w.textChanged.connect(lambda *_: self._update_example())
        self._update_example()

        lay.addStretch(1)
        bb = QDialogButtonBox()
        self.create_btn = bb.addButton("Create…", QDialogButtonBox.AcceptRole)
        self.create_btn.setToolTip("Asks where the database goes, then makes it")
        bb.addButton(QDialogButtonBox.Cancel)
        bb.accepted.connect(self._create)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

    # ---- the language search -----------------------------------------------------------
    def _language_chosen(self, text: str):
        """A language picked from the list: its name, and its code in capitals (as Lemmatrix's
        codes are written: BDI) when the code box is empty."""
        name, _, code = text.rpartition(" · ")
        if not code:
            return
        self.lang_name.setText(name)
        if not self.lang_code.text().strip():
            self.lang_code.setText(code.upper())

    # ---- copy setup ----------------------------------------------------------------------
    def _choose_copy(self):
        from pathlib import Path
        path, _ = QFileDialog.getOpenFileName(self, "Copy setup from", str(Path.home() / "Documents"),
                                              "Lemmatrix database (*.xml)")
        if not path:
            return
        try:
            src = storage.load(path)
        except (storage.FormatError, OSError) as exc:
            QMessageBox.warning(self, "Copy setup", f"Couldn't open {Path(path).name}:\n{exc}")
            return
        self._set_copy(src, Path(path).name)

    def _set_copy(self, src, name: str):
        self.copy_from = src
        self.clear_copy.setEnabled(src is not None)
        self.copy_label.setText(f"Fields, lists and tags from {name}" if src is not None
                                else "Lemmatrix's own fields, lists and tags")

    # ---- soundfile names -----------------------------------------------------------------
    def _pattern_chosen(self):
        data = self.pattern_choice.currentData()
        self.pattern.setVisible(data == CUSTOM)
        if data != CUSTOM:
            self.pattern.setText(data)
        self._update_example()

    def _update_example(self):
        try:
            self.example.setText(newdb.example_name(self.pattern.text().strip() or newdb.PATTERNS[0][1],
                                                    self.choices(copy=False)))
        except Exception:                         # a pattern half typed
            self.example.setText("")

    # ---- the result ----------------------------------------------------------------------
    def choices(self, copy: bool = True) -> newdb.Choices:
        return newdb.Choices(
            base=self.lists.choice(), items=self.lists.version()[0], region=self.lists.version()[1],
            language_name=self.lang_name.text(), language_code=self.lang_code.text(),
            variety_name=self.var_name.text(), variety_code=self.var_code.text(),
            kind=self.pitch_kind.currentData(), name=self.db_name.text(),
            gloss_languages=self.glosses.text().split(),
            you={"name": self.you_name.text().strip(), "code": self.you_code.text().strip(),
                 "email": self.you_email.text().strip()},
            copy_from=self.copy_from if copy else None, pattern=self.pattern.text().strip())

    def _create(self):
        if "{" not in self.pattern.text():
            QMessageBox.warning(self, "New database", "The soundfile name pattern needs at least one placeholder.")
            return
        if self.you_name.text().strip() or self.you_code.text().strip():
            self.prefs.you = self.choices(copy=False).you   # remembered for the next new database
        self.accept()
