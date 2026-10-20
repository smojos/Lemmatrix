# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Edit → Lists: every list in one place.

Researchers, participants (with the file documenting their consent), locations
(hierarchical, with codes and descriptions), the closed fields' lists (Tone Class,
Inflection Class, Word Class...), and the tag structure. Codes renamed here are followed
everywhere: token speakers and notebook sessions; renamed list values are followed in the
lemmas and tokens, and renamed word classes in the tag groups' "usual for" hints.
"""

from __future__ import annotations

import re

from pathlib import Path

from PySide6.QtCore import QDir, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..model import (LEMMAS, TEXTS, UTTERANCES, Database, Location, Person, RefCategory, TierMapping, TierRule,
                     forbidden_in, nfc)
from .. import defaults, resets
from . import theme
from .chiprow import LOCATIONS, PARTICIPANTS, RESEARCHERS, consent_path
from .dialogs import TagStructureDialog
from .fields_dialog import ListEditor
from .icons import icon

TAGS = "tags"
ORIGINAL = Qt.UserRole + 7                    # a row's code when the dialogue opened


def _tool(name, tip, fn, text=""):
    b = QToolButton()
    if name:
        b.setIcon(icon(name, 20))
    if text:
        b.setText(text)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if name else Qt.ToolButtonTextOnly)
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.clicked.connect(lambda *_, fn=fn: fn())
    return b


def _note(text) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {theme.muted()};")
    return lbl


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------

class PeopleEditor(QWidget):
    """Researchers (code, name, email, description) or participants (code, name, the
    Identifiable? and Audio sharing? ticks from their consent form, description, consent file)."""

    def __init__(self, db: Database, people: list[Person], consent: bool, used, parent=None):
        super().__init__(parent)
        self.db, self.consent, self.used = db, consent, used
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if consent:
            self.cols = ["code", "name", "identifiable", "audio", "description", "consent"]
            heads = ["Code", "Name", "Identifiable?", "Audio sharing?", "Description", "Consent file"]
        else:
            self.cols = ["code", "name", "email", "description"]
            heads = ["Code", "Name", "Email", "Description"]
        self.table = QTableWidget(0, len(self.cols))
        self.table.setHorizontalHeaderLabels(heads)
        if consent:
            for key, tip in (("identifiable", "Agreed in the consent form to be identified by name"),
                             ("audio", "Agreed in the consent form that their recordings may be shared "
                                       "(e.g. sent to another speaker in an ɛλicit request)")):
                self.table.horizontalHeaderItem(self.col(key)).setToolTip(tip)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        for p in people:
            self._add_row(p)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, max(self.table.columnWidth(1), 200))
        if not consent:
            self.table.setColumnWidth(self.col("email"), max(self.table.columnWidth(self.col("email")), 180))
        d = self.col("description")
        self.table.setColumnWidth(d, min(max(self.table.columnWidth(d), 160), 260))
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(_tool("add", "Add a person", lambda: self._add_row(Person(""), edit=True)))
        row.addWidget(_tool("delete", "Remove the selected person", self._remove))
        row.addWidget(_tool("up", "Move up", lambda: self._shift(-1)))
        row.addWidget(_tool("down", "Move down", lambda: self._shift(1)))
        if consent:
            row.addSpacing(12)
            row.addWidget(_tool(None, "Choose the file documenting this participant's consent",
                                self._choose_consent, "Choose consent file…"))
            row.addWidget(_tool(None, "Open the selected participant's consent file",
                                self._open_consent, "Open consent file"))
            self.table.cellClicked.connect(self._cell_clicked)
        row.addStretch(1)
        lay.addLayout(row)

    def col(self, key: str) -> int:
        return self.cols.index(key)

    def load(self, people: list[Person]):
        """Show these people instead (Reset to defaults)."""
        self.table.setRowCount(0)
        for p in people:
            self._add_row(p)

    def _add_row(self, p: Person, edit: bool = False):
        r = self.table.rowCount()
        self.table.insertRow(r)
        values = {"code": p.code, "name": p.name, "email": p.email, "description": p.description,
                  "consent": p.consent, "identifiable": p.identifiable, "audio": p.audio_sharing}
        for c, key in enumerate(self.cols):
            v = values[key]
            if key == "consent":
                it = self._consent_item(v)
            elif key in ("identifiable", "audio"):
                it = QTableWidgetItem()
                it.setFlags((it.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable)
                it.setCheckState(Qt.Checked if v else Qt.Unchecked)
            else:
                it = QTableWidgetItem(v)
                if key == "description":
                    it.setToolTip(v)
            self.table.setItem(r, c, it)
        self.table.item(r, 0).setData(ORIGINAL, p.code)
        if edit:
            self.table.setCurrentCell(r, 0)
            self.table.editItem(self.table.item(r, 0))

    def _consent_item(self, path: str) -> QTableWidgetItem:
        """The consent file, as a link: click to open it (Choose consent file… changes it)."""
        it = QTableWidgetItem(path)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        if path:
            f = QFont(self.table.font())
            f.setUnderline(True)
            it.setFont(f)
            it.setForeground(theme.accent())
            full = consent_path(self.db, path)
            it.setToolTip(f"Click to open {full}" + ("" if full and full.exists() else "\n(the file isn't there)"))
        return it

    def _cell_clicked(self, r, c):
        if self.consent and c == self.col("consent") and self._text(r, c):
            self._open_consent()

    def _text(self, r, c) -> str:
        it = self.table.item(r, c)
        return nfc(it.text().strip()) if it else ""

    def _ticked(self, r, key) -> bool:
        it = self.table.item(r, self.col(key))
        return bool(it) and it.checkState() == Qt.Checked

    def _remove(self):
        r = self.table.currentRow()
        if r < 0:
            return
        code = self._text(r, 0)
        original = self.table.item(r, 0).data(ORIGINAL) or ""
        n = self.used(original) if original else ""
        if n and QMessageBox.question(self, "Remove", f"{code} is {n}.\n\nRemove them from the list anyway? "
                                      "Those keep the code.") != QMessageBox.Yes:
            return
        self.table.removeRow(r)

    def _shift(self, step):
        r = self.table.currentRow()
        j = r + step
        if r < 0 or not 0 <= j < self.table.rowCount():
            return
        for c in range(self.table.columnCount()):
            a, b = self.table.takeItem(r, c), self.table.takeItem(j, c)
            self.table.setItem(r, c, b)
            self.table.setItem(j, c, a)
        self.table.setCurrentCell(j, self.table.currentColumn())

    def _choose_consent(self):
        r = self.table.currentRow()
        if r < 0:
            QMessageBox.information(self, "Consent", "Select a participant first.")
            return
        c = self.col("consent")
        current = consent_path(self.db, self._text(r, c))
        from .. import layout                  # consent forms belong in Documentation
        start = str(current) if current and current.exists() else (
            str(layout.existing_folder(layout.documentation_folder(self.db.path))) if self.db.path
            else str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(self, f"Consent documentation for {self._text(r, 0)}", start)
        if not path:
            return
        p = Path(path)
        if self.db.path:                       # inside the database's folder: stored relative to it
            try:
                p = p.relative_to(Path(self.db.path).parent)
            except ValueError:
                pass
        self.table.setItem(r, c, self._consent_item(QDir.toNativeSeparators(str(p))))

    def _open_consent(self):
        r = self.table.currentRow()
        if r < 0:
            return
        path = consent_path(self.db, self._text(r, self.col("consent")))
        if path is None:
            QMessageBox.information(self, "Consent", "No consent file is set for this participant.")
        elif not path.exists():
            QMessageBox.warning(self, "Consent", f"The file isn't there:\n{path}")
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def people(self) -> list[Person]:
        out = []
        for r in range(self.table.rowCount()):
            code = self._text(r, 0)
            if not code:
                continue
            p = Person(code, self._text(r, 1), self._text(r, self.col("description")))
            if self.consent:
                p.consent = self._text(r, self.col("consent"))
                p.identifiable = self._ticked(r, "identifiable")
                p.audio_sharing = self._ticked(r, "audio")
            else:
                p.email = self._text(r, self.col("email"))
            out.append(p)
        return out

    def renames(self) -> dict[str, str]:
        out = {}
        for r in range(self.table.rowCount()):
            old, new = self.table.item(r, 0).data(ORIGINAL) or "", self._text(r, 0)
            if old and new and old != new:
                out[old] = new
        return out

    def problem(self) -> str:
        seen = set()
        for r in range(self.table.rowCount()):
            code = self._text(r, 0)
            if not code:
                if any(self._text(r, c) for c in range(1, self.table.columnCount())):
                    return f"Row {r + 1} has no code."
                continue
            if forbidden_in(code):
                return f"The code {code} contains {forbidden_in(code)}, which can't be in file names."
            if code in seen:
                return f"The code {code} is listed twice."
            seen.add(code)
            if not self.consent:
                email = self._text(r, self.col("email"))
                if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                    return f"{email} (for {code}) doesn't look like an email address."
        return ""


# --------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------

class LocationEditor(QWidget):
    """The hierarchy of places: name, code and a description of each."""

    def __init__(self, locations: list[Location], used, parent=None):
        super().__init__(parent)
        self.used = used
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Name", "Code", "Description"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for loc in locations:
            self.tree.addTopLevelItem(self._item(loc))
        self.tree.expandAll()
        self.tree.currentItemChanged.connect(lambda cur, prev: self._show(cur, prev))
        self.description = QPlainTextEdit()
        self.description.setPlaceholderText("Description of the selected place")
        self.description.setMaximumHeight(110)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.tree)
        split.addWidget(self.description)
        split.setSizes([400, 110])
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        row.addWidget(_tool("add", "Add a place next to the selected one", self._add, "Add place"))
        row.addWidget(_tool("add", "Add a place inside the selected one (a village in a region)",
                            self._add_inside, "Add place inside"))
        row.addWidget(_tool("delete", "Remove the selected place (and the places in it)", self._remove))
        row.addWidget(_tool("up", "Move up", lambda: self._shift(-1)))
        row.addWidget(_tool("down", "Move down", lambda: self._shift(1)))
        row.addStretch(1)
        lay.addLayout(row)
        self._current = None

    def load(self, locations: list[Location]):
        """Show these places instead (Reset to defaults)."""
        self.tree.blockSignals(True)
        self.tree.clear()
        for loc in locations:
            self.tree.addTopLevelItem(self._item(loc))
        self.tree.expandAll()
        self.tree.blockSignals(False)
        self.description.setPlainText("")
        self.description.setEnabled(False)

    def _item(self, loc: Location) -> QTreeWidgetItem:
        it = QTreeWidgetItem([loc.name, loc.code, _one_line(loc.description)])
        it.setFlags(it.flags() | Qt.ItemIsEditable)
        it.setData(0, ORIGINAL, loc.key)
        it.setData(2, Qt.UserRole, loc.description)
        it.setToolTip(2, loc.description)
        for c in loc.children:
            it.addChild(self._item(c))
        return it

    def _store_description(self, it):
        if it is not None:
            text = nfc(self.description.toPlainText().strip())
            it.setData(2, Qt.UserRole, text)
            it.setText(2, _one_line(text))
            it.setToolTip(2, text)

    def _show(self, cur, prev):
        self._store_description(prev)
        self.description.setPlainText(cur.data(2, Qt.UserRole) or "" if cur else "")
        self.description.setEnabled(cur is not None)

    def _add(self, inside: bool = False):
        cur = self.tree.currentItem()
        self._store_description(cur)
        it = self._item(Location("New place"))
        it.setData(0, ORIGINAL, "")
        if inside and cur is not None:
            cur.addChild(it)
            cur.setExpanded(True)
        elif cur is not None and cur.parent() is not None:
            cur.parent().insertChild(cur.parent().indexOfChild(cur) + 1, it)
        elif cur is not None:
            self.tree.insertTopLevelItem(self.tree.indexOfTopLevelItem(cur) + 1, it)
        else:
            self.tree.addTopLevelItem(it)
        self.tree.setCurrentItem(it)
        self.tree.editItem(it, 0)

    def _add_inside(self):
        self._add(inside=True)

    def _keys_under(self, it) -> list[str]:
        out = [it.data(0, ORIGINAL)] if it.data(0, ORIGINAL) else []
        for i in range(it.childCount()):
            out += self._keys_under(it.child(i))
        return out

    def _remove(self):
        cur = self.tree.currentItem()
        if cur is None:
            return
        n = sum(self.used(k) for k in self._keys_under(cur))
        if n and QMessageBox.question(self, "Remove", f"{cur.text(0)} (or a place in it) is in {n} "
                                      "notebook session(s), which keep it.\n\nRemove it from the list "
                                      "anyway?") != QMessageBox.Yes:
            return
        self._current = None
        (cur.parent() or self.tree.invisibleRootItem()).removeChild(cur)

    def _shift(self, step):
        cur = self.tree.currentItem()
        if cur is None:
            return
        parent = cur.parent() or self.tree.invisibleRootItem()
        i = parent.indexOfChild(cur)
        j = i + step
        if 0 <= j < parent.childCount():
            expanded = cur.isExpanded()
            parent.takeChild(i)
            parent.insertChild(j, cur)
            cur.setExpanded(expanded)
            self.tree.setCurrentItem(cur)

    def _read(self, it) -> Location:
        return Location(nfc(it.text(0).strip()), nfc(it.text(1).strip()), it.data(2, Qt.UserRole) or "",
                        [self._read(it.child(i)) for i in range(it.childCount())])

    def locations(self) -> list[Location]:
        self._store_description(self.tree.currentItem())
        return [self._read(self.tree.topLevelItem(i)) for i in range(self.tree.topLevelItemCount())]

    def _all_items(self):
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            it = stack.pop(0)
            yield it
            stack = [it.child(i) for i in range(it.childCount())] + stack

    def renames(self) -> dict[str, str]:
        out = {}
        for it in self._all_items():
            old = it.data(0, ORIGINAL) or ""
            new = nfc(it.text(1).strip()) or nfc(it.text(0).strip())
            if old and new and old != new:
                out[old] = new
        return out

    def problem(self) -> str:
        seen = set()
        for it in self._all_items():
            name, code = it.text(0).strip(), it.text(1).strip()
            if not name:
                return "Every place needs a name."
            key = code or name
            if key in seen:
                return (f"Two places are called {key}. Give one of them a code "
                        "(sessions keep a place's code, or its name if it has none).")
            seen.add(key)
        return ""


# --------------------------------------------------------------------------
# Reference categories
# --------------------------------------------------------------------------

REFS = "references"


class CategoryEditor(QWidget):
    """The reference categories: letter, name, what they're for (lemmas or utterances), numbering.

    A letter that references use can't be changed or removed, and can't move between lemmas
    and utterances: references are part of file names."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Letter", "Name", "For", "Numbering"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        for c in db.settings.ref_categories:
            self._add_row(c)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, 320)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(_tool("add", "Add a category", lambda: self._add_row(RefCategory("", ""), edit=True)))
        row.addWidget(_tool("delete", "Remove the selected category", self._remove))
        row.addWidget(_tool("up", "Move up", lambda: self._shift(-1)))
        row.addWidget(_tool("down", "Move down", lambda: self._shift(1)))
        row.addStretch(1)
        lay.addLayout(row)

    def used(self, letter: str) -> int:
        """How many lemmas and utterances have references in this category."""
        if not letter:
            return 0
        return sum(1 for item in self.db.items() if item.ref.startswith(letter))   # QQ01 is a Q

    def load(self, categories: list[RefCategory]):
        """Show these categories instead (Reset to defaults)."""
        self.table.setRowCount(0)
        for c in categories:
            self._add_row(c)

    def _add_row(self, c: RefCategory, edit: bool = False):
        r = self.table.rowCount()
        self.table.insertRow(r)
        letter = QTableWidgetItem(c.letter)
        n = self.used(c.letter)
        if n:
            letter.setFlags(letter.flags() & ~Qt.ItemIsEditable)
            letter.setToolTip(f"Used by {n} reference(s), so the letter can't change: references are part "
                              "of file names")
        letter.setData(ORIGINAL, c.letter)
        self.table.setItem(r, 0, letter)
        self.table.setItem(r, 1, QTableWidgetItem(c.name))
        kind = QComboBox()
        kind.addItem("Lemmas", LEMMAS)
        kind.addItem("Utterances", UTTERANCES)
        kind.addItem("Texts", TEXTS)
        kind.setCurrentIndex(max(0, kind.findData(c.kind)))
        kind.setEnabled(not n)
        if n:
            kind.setToolTip("In use, so it stays as it is")
        self.table.setCellWidget(r, 2, kind)
        numbering = QComboBox()
        numbering.addItem("automatic", "auto")
        numbering.addItem("by hand", "manual")
        numbering.setCurrentIndex(max(0, numbering.findData(c.numbering)))
        self.table.setCellWidget(r, 3, numbering)
        if edit:
            self.table.setCurrentCell(r, 0)
            self.table.editItem(letter)

    def _text(self, r, c) -> str:
        it = self.table.item(r, c)
        return nfc(it.text().strip()) if it else ""

    def _remove(self):
        r = self.table.currentRow()
        if r < 0:
            return
        original = self.table.item(r, 0).data(ORIGINAL) or ""
        n = self.used(original)
        if n:
            QMessageBox.information(self, "Remove", f"{original} is used by {n} reference(s), so it stays.")
            return
        self.table.removeRow(r)

    def _shift(self, step):
        r = self.table.currentRow()
        j = r + step
        if r < 0 or not 0 <= j < self.table.rowCount():
            return
        cats = self.categories()
        originals = [self.table.item(i, 0).data(ORIGINAL) for i in range(self.table.rowCount())]
        cats[r], cats[j] = cats[j], cats[r]
        originals[r], originals[j] = originals[j], originals[r]
        self.table.setRowCount(0)
        for c, o in zip(cats, originals):
            self._add_row(c)
            self.table.item(self.table.rowCount() - 1, 0).setData(ORIGINAL, o)
        self.table.setCurrentCell(j, 0)

    def categories(self) -> list[RefCategory]:
        out = []
        for r in range(self.table.rowCount()):
            kind, numbering = self.table.cellWidget(r, 2), self.table.cellWidget(r, 3)
            out.append(RefCategory(self._text(r, 0), self._text(r, 1), numbering.currentData(),
                                   kind.currentData()))
        return out

    def problem(self) -> str:
        seen = set()
        for c in self.categories():
            if not c.letter:
                return "Every category needs a letter."
            if not c.letter.isalpha() or not c.letter.isascii():
                return f"“{c.letter}”: a category's letters must be A–Z."
            if c.letter in seen:
                return f"Two categories have the letter {c.letter}."
            seen.add(c.letter)
        letters = sorted(seen, key=len, reverse=True)
        for a in letters:                         # QQ would read as Q followed by Q…
            for b in letters:
                if a != b and a.startswith(b):
                    return f"{a} starts with {b}, so their references couldn't be told apart."
        return ""


TIERS = "tiers"


class TierEditor(QWidget):
    """The database's tier mapping: tier name, the field it fills in, which tier is the main one."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Tier", "Fills in", "Main"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        m = db.settings.tier_mapping
        for r in m.rules:
            self._add_row(r, m.is_main(r.tier))
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(_tool("add", "Add a tier", lambda: self._add_row(TierRule(""), False, edit=True)))
        row.addWidget(_tool("delete", "Remove the selected tier", self._remove))
        row.addStretch(1)
        lay.addLayout(row)

    def load(self, mapping: TierMapping):
        """Show this mapping instead (Reset to defaults)."""
        self.table.setRowCount(0)
        for r in mapping.rules:
            self._add_row(r, mapping.is_main(r.tier))

    def _add_row(self, rule: TierRule, main: bool, edit: bool = False):
        from .texts import field_choices
        from PySide6.QtWidgets import QRadioButton
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(rule.tier))
        combo = QComboBox()
        choices = field_choices(self.db)
        for label, f, lang in choices:
            combo.addItem(label, (f, lang))
        i = next((k for k, (_, f, lang) in enumerate(choices) if (f, lang) == (rule.field, rule.lang)), 0)
        combo.setCurrentIndex(i)
        self.table.setCellWidget(r, 1, combo)
        rb = QRadioButton()
        rb.setChecked(main)
        rb.setAutoExclusive(False)
        rb.toggled.connect(lambda on, rb=rb: on and self._only_main(rb))
        self.table.setCellWidget(r, 2, rb)
        if edit:
            self.table.setCurrentCell(r, 0)
            self.table.editItem(self.table.item(r, 0))

    def _only_main(self, keep):
        for r in range(self.table.rowCount()):
            rb = self.table.cellWidget(r, 2)
            if rb is not keep and rb.isChecked():
                rb.blockSignals(True)
                rb.setChecked(False)
                rb.blockSignals(False)

    def _remove(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def mapping(self) -> TierMapping:
        m = TierMapping(self.db.settings.tier_mapping.main, [])
        for r in range(self.table.rowCount()):
            name = nfc((self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip())
            if not name:
                continue
            f, lang = self.table.cellWidget(r, 1).currentData()
            m.rules.append(TierRule(name, f, lang))
            if self.table.cellWidget(r, 2).isChecked():
                m.main = name
        return m

    def problem(self) -> str:
        names = [r.tier.lower() for r in self.mapping().rules]
        if len(names) != len(set(names)):
            return "Two tier rules have the same name."
        if names and not any(self.table.cellWidget(r, 2).isChecked() for r in range(self.table.rowCount())):
            return "Choose the main tier: its intervals are a text's lines."
        if any("@" in n for n in names):
            return "Give the tier's name without @speaker: tx stands for tx@SP1, tx@SP2…"
        return ""


def _one_line(text: str, n: int = 80) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n] + "…"


# --------------------------------------------------------------------------
# The dialogue
# --------------------------------------------------------------------------

class ListsDialog(QDialog):
    def __init__(self, parent, db: Database, notebook, start: str | None = None):
        super().__init__(parent)
        self.db, self.notebook = db, notebook
        self.setWindowTitle("Lists")
        self.resize(1080, 700)
        lay = QVBoxLayout(self)
        body = QHBoxLayout()
        lay.addLayout(body, 1)
        self.index = QListWidget()
        self.index.setMaximumWidth(220)
        self.pages = QStackedWidget()
        body.addWidget(self.index)
        body.addWidget(self.pages, 1)
        self.keys: dict[str, int] = {}          # page key -> row in the index

        md = db.metadata
        self._heading("People and places")
        self.researchers = PeopleEditor(db, md.researchers, False, self._researcher_use)
        self._page(RESEARCHERS, "Researchers", self.researchers,
                   "The researchers of the sessions. The code is what the notebook and the Current "
                   "Session show; renaming a code renames it in the notebook too. The email is where "
                   "ɛλicit requests tell a researcher their recordings have come in (the anonymous "
                   "backup always takes it out).",
                   lambda: self._reset_people(self.researchers, defaults.default_researchers(),
                                              self._researcher_use))
        self.participants = PeopleEditor(db, md.participants, True, self._participant_use)
        self._page(PARTICIPANTS, "Participants", self.participants,
                   "The participants (speakers). The code is the tokens' speaker; renaming it renames it "
                   "in the tokens and the notebook too. The consent file documents their informed consent: "
                   "click it to open it (a file inside the database's folder is kept relative to it). "
                   "Tick Identifiable? and Audio sharing? only when the consent form explicitly agrees "
                   "to them: ɛλicit warns before sending a recording whose speaker hasn't agreed to "
                   "audio sharing.",
                   lambda: self._reset_people(self.participants, defaults.default_participants(),
                                              self._participant_use))
        self.locations = LocationEditor(md.locations, self._location_use)
        self._page(LOCATIONS, "Locations", self.locations,
                   "Places, from countries down to villages. Double-click a name or code to edit it; "
                   "sessions keep a place's code (or its name, if it has no code).", self._reset_locations)

        self.categories = CategoryEditor(db)
        self._page(REFS, "Reference categories", self.categories,
                   "The letters references start with, and what each is for: lemmas, or utterances "
                   "(one-off sentences and phrases, View → Texts and utterances). A letter in use stays "
                   "as it is, since references are part of file names; its name can be changed.\n\n"
                   + defaults.DIXON_NOTE, self._reset_categories)

        self._heading("Field lists")
        self.field_lists = []
        self.class_list = None                  # the Word Class list's editor
        s = db.settings
        for kind, fields in (("lemma", s.entry_fields), ("token", s.token_fields), ("text", s.text_fields)):
            for f in fields:
                if not f.closed:
                    continue
                ed = ListEditor()
                ed.set_items(f.items)
                self.field_lists.append((f, ed))
                note = f"The values of the {kind} field {f.title}. Values can be nested."
                if f.role == "word-class":
                    self.class_list = ed
                    note += (" Tag groups can be marked as usual for word classes (under Tags); a class "
                             "includes those nested under it. Renaming a class renames it in the lemmas "
                             "and the tag groups.")
                self._page(f"field:{f.name}", f.title, ed, note,
                           lambda f=f, ed=ed: self._reset_field(f, ed))

        self._heading("Texts")
        self.tier_editor = TierEditor(db)
        self._page(TIERS, "Tier mapping", self.tier_editor,
                   "What each tier of a text's Praat TextGrid fills in, by the tier's name (a name like "
                   "tx@SP1 counts as tx, said by SP1). The main tier's intervals are the lines; the other "
                   "tiers are matched to them by time. A text can have its own mapping (chosen in its "
                   "dialogue); new tier names are learned when a text is added.", self._reset_tiers)

        self._heading("Tags")
        self.tags = TagStructureDialog(
            self, db, (lambda: self.class_list.items()) if self.class_list is not None else None)
        if self.class_list is not None:
            self._class_names = {}
            self.class_list.changed = self._classes_changed
        self.tags.setWindowFlags(Qt.Widget)
        self.tags.button_box.hide()
        self._page(TAGS, "Tag structure", self.tags, "", self._reset_tags)

        self.index.currentRowChanged.connect(self._row_changed)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.show_page(start or RESEARCHERS)

    # ---- pages -----------------------------------------------------------
    def _heading(self, text):
        it = QListWidgetItem(text)
        f = QFont(self.index.font())
        f.setBold(True)
        it.setFont(f)
        it.setFlags(Qt.NoItemFlags)
        self.index.addItem(it)

    def _page(self, key, title, widget, note, reset=None):
        page = QWidget()
        pl = QVBoxLayout(page)
        head = QLabel(title)
        f = QFont(head.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.3)
        head.setFont(f)
        top = QHBoxLayout()
        top.addWidget(head)
        top.addStretch(1)
        if reset is not None:
            top.addWidget(_tool("reset-filters", f"Put the default {title.lower()} back. Anything still in "
                                "use is kept; nothing changes until you click OK.",
                                lambda: self._reset(title, reset), "Reset to defaults"))
        pl.addLayout(top)
        if note:
            pl.addWidget(_note(note))
        pl.addWidget(widget, 1)
        self.pages.addWidget(page)
        it = QListWidgetItem("   " + title)
        it.setData(Qt.UserRole, self.pages.count() - 1)
        self.index.addItem(it)
        self.keys[key] = self.index.count() - 1

    def _reset(self, title, fn):
        """Reset one list to the defaults of a new database, keeping what's in use."""
        from .widgets import ask
        if not ask(self, "Reset to defaults",
                   f"Replace the {title.lower()} with the defaults?\n\nAnything still in use is kept. "
                   "The reset is only kept if you then click OK in Lists; Cancel there leaves everything "
                   "as it was.", "Reset to defaults"):
            return
        kept = fn() or []
        if kept:
            QMessageBox.information(self, "Reset to defaults",
                                    "Kept because they're in use:\n" + ", ".join(kept))

    # ---- what Reset to defaults does on each page -------------------------------
    def _reset_people(self, editor, defaults, in_use):
        people, kept = resets.merge_people(defaults, editor.people(), in_use)
        editor.load(people)
        return kept

    def _reset_locations(self):
        places, kept = resets.merge_locations(defaults.default_locations(), self.locations.locations(),
                                              self._location_use)
        self.locations.load(places)
        return kept

    def _reset_categories(self):
        cats, kept = resets.merge_categories(defaults.default_settings().ref_categories,
                                             self.categories.categories(), self.categories.used)
        self.categories.load(cats)
        return kept

    def _reset_field(self, f, editor):
        want = next((d for d in self._default_fields() if d.name == f.name), None)
        used = self._values_in_use(f)
        items, kept = resets.merge_items(want.items if want else [], editor.items(), used)
        editor.set_items(items)
        editor.changed()
        return kept

    def _default_fields(self):
        d = defaults.default_settings()
        return d.entry_fields + d.token_fields + d.text_fields

    def _values_in_use(self, f) -> set[str]:
        out = set()
        for e in self.db.items():
            out.add(e.get(f.name))
            for t in e.tokens:
                out.add(t.get(f.name))
        for t in self.db.texts:
            out.add(t.get(f.name))
        return {v for v in out if v}

    def _reset_tiers(self):
        self.tier_editor.load(defaults.tier_mapping())
        return []

    def _reset_tags(self):
        used = {x for _, t in self.db.all_tokens() for x in t.tags}
        ts, kept = resets.merge_tags(defaults.default_tag_structure(), self.tags.structure(), used)
        self.tags.load(ts)
        return kept

    def _row_changed(self, row):
        it = self.index.item(row)
        if it is not None and it.data(Qt.UserRole) is not None:
            self.pages.setCurrentIndex(it.data(Qt.UserRole))

    def _classes_changed(self):
        """The Word Class list was edited: the tag editor's hints follow renamed classes."""
        now = self.class_list.renames()
        delta = {}
        for orig, new in now.items():
            before = self._class_names.get(orig, orig)
            if before != new:
                delta[before] = new
        for orig, before in self._class_names.items():
            if orig not in now and before != orig:      # renamed back
                delta[before] = orig
        self._class_names = now
        self.tags.rename_classes(delta)
        self.tags.refresh_usual()

    def value_renames(self) -> dict[str, dict[str, str]]:
        """Values renamed in the closed fields' lists: field name -> {old: new}."""
        return {f.name: ed.renames() for f, ed in self.field_lists if ed.renames()}

    def show_page(self, key: str):
        row = self.keys.get(key, self.keys.get(RESEARCHERS))
        self.index.setCurrentRow(row)

    # ---- how much things are used -----------------------------------------
    def _sessions_with(self, attr, code) -> int:
        return sum(1 for s in self.notebook.sessions if code in getattr(s, attr))

    def _researcher_use(self, code) -> str:
        n = self._sessions_with("researchers", code)
        return f"in {n} notebook session(s)" if n else ""

    def _participant_use(self, code) -> str:
        tokens = sum(1 for _, t in self.db.all_tokens() if t.speaker == code) + \
            sum(1 for t in self.db.texts if code in t.participants)
        n = self._sessions_with("participants", code)
        parts = ([f"the speaker of {tokens} token(s)"] if tokens else []) + \
            ([f"in {n} notebook session(s)"] if n else [])
        return " and ".join(parts)

    def _location_use(self, key) -> int:
        return self._sessions_with("locations", key)

    # ---- result ------------------------------------------------------------
    def accept(self):
        for key, ed in ((RESEARCHERS, self.researchers), (PARTICIPANTS, self.participants),
                        (LOCATIONS, self.locations)):
            if (problem := ed.problem()):
                self.show_page(key)
                QMessageBox.warning(self, "Lists", problem)
                return
        if (problem := self.categories.problem()):
            self.show_page(REFS)
            QMessageBox.warning(self, "Lists", problem)
            return
        if (problem := self.tier_editor.problem()):
            self.show_page(TIERS)
            QMessageBox.warning(self, "Lists", problem)
            return
        if not self.tags.validate():
            self.show_page(TAGS)
            return
        super().accept()

    def apply(self) -> dict:
        """Put the lists into the database; returns the renames to follow elsewhere."""
        md = self.db.metadata
        md.researchers = self.researchers.people()
        md.participants = self.participants.people()
        md.locations = self.locations.locations()
        for f, ed in self.field_lists:
            f.items = ed.items()
        self.db.settings.ref_categories = self.categories.categories()
        self.db.settings.tier_mapping = self.tier_editor.mapping()
        return {RESEARCHERS: self.researchers.renames(), PARTICIPANTS: self.participants.renames(),
                LOCATIONS: self.locations.renames()}
