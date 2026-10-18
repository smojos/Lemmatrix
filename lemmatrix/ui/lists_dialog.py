"""Edit → Lists: every list in one place.

Researchers, participants (with the file documenting their consent), locations
(hierarchical, with codes and descriptions), the closed fields' lists (Tone Class,
Inflection Class, Word Class...), and the tag structure. Codes renamed here are followed
everywhere: token speakers and notebook sessions; renamed list values are followed in the
lemmas and tokens, and renamed word classes in the tag groups' "usual for" hints.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QSplitter, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ..model import Database, Location, Person, forbidden_in, nfc
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
    """Researchers or participants: code, name, description (and a consent file)."""

    def __init__(self, db: Database, people: list[Person], consent: bool, used, parent=None):
        super().__init__(parent)
        self.db, self.consent, self.used = db, consent, used
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        cols = ["Code", "Name", "Description"] + (["Consent file"] if consent else [])
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        for p in people:
            self._add_row(p)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, max(self.table.columnWidth(1), 200))
        self.table.setColumnWidth(2, min(max(self.table.columnWidth(2), 160), 260))
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

    def _add_row(self, p: Person, edit: bool = False):
        r = self.table.rowCount()
        self.table.insertRow(r)
        values = [p.code, p.name, p.description] + ([p.consent] if self.consent else [])
        for c, v in enumerate(values):
            it = self._consent_item(v) if c == 3 else QTableWidgetItem(v)
            if c == 2:
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
        if c == 3 and self._text(r, 3):
            self._open_consent()

    def _text(self, r, c) -> str:
        it = self.table.item(r, c)
        return nfc(it.text().strip()) if it else ""

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
        current = consent_path(self.db, self._text(r, 3))
        start = str(current) if current and current.exists() else (
            str(Path(self.db.path).parent) if self.db.path else str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(self, f"Consent documentation for {self._text(r, 0)}", start)
        if not path:
            return
        p = Path(path)
        if self.db.path:                       # inside the database's folder: stored relative to it
            try:
                p = p.relative_to(Path(self.db.path).parent)
            except ValueError:
                pass
        self.table.setItem(r, 3, self._consent_item(QDir.toNativeSeparators(str(p))))

    def _open_consent(self):
        r = self.table.currentRow()
        if r < 0:
            return
        path = consent_path(self.db, self._text(r, 3))
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
            if code:
                out.append(Person(code, self._text(r, 1), self._text(r, 2),
                                  self._text(r, 3) if self.consent else ""))
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
                   "Session show; renaming a code renames it in the notebook too.")
        self.participants = PeopleEditor(db, md.participants, True, self._participant_use)
        self._page(PARTICIPANTS, "Participants", self.participants,
                   "The participants (speakers). The code is the tokens' speaker; renaming it renames it "
                   "in the tokens and the notebook too. The consent file documents their informed consent: "
                   "click it to open it (a file inside the database's folder is kept relative to it).")
        self.locations = LocationEditor(md.locations, self._location_use)
        self._page(LOCATIONS, "Locations", self.locations,
                   "Places, from countries down to villages. Double-click a name or code to edit it; "
                   "sessions keep a place's code (or its name, if it has no code).")

        self._heading("Field lists")
        self.field_lists = []
        self.class_list = None                  # the Word Class list's editor
        s = db.settings
        for kind, fields in (("lemma", s.entry_fields), ("token", s.token_fields)):
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
                self._page(f"field:{f.name}", f.title, ed, note)

        self._heading("Tags")
        self.tags = TagStructureDialog(
            self, db, (lambda: self.class_list.items()) if self.class_list is not None else None)
        if self.class_list is not None:
            self._class_names = {}
            self.class_list.changed = self._classes_changed
        self.tags.setWindowFlags(Qt.Widget)
        self.tags.button_box.hide()
        self._page(TAGS, "Tag structure", self.tags, "")

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

    def _page(self, key, title, widget, note):
        page = QWidget()
        pl = QVBoxLayout(page)
        head = QLabel(title)
        f = QFont(head.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.3)
        head.setFont(f)
        pl.addWidget(head)
        if note:
            pl.addWidget(_note(note))
        pl.addWidget(widget, 1)
        self.pages.addWidget(page)
        it = QListWidgetItem("   " + title)
        it.setData(Qt.UserRole, self.pages.count() - 1)
        self.index.addItem(it)
        self.keys[key] = self.index.count() - 1

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
        tokens = sum(1 for e in self.db.entries for t in e.tokens if t.speaker == code)
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
        return {RESEARCHERS: self.researchers.renames(), PARTICIPANTS: self.participants.renames(),
                LOCATIONS: self.locations.renames()}
