"""Tools → Fill in recording dates from the sound files…: a preview, then one undo step."""

from __future__ import annotations

from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHeaderView, QLabel,
                               QRadioButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from .. import matrix as mx, recdates
from . import theme
from .widgets import ipa_font


class RecordingDatesDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.db = main.doc.db
        self.setWindowTitle("Fill in recording dates")
        self.resize(900, 560)
        lay = QVBoxLayout(self)
        intro = QLabel("A token's date (when it was recorded) is taken from its sound file's own metadata: "
                       "the creation date Lemmatrix writes into its recordings, or the date a field recorder "
                       "or sound editor wrote. Check the list, then Fill in. One undo step undoes it all.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.only_empty = QRadioButton("Only tokens that have no date")
        self.only_empty.setChecked(True)
        self.overwrite = QRadioButton("Also change dates that differ from the sound file's")
        self.file_dates = QCheckBox("When a sound file has no date in it, use the date the file was last changed")
        self.file_dates.setToolTip("Less reliable: copying, converting or syncing a file can change this date")
        for w in (self.only_empty, self.overwrite, self.file_dates):
            lay.addWidget(w)
            (w.toggled).connect(lambda *_: self._fill())
        self.tree = QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["Lemma", "Tags", "Sound file", "Date now", "New date", "From"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        lay.addWidget(self.tree, 1)
        self.count = QLabel()
        self.count.setWordWrap(True)
        self.count.setStyleSheet(f"color: {theme.muted()};")
        lay.addWidget(self.count)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.fill_btn = buttons.addButton("Fill in", QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.changes = []
        self._fill()

    def _fill(self):
        self.changes, counts = recdates.plan(self.db, overwrite=self.overwrite.isChecked(),
                                            file_dates=self.file_dates.isChecked(),
                                            skip=getattr(self.main, "cloud_files", set()))
        self.tree.clear()
        db = self.db
        defaults = mx.default_names(db)
        for c in self.changes:
            t = c.entry.tokens[c.index]
            tags = " + ".join(mx.chips(db, [x for x in t.tags if x not in defaults])) or "citation"
            it = QTreeWidgetItem([f"{c.entry.ref} {db.lemma(c.entry)}", tags, t.file, c.old or "—", c.new,
                                  c.source])
            it.setFont(0, ipa_font(self.main.prefs.ipa_size))
            self.tree.addTopLevelItem(it)
        left = "; ".join(f"{n} {what}" for what, n in counts.items())
        self.count.setText(f"{len(self.changes)} date(s) to fill in." + (f"  Left alone: {left}." if left else ""))
        self.fill_btn.setEnabled(bool(self.changes))

    def accept(self):
        if self.changes:
            recdates.apply(self.main.doc, self.changes)
            self.main.statusBar().showMessage(f"{len(self.changes)} recording date(s) filled in.", 5000)
        super().accept()
