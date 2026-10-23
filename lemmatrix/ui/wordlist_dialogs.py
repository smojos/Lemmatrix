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
WHY_EACW = ("Why the EACW? Its references mean something: the letter is the domain (D mammals, F fish, "
            "Q numbers), f and m are female and male, and you can add a, b, c… varieties under any item "
            "without losing the comparison. Ambiguous glosses come with a plain-English clarification, "
            "animals and plants with their taxon, and it comes in regional versions (East, West, North, "
            "South and Central Africa). Uncommon items are hidden but within reach, and every item is "
            "linked to the SIL Comparative African Wordlist and the Swadesh list, so your data can be "
            "exported as either.")


class WordlistChoice(QWidget):
    """Blank, EACW (recommended), CAWL or Swadesh, each with its citation in the hover: the
    wordlist section of File → New database (ui/new_database.py). The EACW comes in versions (Josh,
    23 October): Base (its default items) or Expanded (its hidden items too), and Global, Africa or
    one region; the ⓘ beside it says why to choose it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from . import theme
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.group = QButtonGroup(self)
        choices = [
            (wl.EACW, f"{wl.NAMES[wl.EACW]} (recommended), with Lemmatrix's reference categories (C001f)"),
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
            if lid == wl.EACW:
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.addWidget(b)
                info = QLabel("ⓘ")
                info.setToolTip(WHY_EACW)
                info.setStyleSheet(f"color: {theme.muted()};")
                row.addWidget(info)
                row.addStretch(1)
                lay.addLayout(row)
                b.setChecked(True)
                lay.addWidget(self._version_row())
            else:
                lay.addWidget(b)
        self.group.buttonToggled.connect(lambda *_: self._update())
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
        self._update()

    def _version_row(self) -> QWidget:
        """Items (Base, Expanded) and Region (Global, Africa, North… Central), with the count."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(24, 0, 0, 0)
        self.items = QComboBox()
        self.items.addItem("Base: the published list", wl.BASE)
        self.items.addItem("Expanded: with the hidden items", wl.EXPANDED)
        self.items.setToolTip("Base: the published list's default items. Expanded: every item, the "
                              "hidden ones too (the recommended variants: female and male forms, "
                              "plurals, rarer contrasts). A hidden item can always be inserted later "
                              "(right-click a lemma → Insert EACW items…).")
        self.region = QComboBox()
        for key in (wl.GLOBAL, wl.AFRICA, *wl.REGIONS):
            self.region.addItem(wl.REGION_NAMES[key], key)
        self.region.setCurrentIndex(self.region.findData(wl.AFRICA))
        self.region.setToolTip("Global: only the items for everyone (no African sub code). Africa: every "
                               "region's items. North, West, East, South or Central: the items for "
                               "everyone, for all of Africa, and for that region.")
        self.count = QLabel()
        self.count.setStyleSheet("color: grey;")
        h.addWidget(QLabel("Items"))
        h.addWidget(self.items)
        h.addSpacing(12)
        h.addWidget(QLabel("Region"))
        h.addWidget(self.region)
        h.addSpacing(12)
        h.addWidget(self.count)
        h.addStretch(1)
        self.items.currentIndexChanged.connect(self._update)
        self.region.currentIndexChanged.connect(self._update)
        self.version_row = w
        return w

    def _update(self, *_):
        n = len(wl.version_items(*self.version()))
        self.count.setText(f"{n:,} lemmas")
        self.version_row.setEnabled(self.choice() == wl.EACW)

    def version(self) -> tuple[str, str]:
        """The EACW's version chosen: (items, region)."""
        return self.items.currentData(), self.region.currentData()

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


def pdf_researcher(db) -> tuple[str, str]:
    """The researcher a wordlist PDF names: the database's owner (Edit → Metadata), else its first
    researcher; and their email where the researchers' list has one."""
    md = db.metadata
    owner = (md.author or "").strip()
    people = [p for p in md.researchers if p.name or p.code]
    match = next((p for p in people if owner and owner.casefold() in (p.name.casefold(), p.code.casefold())),
                 None)
    if match is None and not owner and people:
        match = people[0]
    name = owner if owner and (match is None or owner.casefold() != match.code.casefold()) else \
        (match.name or match.code if match else "")
    return name, (match.email if match else "")


def pdf_details(db, lid: str) -> list[str]:
    """The lines under a wordlist PDF's title (Josh, 23 October: basic metadata of the researcher
    and the language code): the language and variety with their codes, the database, the
    researcher, the list's version for the EACW, and the date."""
    md = db.metadata
    def named(name, code):
        return f"{name} [{code}]" if name and code and name != code else (name or code)
    lines = []
    lang = named(md.language_name, md.language_code)
    if lang:
        lines.append(f"Language: {lang}" + (f" · variety: {named(md.variety_name, md.variety_code)}"
                                            if md.variety_name or md.variety_code else ""))
    if md.name:
        lines.append(f"Database: {md.name}")
    name, email = pdf_researcher(db)
    if name or email:
        lines.append("Researcher: " + " ".join(x for x in (name, f"<{email}>" if email else "") if x))
    if lid == wl.EACW and md.wordlist_items:
        lines.append(f"EACW version: {wl.version_name(md.wordlist_items, md.wordlist_region)}")
    lines.append(f"Exported: {_dt.date.today().isoformat()}")
    return lines


def pdf_html(db, lid: str, header, data) -> str:
    md = db.metadata
    esc = html.escape
    rows = "".join("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in r) + "</tr>" for r in data)
    doi = f"<br/>DOI: {esc(wl.DOIS[lid])}" if wl.DOIS.get(lid) else ""
    return (f"<h2>{esc(wl.NAMES[lid])}</h2>"
            f"<p>{'<br/>'.join(esc(x) for x in pdf_details(db, lid))}</p>"
            f"<p style='font-size:8pt; color:#555'>{esc(wl.CITATIONS[lid])}{doi}</p>"
            "<table border='0' cellspacing='0' cellpadding='3' width='100%'>"
            "<thead><tr>" + "".join(f"<th align='left' width='{w}'>{esc(h)}</th>"
                                    for h, w in zip(header, ("12%", "44%", "44%"))) + "</tr></thead>"
            f"<tbody>{rows}</tbody></table>")


def write_pdf(path: str, db, lid: str, header, data):
    """An A4 PDF: the list's name and citation, the database, the date, then the three columns."""
    w = QPdfWriter(str(path))
    w.setPageSize(QPageSize(QPageSize.A4))
    w.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)
    w.setTitle(f"{wl.NAMES[lid]}: {Path(db.path).stem if db.path else ''}")
    w.setCreator("Lemmatrix")
    name, _ = pdf_researcher(db)
    if name:
        w.setAuthor(name)
    # The page laid out at 96 dpi, the resolution the text's point sizes assume (Josh, 23 October:
    # at QPdfWriter's own 1200 dpi the whole list came out on one page in type too small to read)
    w.setResolution(96)
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(w)
    doc.setDefaultStyleSheet("td, th { font-family: 'Charis SIL', 'Doulos SIL', serif; font-size: 10pt; }"
                             "th { border-bottom: 1px solid #888; }")
    doc.setHtml(pdf_html(db, lid, header, data))
    rect = w.pageLayout().paintRectPixels(w.resolution())
    doc.setPageSize(QSizeF(rect.width(), rect.height()))
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
    compared, wrong = wl.gloss_mismatches(db, base)
    if wrong and len(wrong) >= 3 and len(wrong) * 3 >= compared:   # a third or more: probably not its numbers
        sample = "; ".join(f"{e.ref} {db.gloss(e, 'en') or db.gloss(e)} ≠ {wl.item_gloss(base, i)}"
                           for e, i in wrong[:5])
        box = QMessageBox(QMessageBox.Warning, "Link to wordlists",
                          f"{len(wrong):,} of the {compared:,} lemmas' glosses don't match the "
                          f"{wl.NAMES[base]}'s items ({sample}{'…' if len(wrong) > 5 else ''}).\n\n"
                          f"Are these references really numbers of the {wl.NAMES[base]}? Linking gives "
                          "each lemma the numbers of the item with its reference, whatever its gloss.",
                          parent=win)
        go = box.addButton("Link anyway", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is not go:
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
    if base == wl.EACW:
        msg += (" They also get the list's Clarification and Taxon where theirs are empty (two lemma "
                "fields, added if the database doesn't have them), and the list's word classes join the "
                "Word Class list.")
    if QMessageBox.question(win, "Link to wordlists", msg + "\n\nLink them?") != QMessageBox.Yes:
        return
    if base == wl.EACW and (wl.ensure_fields(db) + wl.ensure_word_classes(db)):
        win.doc.settings_changed()
        win._setup_columns()
    changed = {}
    for e, new in plan:
        after = changed.setdefault(id(e), (e, e.copy()))[1]
        after.lists = {k: v for k, v in after.lists.items() if k == base}
        after.lists.update(new)
    if base == wl.EACW:
        for e, vals in wl.field_plan(db):
            after = changed.setdefault(id(e), (e, e.copy()))[1]
            for name, value in vals.items():
                after.set(name, value)
    win.doc.set_wordlist_base(base, list(changed.values()))
    win.statusBar().showMessage(f"Linked {len(changed):,} lemmas to the wordlists.", 8000)


# --------------------------------------------------------------------------
# Insert EACW items… (Josh, 23 October: a hidden item can always be inserted later)
# --------------------------------------------------------------------------
class InsertItemsDialog(QDialog):
    """The EACW items an EACW database doesn't have, to tick and insert: those beside a lemma (its
    hidden letters) or any, by version (Base, Expanded) and region, with a search. Each goes in
    after the lemma of the item before it in the list; one undo step."""

    def __init__(self, win, near=None):
        super().__init__(win)
        from PySide6.QtWidgets import QCheckBox, QLineEdit
        self.win, self.db, self.near = win, win.doc.db, near
        self.setWindowTitle("Insert EACW items")
        self.resize(820, 600)
        lay = QVBoxLayout(self)
        intro = QLabel("Items of the Extended African Comparative Wordlist that this database doesn't have "
                       "yet. Grey ones are hidden in the published list (recommended variants). Each "
                       "lemma gets the list's gloss, word class, Clarification and Taxon, and its CAWL "
                       "and Swadesh numbers.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        row = QHBoxLayout()
        self.only_near = QCheckBox(f"Only beside {near.ref}" if near is not None else "")
        self.only_near.setVisible(near is not None)
        self.only_near.setChecked(near is not None)
        self.items = QComboBox()
        self.items.addItem("Expanded: hidden items too", wl.EXPANDED)
        self.items.addItem("Base: published items only", wl.BASE)
        self.region = QComboBox()
        for key in (wl.GLOBAL, wl.AFRICA, *wl.REGIONS):
            self.region.addItem(wl.REGION_NAMES[key], key)
        self.region.setCurrentIndex(max(0, self.region.findData(self.db.metadata.wordlist_region or wl.AFRICA)))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search references and glosses")
        self.search.setClearButtonEnabled(True)
        for w in (self.only_near, QLabel("Items"), self.items, QLabel("Region"), self.region, self.search):
            row.addWidget(w)
        lay.addLayout(row)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Reference", "Gloss", "Sub", "Clarification"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.table, 1)
        bar = QHBoxLayout()
        tick_all, untick = QPushButton("Tick all shown"), QPushButton("Untick all")
        tick_all.clicked.connect(lambda: self._tick_all(True))
        untick.clicked.connect(lambda: self._tick_all(False))
        bar.addWidget(tick_all)
        bar.addWidget(untick)
        bar.addStretch(1)
        self.insert_btn = QPushButton("Insert")
        self.insert_btn.setDefault(True)
        self.insert_btn.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        bar.addWidget(self.insert_btn)
        bar.addWidget(cancel)
        lay.addLayout(bar)
        self.ticked: set[str] = set()
        self.shown: list = []
        for sig in (self.only_near.toggled, self.items.currentIndexChanged, self.region.currentIndexChanged,
                    self.search.textChanged):
            sig.connect(lambda *_: self._fill())
        self.table.itemChanged.connect(self._ticked_changed)
        if near is not None:                       # what is beside the lemma starts ticked
            self.ticked = {i.number for i in wl.missing_family(self.db, near)}
        self._fill()

    def candidates(self) -> list:
        items, region = self.items.currentData(), self.region.currentData()
        pool = wl.missing_family(self.db, self.near) if self.only_near.isChecked() and self.near is not None \
            else wl.missing(self.db)
        q = self.search.text().strip().casefold()
        return [i for i in pool if wl.in_version(i, items, region)
                and (not q or q in i.number.casefold() or q in i.gloss.casefold())]

    def _fill(self):
        from PySide6.QtGui import QColor
        self.table.blockSignals(True)
        self.shown = self.candidates()
        self.table.setRowCount(len(self.shown))
        grey = QColor("#8c8c8c")
        for r, i in enumerate(self.shown):
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            tick.setCheckState(Qt.Checked if i.number in self.ticked else Qt.Unchecked)
            self.table.setItem(r, 0, tick)
            for c, text in enumerate((i.number, i.gloss, " ".join(i.sub), i.clarification), start=1):
                it = QTableWidgetItem(text)
                if not i.default:
                    it.setForeground(grey)
                    it.setToolTip("Hidden in the published list")
                self.table.setItem(r, c, it)
        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)
        self._count()

    def _ticked_changed(self, it):
        if it.column() != 0:
            return
        n = self.shown[it.row()].number
        (self.ticked.add if it.checkState() == Qt.Checked else self.ticked.discard)(n)
        self._count()

    def _tick_all(self, on: bool):
        for i in self.shown:
            (self.ticked.add if on else self.ticked.discard)(i.number)
        self._fill()

    def _count(self):
        n = len(self.ticked)
        self.insert_btn.setText(f"Insert {n:,}" if n else "Insert")
        self.insert_btn.setEnabled(bool(n))

    def chosen(self) -> list:
        return [i for i in wl.get(wl.EACW).items if i.number in self.ticked]


def insert_items(win, items) -> list:
    """New lemmas for EACW items, each after the lemma of the item before it; one undo step.
    Returns the new lemmas."""
    db = win.doc.db
    order = list(db.entries)
    classes = set(db.settings.word_classes())
    made = []
    for item in items:
        e = db.new_entry(item.number, gloss=item.gloss,
                         word_class=item.word_class if item.word_class in classes else "",
                         speaker=win.session_speaker(), date=win.session_date())
        wl.fill_item(db, e, item)
        order.insert(wl.insert_position(order, item.number), e)
        made.append(e)
    if made:
        win.doc.restructure(f"Insert {len(made)} EACW item{'s' if len(made) != 1 else ''}", order)
    return made


def insert_eacw_items(win, near=None):
    """Right-click a lemma → Insert EACW items… (or Tools): pick and insert."""
    db = win.doc.db
    if not wl.is_eacw(db):
        QMessageBox.information(win, "Insert EACW items",
                                "This database isn't built on the Extended African Comparative Wordlist "
                                "(Tools → Link to wordlists… sets that).")
        return
    if not wl.missing(db):
        QMessageBox.information(win, "Insert EACW items", "This database has every item of the list.")
        return
    d = InsertItemsDialog(win, near)
    if d.exec() != QDialog.Accepted:
        return
    made = insert_items(win, d.chosen())
    win.lemmas.set_rows(db.entries)
    if made:
        win.lemmas.select_row(made[0])
        win.statusBar().showMessage(f"Inserted {len(made):,} EACW item(s).", 8000)


# --------------------------------------------------------------------------
# Tools → Check reference order… (Josh, 23 October)
# --------------------------------------------------------------------------
def check_reference_order(win):
    """The lemmas that aren't where the EACW's order puts them, with an offer to move them; one
    undo step. The order: the list's items at their places, the researcher's own references inside
    their item's family (B001b after B001), other references at the end of their section (C + ISO
    code after the last C item)."""
    db = win.doc.db
    title = "Check reference order"
    if not wl.is_eacw(db):
        QMessageBox.information(win, title, "This database isn't built on the Extended African Comparative "
                                "Wordlist (Tools → Link to wordlists… sets that).")
        return
    order, moving = wl.out_of_place(db.entries)
    if not moving:
        QMessageBox.information(win, title, f"All {len(db.entries):,} lemmas are in the list's order.")
        return
    before = {id(e): (db.entries[k - 1].ref if k else "(the start)") for k, e in enumerate(db.entries)}
    after = {id(e): (order[k - 1].ref if k else "(the start)") for k, e in enumerate(order)}
    d = QDialog(win)
    d.setWindowTitle(title)
    d.resize(640, 520)
    lay = QVBoxLayout(d)
    note = QLabel(f"{len(moving):,} of the {len(db.entries):,} lemmas aren't in the list's order. Your own "
                  "references go inside their item's family (B001b after B001) and other references "
                  "at the end of their section (an ethnic group's C + ISO code after the last C item).")
    note.setWordWrap(True)
    lay.addWidget(note)
    table = QTableWidget(len(moving), 4)
    table.setHorizontalHeaderLabels(["Lemma", "Gloss", "Now after", "Goes after"])
    table.verticalHeader().hide()
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    for r, e in enumerate(moving):
        for c, v in enumerate((e.ref, db.gloss(e), before[id(e)], after[id(e)])):
            table.setItem(r, c, QTableWidgetItem(v))
    table.resizeColumnsToContents()
    lay.addWidget(table, 1)
    buttons = QDialogButtonBox()
    move = buttons.addButton(f"Move {len(moving):,}", QDialogButtonBox.AcceptRole)
    buttons.addButton("Close", QDialogButtonBox.RejectRole)
    buttons.accepted.connect(d.accept)
    buttons.rejected.connect(d.reject)
    move.setDefault(True)
    lay.addWidget(buttons)
    if d.exec() != QDialog.Accepted:
        return
    win.doc.restructure(f"Move {len(moving):,} lemmas into the list's order", order)
    win.lemmas.set_rows(db.entries)
    win.statusBar().showMessage(f"Moved {len(moving):,} lemmas into the list's order.", 8000)
