# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""File → Export → Anonymous archive… and Ethical archive… (IDEAS.md idea 44): one dialogue,
the archive chosen at the top with its own defaults, then the copy (see anonymise.py)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, QDir
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QRadioButton, QVBoxLayout, QWidget)

from .. import anonymise
from ..anonymise import ANONYMOUS, ETHICAL
from . import theme
from .dialogs import PathEdit

INTRO = {
    ANONYMOUS: "A copy in which nobody is named, for letting others see your setup. Every person's code is "
               "renumbered (SP1, SP2… and RS1, RS2…) wherever it appears, names, descriptions, emails and "
               "consent links all go, the language's and variety's names become their codes, and no "
               "recordings go in. The database itself isn't changed.",
    ETHICAL: "A copy of the data to share or deposit, as the consent forms allow. Participants and "
             "researchers with Identifiable? selected (Edit → Lists) keep their names; everyone else is their "
             "code only. Only the recordings of speakers who agreed to audio sharing go in. The database "
             "itself isn't changed.",
}


class ArchiveExportDialog(QDialog):
    def __init__(self, main, kind: str = ETHICAL):
        super().__init__(main)
        self.main = main
        db = main.doc.db
        self.resize(660, 520)
        lay = QVBoxLayout(self)

        switch = QWidget()
        sl = QHBoxLayout(switch)
        sl.setContentsMargins(0, 0, 0, 0)
        self.kinds = QButtonGroup(self)
        self.kind_buttons = {}
        for k in (ANONYMOUS, ETHICAL):
            b = QRadioButton(anonymise.TITLES[k])
            b.setStyleSheet(f"font-weight: bold; color: {theme.colour('pitch').name()};")   # the theme colour
            self.kinds.addButton(b)
            self.kind_buttons[k] = b
            sl.addWidget(b)
        sl.addStretch(1)
        lay.addWidget(switch)

        self.intro = QLabel()
        self.intro.setWordWrap(True)
        lay.addWidget(self.intro)
        self.ai_note = QLabel(anonymise.AI_NOTE)
        self.ai_note.setWordWrap(True)
        self.ai_note.setStyleSheet("font-style: italic;")
        lay.addWidget(self.ai_note)

        form = QFormLayout()
        self.hide_language = QCheckBox("Hide the language code too (it becomes LXX)")
        self.hide_variety = QCheckBox("Hide the variety code too (it becomes VXX)")
        for w in (self.hide_language, self.hide_variety):
            w.toggled.connect(lambda *_: self._update_folder())
            w.setToolTip("A code can be looked up, so it gives the language or variety away. Hide it when "
                         "naming the language or variety could identify its speakers; the archive is then much "
                         "less useful for future work on the language.")
        codes = QWidget()
        cl = QVBoxLayout(codes)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.hide_language)
        cl.addWidget(self.hide_variety)
        self.codes_row = codes
        self.notebook = QCheckBox("Include the notebook (notes, questions, To Dos and Cogitate's hypotheses)")
        self.notebook.setToolTip(anonymise.PRIVATE_NOTE)
        self.names = QCheckBox()
        self.thanks = QCheckBox("Include the personal thank-yous (Edit → Metadata → Acknowledgements)")
        self.thanks.setToolTip("Organisations' support always goes in. The thank-yous to people are left out "
                               "unless you include them here.")
        self.thanks_note = QLabel("⚠ If they name or identify people, everyone named must have given their "
                                  "informed consent to be named in the archive.")
        self.thanks_note.setWordWrap(True)
        self.thanks_note.setStyleSheet(f"color: {theme.muted()};")
        self.thanks.toggled.connect(lambda on: self.thanks_note.setVisible(on and self.kind != ANONYMOUS))
        self.recordings = QCheckBox()
        self.places = QComboBox()
        self.places.addItem("Keep every place", 0)
        self.places.addItem("Keep only the top two levels (e.g. country and county)", 2)
        self.places.addItem("Keep only the top level (country)", 1)
        self.consent = QComboBox()
        self.consent.addItem("Leave them out", False)
        self.consent.addItem("", True)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("password")
        self.password2 = QLineEdit()
        self.password2.setEchoMode(QLineEdit.Password)
        self.password2.setPlaceholderText("the same again")
        if not anonymise.zip_available():
            self.consent.model().item(1).setEnabled(False)
            self.consent.setToolTip("Needs the pyzipper package (installed with the next start of Lemmatrix)")
        self.stem = Path(db.path).stem if db.path else "Database"
        from .. import layout                  # exports start in the database's Exports folder
        self.base = layout.exports_folder(db.path) if db.path else Path.home() / "Documents"
        self.folder = PathEdit("", True, "Export to folder")
        self.codes_label = QLabel("Language")
        form.addRow(self.codes_label, codes)
        form.addRow("Notebook", self.notebook)
        form.addRow("Free text", self.names)
        self.thanks_label = QLabel("Thanks")
        form.addRow(self.thanks_label, self.thanks)
        form.addRow("", self.thanks_note)
        form.addRow("Recordings", self.recordings)
        form.addRow("Places", self.places)
        form.addRow("Consent forms", self.consent)
        form.addRow("", self.password)
        form.addRow("", self.password2)
        form.addRow("Folder", self.folder)
        lay.addLayout(form)
        self.private = QLabel(anonymise.PRIVATE_NOTE)
        self.private.setWordWrap(True)
        self.private.setStyleSheet(f"color: {theme.muted()};")
        lay.addWidget(self.private)
        note = QLabel("Free text can still hold things that identify people (a name not on the lists, a village). "
                      "The report at the end lists every replacement.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.muted()};")
        lay.addWidget(note)
        lay.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.export_btn = buttons.addButton("Export", QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.consent.currentIndexChanged.connect(lambda *_: self._enable())
        self.kinds.buttonToggled.connect(lambda b, on: on and self.set_kind(self._kind_of(b)))
        self.kind = ""
        self._shown_default = ""
        self.notebook.toggled.connect(lambda *_: self._update_folder())
        self.kind_buttons[kind].setChecked(True)
        self.set_kind(kind)

    def _kind_of(self, button) -> str:
        return next(k for k, b in self.kind_buttons.items() if b is button)

    def _default_folder(self, kind: str) -> str:
        """A new folder in Exports, named from the archive's stem (with any hidden codes and
        names already replaced), the archive and the date; (2), (3)… if one is there already."""
        word = "anonymous" if kind == ANONYMOUS else "ethical"
        opts = self.options(kind) if hasattr(self, "hide_language") else anonymise.Options.for_kind(kind)
        stem = anonymise.archive_stem(self.main.doc.db, self.main.doc.notebook, opts)
        base = self.base / f"{stem} {word} archive {QDate.currentDate().toString('yyyy-MM-dd')}"
        path, n = base, 2
        while path.exists() and any(path.iterdir()):
            path, n = base.with_name(f"{base.name} ({n})"), n + 1
        return QDir.toNativeSeparators(str(path))

    def _update_folder(self):
        """The default folder follows the options (a hidden code mustn't show in its name),
        unless a folder of one's own was typed or chosen."""
        if not self.kind:
            return
        if not self.folder.text() or self.folder.text() == self._shown_default:
            self._shown_default = self._default_folder(self.kind)
            self.folder.edit.setText(self._shown_default)

    def set_kind(self, kind: str):
        """Switch to the other archive: its own defaults (Josh, 22 October)."""
        if kind == self.kind:
            return
        self.kind = kind
        anon = kind == ANONYMOUS
        defaults = anonymise.Options.for_kind(kind)
        self.setWindowTitle(f"Export {anonymise.TITLES[kind].lower()}")
        self.intro.setText(INTRO[kind])
        self.ai_note.setVisible(anon)
        self.codes_label.setVisible(anon)
        self.codes_row.setVisible(anon)
        for w in (self.hide_language, self.hide_variety):
            w.setChecked(False)
        self.notebook.setChecked(defaults.notebook)
        self.names.setChecked(True)
        self.names.setEnabled(not anon)           # nobody is named: always, in the anonymous archive
        self.names.setText("Names in comments, translations, notes and TextGrids are replaced with codes "
                           "(always, in an anonymous archive)" if anon else
                           "Replace the names of people who aren't identifiable, in comments, translations, "
                           "notes and TextGrids, with their codes")
        if anon:
            self.recordings.setChecked(False)
            self.recordings.setEnabled(False)
            self.recordings.setText("None in an anonymous archive (a voice undoes the anonymising)")
        else:
            self.recordings.setEnabled(True)
            self.recordings.setChecked(defaults.recordings)
            self.recordings.setText("Include the recordings of speakers who agreed to audio sharing")
        self.places.setCurrentIndex(self.places.findData(defaults.place_levels))
        self.thanks.setChecked(defaults.thanks)
        self.thanks.setEnabled(not anon and bool(self.main.doc.db.metadata.thanks))
        self.thanks.setText("None in an anonymous archive (they name people)" if anon else
                            "Include the personal thank-yous (Edit → Metadata → Acknowledgements)"
                            if self.main.doc.db.metadata.thanks else "None in the metadata")
        self.thanks_note.setVisible(False)
        self.consent.setItemText(1, "Add them, with the code key, as a password-protected zip" if anon
                                 else "Add them as a password-protected zip")
        self.consent.setToolTip("The key (old code → new code) is kept only inside this zip, never in the clear"
                                if anon else "")
        self._update_folder()
        self._enable()

    def _enable(self):
        zipped = bool(self.consent.currentData())
        for w in (self.password, self.password2):
            w.setEnabled(zipped)

    def options(self, kind: str | None = None) -> anonymise.Options:
        kind = kind or self.kind
        anon = kind == ANONYMOUS
        return anonymise.Options(
            kind=kind, notebook=self.notebook.isChecked(), replace_names=self.names.isChecked() or anon,
            recordings=self.recordings.isChecked() and not anon, place_levels=int(self.places.currentData()),
            consent_password=self.password.text() if self.consent.currentData() else "",
            hide_language_code=anon and self.hide_language.isChecked(),
            hide_variety_code=anon and self.hide_variety.isChecked(),
            thanks=self.thanks.isChecked() and not anon)

    def accept(self):
        if self.consent.currentData():
            if not self.password.text():
                QMessageBox.warning(self, "Export", "Give a password for the consent forms' zip.")
                return
            if self.password.text() != self.password2.text():
                QMessageBox.warning(self, "Export", "The two passwords aren't the same.")
                return
        folder = Path(self.folder.text().strip())
        if not str(folder).strip():
            QMessageBox.warning(self, "Export", "Choose a folder to export to.")
            return
        main = self.main
        try:
            anonymise.check_folder(main.doc.db, folder)
        except anonymise.ArchiveError as exc:
            QMessageBox.warning(self, "Export", f"{exc}\n\nChoose a new or empty folder.")
            return
        try:
            report = anonymise.export(main.doc.db, main.doc.notebook, folder, self.options())
        except (OSError, anonymise.ArchiveError) as exc:
            QMessageBox.warning(self, "Export", f"Couldn't export: {exc}")
            return
        QMessageBox.information(self, anonymise.TITLES[self.kind], anonymise.summary(report, self.options()))
        super().accept()


AnonymousExportDialog = ArchiveExportDialog       # the older name
