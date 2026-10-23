# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Tools → Convert references from a table… (Josh, 23 October 2026): the preview of a conversion map
and the conversion itself, as one undo step. The working part is `lemmatrix/convert_refs.py`."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from .. import convert_refs as cr
from .. import wordlists as wl


class ConvertReferencesDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win, self.db = win, win.doc.db
        self.plan: cr.Plan | None = None
        self.setWindowTitle("Convert references from a table")
        self.resize(860, 620)
        lay = QVBoxLayout(self)
        intro = QLabel("A conversion map changes the database's references all at once: a CSV or "
                       "tab-separated table with the columns <b>old</b> and <b>new</b> (<b>-</b> deletes "
                       "a lemma that has no data), and optionally <b>gloss</b> and <b>old gloss</b> (the "
                       "gloss changes only where it is still the old one). Recordings and pictures whose "
                       "names were up to date are renamed with their lemmas. One undo step.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        row = QHBoxLayout()
        choose = QPushButton("Choose a table…")
        choose.clicked.connect(self.choose)
        self.file_label = QLabel("No table chosen.")
        row.addWidget(choose)
        row.addWidget(self.file_label, 1)
        lay.addLayout(row)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Now", "Becomes", "Gloss", "What happens"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.table, 1)
        self.reorder = QCheckBox("Put the lemmas in the order of the Extended African Comparative Wordlist")
        self.reorder.setToolTip("Lemmas whose references are items of the list go in the list's order; "
                                "your own stay after the lemma they follow now.")
        self.reorder.setChecked(wl.is_eacw(self.db))
        lay.addWidget(self.reorder)
        bar = QHBoxLayout()
        bar.addStretch(1)
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setEnabled(False)
        self.convert_btn.clicked.connect(self.convert)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        bar.addWidget(self.convert_btn)
        bar.addWidget(cancel)
        lay.addLayout(bar)

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a conversion table", "",
                                              "Tables (*.csv *.tsv *.txt);;All files (*)")
        if path:
            self.load(path)

    def load(self, path: str):
        try:
            rows = cr.read_table(path)
        except (cr.TableError, OSError, UnicodeDecodeError) as exc:
            QMessageBox.warning(self, "Convert references", str(exc))
            return
        self.file_label.setText(path)
        self.plan = p = cr.plan(self.db, rows)
        self._show(p)

    def _show(self, p: cr.Plan):
        db = self.db
        glossed = {id(e): g for e, g in p.glosses}
        refs = {id(e): r for e, r in p.refs}
        lines = [(e.ref, ref, glossed.get(id(e), ""), "reference" + (" and gloss" if id(e) in glossed else ""))
                 for e, ref in p.refs]
        lines += [(e.ref, e.ref, g, "gloss") for e, g in p.glosses if id(e) not in refs]
        lines += [(e.ref, "", "", "deleted (empty)") for e in p.deletions]
        lines += [(e.ref, e.ref, "", why) for e, why in p.left]
        self.table.setRowCount(len(lines))
        for r, vals in enumerate(lines):
            for c, v in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()
        with_data = sum(1 for e, _ in p.refs if cr.has_data(db, e))
        parts = [f"{len(p.refs):,} references change ({with_data:,} of those lemmas have data)",
                 f"{len(p.glosses):,} glosses change", f"{len(p.deletions):,} empty lemmas are deleted"]
        if p.unknown:
            parts.append(f"{len(p.unknown):,} references in the table aren't in this database "
                         f"({', '.join(p.unknown[:8])}{'…' if len(p.unknown) > 8 else ''})")
        text = "; ".join(parts) + "."
        if p.problems:
            text += "<br><b>Nothing can change until the table is put right:</b><br>" + "<br>".join(p.problems[:20])
        self.summary.setText(text)
        self.convert_btn.setEnabled(not p.problems and p.changes > 0)
        self.reorder.setChecked(self._mostly_eacw())

    def _mostly_eacw(self) -> bool:
        """Whether most of the references after the conversion are items of the EACW."""
        p = self.plan
        new_of = {id(e): r for e, r in p.refs} if p else {}
        gone = {id(e) for e in p.deletions} if p else set()
        refs = [new_of.get(id(e), e.ref) for e in self.db.entries if id(e) not in gone]
        return bool(refs) and sum(1 for r in refs if wl.canon(wl.EACW, r)) > len(refs) / 2

    def convert(self):
        p = self.plan
        if p is None or p.problems:
            return
        db, doc = self.db, self.win.doc
        pairs = cr.converted(db, p)
        renames, notes = cr.file_renames(db, pairs)
        pairs = cr.token_files(db, pairs)
        gone = {id(e) for e in p.deletions}
        order = [e for e in db.entries if id(e) not in gone]
        if self.reorder.isChecked():
            after = {id(e): a for e, a in pairs}
            keyed = [(after.get(id(e), e), e) for e in order]       # sorted by the new references
            pos = {id(a): k for k, a in enumerate(wl.eacw_order([a for a, _ in keyed]))}
            order = [e for a, e in sorted(keyed, key=lambda x: pos[id(x[0])])]
        trouble = doc.restructure("Convert references", order, pairs, renames)
        if trouble:
            QMessageBox.warning(self, "Convert references", "Nothing was changed:\n" + "\n".join(trouble))
            return
        self.win.lemmas.set_rows(db.entries)
        msg = (f"Converted: {len(p.refs):,} references, {len(p.glosses):,} glosses, "
               f"{len(p.deletions):,} empty lemmas deleted, {len(renames) // 2:,} files renamed.")
        if notes:
            msg += "\n\nLeft as they were:\n" + "\n".join(notes[:20])
        if wl.is_eacw(db) or self.reorder.isChecked():
            msg += ("\n\nNext: Tools → Link to wordlists… gives the lemmas the list's CAWL and Swadesh "
                    "numbers, Clarification and Taxon; right-click a lemma → Insert EACW items… adds "
                    "the items the database doesn't have yet.")
        QMessageBox.information(self, "Convert references", msg)
        self.accept()
