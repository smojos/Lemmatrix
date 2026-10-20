# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""File → Export → Anonymous backup…: choose what goes, then write the copy (see anonymise.py)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, QDir
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QLineEdit, QMessageBox, QVBoxLayout)

from .. import anonymise
from . import theme
from .dialogs import PathEdit


class AnonymousExportDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        db = main.doc.db
        self.setWindowTitle("Export anonymous backup")
        self.resize(620, 420)
        lay = QVBoxLayout(self)
        intro = QLabel("A copy to share or deposit. Participants' names, descriptions and consent links are "
                       "always taken out; their codes (SP1…) stay, since tokens, sessions and file names use "
                       "them. The database itself isn't changed.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        self.researchers = QCheckBox("Take out the researchers' names (and the owner's) too")
        self.notebook = QCheckBox("Include the notebook")
        self.notebook.setChecked(True)
        self.names = QCheckBox("Replace participants' names written in comments and notebook notes "
                               "with their codes")
        self.names.setChecked(True)
        self.recordings = QCheckBox("Include the recordings (voices are personal data too)")
        self.places = QComboBox()
        self.places.addItem("Keep every place", 0)
        self.places.addItem("Keep only the top two levels (e.g. country and county)", 2)
        self.places.addItem("Keep only the top level (country)", 1)
        self.consent = QComboBox()
        self.consent.addItem("Leave them out", False)
        self.consent.addItem("Add them as a password-protected zip", True)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("password")
        self.password2 = QLineEdit()
        self.password2.setEchoMode(QLineEdit.Password)
        self.password2.setPlaceholderText("the same again")
        if not anonymise.zip_available():
            self.consent.model().item(1).setEnabled(False)
            self.consent.setToolTip("Needs the pyzipper package (installed with the next start of Lemmatrix)")
        stem = Path(db.path).stem if db.path else "Database"
        from .. import layout                  # exports start in the database's Exports folder
        base = layout.exports_folder(main.doc.db.path) if main.doc.db.path else Path.home() / "Documents"
        start = base / f"{stem} anonymous {QDate.currentDate().toString('yyyy-MM-dd')}"
        self.folder = PathEdit(QDir.toNativeSeparators(str(start)), True, "Export to folder")
        form.addRow("People", self.researchers)
        form.addRow("Notebook", self.notebook)
        form.addRow("Free text", self.names)
        form.addRow("Recordings", self.recordings)
        form.addRow("Places", self.places)
        form.addRow("Consent forms", self.consent)
        form.addRow("", self.password)
        form.addRow("", self.password2)
        form.addRow("Folder", self.folder)
        lay.addLayout(form)
        note = QLabel("Free text can still hold things that identify people (a name not on the participant "
                      "list, a village). The report at the end lists every name replaced.")
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
        self.notebook.toggled.connect(lambda *_: self._enable())
        self._enable()

    def _enable(self):
        zipped = bool(self.consent.currentData())
        for w in (self.password, self.password2):
            w.setEnabled(zipped)

    def options(self) -> anonymise.Options:
        return anonymise.Options(
            researchers=self.researchers.isChecked(), notebook=self.notebook.isChecked(),
            replace_names=self.names.isChecked(), recordings=self.recordings.isChecked(),
            place_levels=int(self.places.currentData()),
            consent_password=self.password.text() if self.consent.currentData() else "")

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
        if folder.exists() and any(folder.iterdir()):
            if QMessageBox.question(self, "Export", f"{folder} isn't empty. Export into it anyway? "
                                    "Files with the same names are replaced.") != QMessageBox.Yes:
                return
        main = self.main
        try:
            report = anonymise.export(main.doc.db, main.doc.notebook, folder, self.options())
        except OSError as exc:
            QMessageBox.warning(self, "Export", f"Couldn't export: {exc}")
            return
        QMessageBox.information(self, "Anonymous backup", anonymise.summary(report, self.options()))
        super().accept()
