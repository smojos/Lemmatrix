# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The comparative wordlists' windows (IDEAS.md idea 40, Josh, 22 October 2026): choosing a list for
a new database, File → Export → Wordlist… (to the clipboard or a PDF) and Tools → Link to
wordlists…. The lists themselves are `lemmatrix/wordlists`."""

from __future__ import annotations

import datetime as _dt
import html
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF, Qt
from PySide6.QtGui import QGuiApplication, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QRadioButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import layout
from .. import wordlists as wl

BLANK = ""


def citation_tip(lid: str) -> str:
    """A list's hover: its citation and DOI (Josh: "hoverovers give a citation and/or DOI")."""
    tip = wl.CITATIONS[lid]
    if wl.DOIS.get(lid):
        tip += f"\nDOI: {wl.DOIS[lid]}"
    return tip


# --------------------------------------------------------------------------
# New database: which list to start from
# --------------------------------------------------------------------------
class WordlistChoice(QWidget):
    """Blank, EACW (recommended), CAWL or Swadesh, each with its citation in the hover: the
    wordlist section of File → New database (ui/new_database.py)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.group = QButtonGroup(self)
        choices = [
            (wl.EACW, f"{wl.NAMES[wl.EACW]} (recommended): {len(wl.get(wl.EACW).items):,} lemmas, "
                      "with Lemmatrix's reference categories (C001b)"),
            (wl.CAWL, f"{wl.NAMES[wl.CAWL]}: {len(wl.get(wl.CAWL).items):,} lemmas, numbered 0001–1700, "
                      "no categories"),
            (wl.SWADESH, f"{wl.NAMES[wl.SWADESH]}: {len(wl.get(wl.SWADESH).items)} lemmas, numbered "
                         "001–207, no categories"),
            (BLANK, "Blank: no lemmas"),
        ]
        for lid, text in choices:
            b = QRadioButton(text)
            b.setProperty("list", lid)
            if lid:
                b.setToolTip(citation_tip(lid))
            self.group.addButton(b)
            lay.addWidget(b)
            if lid == wl.EACW:
                b.setChecked(True)
        if not wl.get(wl.CAWL).has_glosses:
            note = QLabel("The CAWL's own glosses come with SIL's permission; until then its lemmas take "
                          "the Extended African Comparative Wordlist's gloss where the two match.")
            note.setWordWrap(True)
            note.setStyleSheet("color: grey;")
            lay.addWidget(note)
        note = QLabel("Every lemma also carries the other two lists' numbers, so the database can be "
                      "searched (CAWL 345) and exported as any of them.")
        note.setWordWrap(True)
        lay.addWidget(note)

    def choice(self) -> str:
        b = self.group.checkedButton()
        return b.property("list") if b is not None else BLANK


class StartListDialog(QDialog):
    """The wordlist choice on its own (kept for callers that ask only that)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New database")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Start the new database with:"))
        self.lists = WordlistChoice(self)
        self.group = self.lists.group
        lay.addWidget(self.lists)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def choice(self) -> str:
        return self.lists.choice()


def ask_start_list(parent) -> str | None:
    """The list a new database starts from ("" for blank), or None if cancelled."""
    d = StartListDialog(parent)
    return d.choice() if d.exec() == QDialog.Accepted else None


# --------------------------------------------------------------------------
# File → Export → Wordlist…
# --------------------------------------------------------------------------
class WordlistExportDialog(QDialog):
    """Every item of the chosen list in its order (blank where the database has nothing), with the
    lemma and the list's own gloss; gloss matches for the rest shown with ticks first."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.db = win.doc.db
        self.setWindowTitle("Export a wordlist")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("List:"))
        self.which = QComboBox()
        for lid in wl.LIST_IDS:
            self.which.addItem(f"{wl.SHORT[lid]}: {wl.NAMES[lid]}", lid)
            self.which.setItemData(self.which.count() - 1, citation_tip(lid), Qt.ToolTipRole)
        row.addWidget(self.which, 1)
        lay.addLayout(row)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Number", "List's gloss", "Lemma", "Its gloss"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table, 1)
        self.note = QLabel("Ticked matches are exported, and their number is kept on the lemma "
                           "(one undo step), so the next export finds them.")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        bb = QHBoxLayout()
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setToolTip("Copy the list (number, lemma, gloss) as a table, to paste into Word or Excel")
        self.pdf_btn = QPushButton("Save as PDF…")
        close = QPushButton("Close")
        bb.addStretch(1)
        for b in (self.copy_btn, self.pdf_btn, close):
            bb.addWidget(b)
        lay.addLayout(bb)
        self.copy_btn.clicked.connect(self.copy)
        self.pdf_btn.clicked.connect(self.save_pdf)
        close.clicked.connect(self.reject)
        self.which.currentIndexChanged.connect(self._fill)
        base = wl.base_of(self.db)
        others = [lid for lid in wl.LIST_IDS if lid != base]
        if others:
            self.which.setCurrentIndex(self.which.findData(others[0]))
        self._fill()

    def lid(self) -> str:
        return self.which.currentData()

    def _fill(self):
        lid = self.lid()
        self.matches = wl.gloss_matches(self.db, lid)
        self.table.setRowCount(len(self.matches))
        items = wl.get(lid).by_number
        for r, (num, e) in enumerate(self.matches):
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            tick.setCheckState(Qt.Checked)
            self.table.setItem(r, 0, tick)
            for c, text in enumerate((num, wl.item_gloss(lid, items[num]),
                                      f"{e.ref} {self.db.lemma(e)}", self.db.gloss(e)), start=1):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(r, c, it)
        rows = wl.rows(self.db, lid)
        have = sum(1 for x in rows if x.entries)
        parts = [f"{wl.NAMES[lid]}: {len(rows):,} items, {have:,} with a lemma in this database."]
        if self.matches:
            parts.append(f"{len(self.matches)} more found by gloss, below.")
        else:
            parts.append("No more found by gloss.")
        if lid == wl.CAWL and not wl.get(wl.CAWL).has_glosses:
            parts.append("(The CAWL's own glosses aren't included yet: the Extended African "
                         "Comparative Wordlist's are shown where the two match.)")
        self.summary.setText(" ".join(parts))
        self.table.setVisible(bool(self.matches))
        self.note.setVisible(bool(self.matches))

    def _ticked(self) -> list:
        return [self.matches[r] for r in range(self.table.rowCount())
                if self.table.item(r, 0).checkState() == Qt.Checked]

    def _remember(self, ticked):
        """Store the ticked matches' numbers on their lemmas: one undo step."""
        if not ticked:
            return
        lid = self.lid()
        pairs = []
        by_entry: dict[str, list] = {}
        for num, e in ticked:
            by_entry.setdefault(e.id, []).append(num)
        for e in self.db.entries:
            if e.id in by_entry:
                after = e.copy()
                nums = list(after.lists.get(lid, []))
                for n in by_entry[e.id]:
                    if n not in nums:
                        nums.append(n)
                after.lists[lid] = nums
                pairs.append((e, after))
        self.win.doc.apply_changes(f"Wordlist numbers ({wl.SHORT[lid]}) from glosses", pairs, stamp=False)
        self._fill()

    def _table(self):
        ticked = self._ticked()
        header, data = wl.table(self.db, self.lid(), ticked)
        self._remember(ticked)
        return header, data

    def copy(self):
        header, data = self._table()
        QGuiApplication.clipboard().setText(wl.tsv(header, data))
        self.win.statusBar().showMessage(f"Copied the {wl.SHORT[self.lid()]} list ({len(data):,} rows).", 6000)

    def save_pdf(self):
        lid = self.lid()
        db = self.db
        stem = Path(db.path).stem if db.path else "Lemmatrix"
        start = (layout.existing_folder(layout.exports_folder(db.path)) if db.path
                 else Path.home() / "Documents")
        path, _ = QFileDialog.getSaveFileName(self, "Save as PDF", str(start / f"{stem} - {wl.SHORT[lid]}.pdf"),
                                              "PDF (*.pdf)")
        if not path:
            return
        header, data = self._table()
        try:
            write_pdf(path, db, lid, header, data)
        except OSError as exc:
            QMessageBox.warning(self, "Save as PDF", f"Couldn't write {Path(path).name}: {exc}")
            return
        self.win.statusBar().showMessage(f"Saved {Path(path).name}.", 6000)


def pdf_html(db, lid: str, header, data) -> str:
    md = db.metadata
    title = " - ".join(x for x in (md.language_name or md.language_code, md.variety_name or md.variety_code,
                                   md.name) if x)
    esc = html.escape
    rows = "".join("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in r) + "</tr>" for r in data)
    doi = f"<br/>DOI: {esc(wl.DOIS[lid])}" if wl.DOIS.get(lid) else ""
    return (f"<h2>{esc(wl.NAMES[lid])}</h2>"
            f"<p>{esc(title)}<br/>{_dt.date.today().isoformat()}</p>"
            f"<p style='font-size:8pt; color:#555'>{esc(wl.CITATIONS[lid])}{doi}</p>"
            "<table border='0' cellspacing='0' cellpadding='3' width='100%'>"
            "<tr>" + "".join(f"<th align='left'>{esc(h)}</th>" for h in header) + "</tr>"
            f"{rows}</table>")


def write_pdf(path: str, db, lid: str, header, data):
    """An A4 PDF: the list's name and citation, the database, the date, then the three columns."""
    w = QPdfWriter(str(path))
    w.setPageSize(QPageSize(QPageSize.A4))
    w.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
    w.setTitle(f"{wl.NAMES[lid]}: {Path(db.path).stem if db.path else ''}")
    w.setCreator("Lemmatrix")
    doc = QTextDocument()
    doc.setDefaultStyleSheet("td, th { font-family: 'Charis SIL', 'Doulos SIL', serif; font-size: 10pt; }"
                             "th { border-bottom: 1px solid #888; }")
    doc.setHtml(pdf_html(db, lid, header, data))
    doc.setPageSize(QSizeF(w.width(), w.height()))
    doc.print_(w)
    if not Path(path).exists():
        raise OSError("the file wasn't written")


# --------------------------------------------------------------------------
# Tools → Link to wordlists…
# --------------------------------------------------------------------------
def link_to_wordlists(win):
    """Set an existing database's base list and give its lemmas the other lists' numbers from the
    mapping, by reference (Josh's database: EACW). One undo step."""
    db = win.doc.db
    current = wl.base_of(db)
    labels = [f"{wl.NAMES[x]} ({wl.SHORT[x]})" for x in wl.LIST_IDS]
    from PySide6.QtWidgets import QInputDialog
    start = wl.LIST_IDS.index(current) if current else 0
    text, ok = QInputDialog.getItem(win, "Link to wordlists",
                                    "This database's references are the numbers of:", labels, start, False)
    if not ok:
        return
    base = wl.LIST_IDS[labels.index(text)]
    known = sum(1 for e in db.entries if wl.canon(base, e.ref))
    if not known:
        QMessageBox.information(win, "Link to wordlists",
                                f"None of this database's references is an item of the {wl.NAMES[base]}.")
        return
    plan = wl.link_plan(db, base)
    others = [x for x in wl.LIST_IDS if x != base]
    msg = (f"{known:,} of the {len(db.entries):,} lemmas have references in the {wl.NAMES[base]}. "
           f"{len(plan):,} of them will get their {' and '.join(wl.SHORT[x] for x in others)} numbers "
           "from the mapping (kept hidden in the database file; searched with e.g. "
           f"“{wl.SHORT[others[0]].upper()} 1”, exported with File → Export → Wordlist…).")
    if not plan and current == base:
        QMessageBox.information(win, "Link to wordlists", msg.split(". ")[0] + ", and they are linked already.")
        return
    if QMessageBox.question(win, "Link to wordlists", msg + "\n\nLink them?") != QMessageBox.Yes:
        return
    pairs = []
    for e, new in plan:
        after = e.copy()
        after.lists = {k: v for k, v in after.lists.items() if k == base}
        after.lists.update(new)
        pairs.append((e, after))
    win.doc.set_wordlist_base(base, pairs)
    win.statusBar().showMessage(f"Linked {len(plan):,} lemmas to the wordlists.", 8000)
