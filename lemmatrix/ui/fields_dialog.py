# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Edit → Fields: lemma, token and text fields, open or closed, with a live XML preview."""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QRadioButton,
                               QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import storage
from ..model import Database, Entry, FieldDef, ListItem, Token, nfc
from . import theme
from .icons import icon

NAME_RX = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
RESERVED = {"token", "entry", "database", "metadata", "settings"}


def _tool(name, tip, fn):
    b = QToolButton()
    b.setIcon(icon(name, 20))
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.clicked.connect(lambda *_, fn=fn: fn())   # ignore the 'checked' flag
    return b


class ListEditor(QWidget):
    """Edit a closed field's (hierarchical) list."""

    def __init__(self, parent=None, flat: bool = False):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(QLabel("List"))
        head.addStretch(1)
        head.addWidget(_tool("add", "Add an item", self._add))
        sub = QToolButton()
        sub.setText("Add sub-item")
        sub.clicked.connect(self._add_sub)
        if not flat:                              # a flat list (Symbols) has no sub-items
            head.addWidget(sub)
        head.addWidget(_tool("delete", "Remove the selected item", self._remove))
        head.addWidget(_tool("up", "Move up", lambda: self._shift(-1)))
        head.addWidget(_tool("down", "Move down", lambda: self._shift(1)))
        lay.addLayout(head)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemChanged.connect(lambda *a: self.changed())
        lay.addWidget(self.tree)
        self.changed = lambda: None

    def _item(self, name, original: str = ""):
        it = QTreeWidgetItem([name])
        it.setFlags(it.flags() | Qt.ItemIsEditable)
        if original:
            it.setData(0, Qt.UserRole, original)      # the value when the list was opened
        return it

    def set_items(self, items: list[ListItem]):
        self.tree.blockSignals(True)
        self.tree.clear()

        def add(parent, node):
            it = self._item(node.name, node.name)
            if parent is None:
                self.tree.addTopLevelItem(it)
            else:
                parent.addChild(it)
            for c in node.children:
                add(it, c)
        for n in items:
            add(None, n)
        self.tree.expandAll()
        self.tree.blockSignals(False)

    def items(self) -> list[ListItem]:
        def read(it):
            return ListItem(nfc(it.text(0).strip()), [read(it.child(i)) for i in range(it.childCount())])
        return [read(self.tree.topLevelItem(i)) for i in range(self.tree.topLevelItemCount())
                if self.tree.topLevelItem(i).text(0).strip()]

    def renames(self) -> dict[str, str]:
        """Values renamed since the list was opened: old -> new."""
        out = {}

        def walk(it):
            old, new = it.data(0, Qt.UserRole), nfc(it.text(0).strip())
            if old and new and old != new:
                out[old] = new
            for i in range(it.childCount()):
                walk(it.child(i))
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out

    def _add(self):
        name, ok = QInputDialog.getText(self, "Add item", "Value:")
        if ok and name.strip():
            cur = self.tree.currentItem()
            it = self._item(name.strip())
            if cur and cur.parent():
                cur.parent().addChild(it)
            else:
                self.tree.addTopLevelItem(it)
            self.tree.setCurrentItem(it)
            self.changed()

    def _add_sub(self):
        cur = self.tree.currentItem()
        if cur is None:
            return self._add()
        name, ok = QInputDialog.getText(self, "Add sub-item", f"Value under “{cur.text(0)}”:")
        if ok and name.strip():
            it = self._item(name.strip())
            cur.addChild(it)
            cur.setExpanded(True)
            self.tree.setCurrentItem(it)
            self.changed()

    def _remove(self):
        cur = self.tree.currentItem()
        if cur is None:
            return
        (cur.parent() or self.tree.invisibleRootItem()).removeChild(cur)
        self.changed()

    def _shift(self, step):
        cur = self.tree.currentItem()
        if cur is None:
            return
        parent = cur.parent() or self.tree.invisibleRootItem()
        i = parent.indexOfChild(cur)
        j = i + step
        if 0 <= j < parent.childCount():
            parent.takeChild(i)
            parent.insertChild(j, cur)
            self.tree.setCurrentItem(cur)
            self.changed()


class FieldsDialog(QDialog):
    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Fields")
        self.setWindowIcon(icon("gear"))
        self.resize(1180, 640)
        s = db.settings
        self.lists = {"lemma": copy.deepcopy(s.entry_fields), "token": copy.deepcopy(s.token_fields),
                      "text": copy.deepcopy(s.text_fields)}
        from .. import fieldkeys
        for kind in self.lists:                      # remember original names to follow renames
            for f in self.lists[kind]:
                f._orig = f.name
                f._keys = fieldkeys.keys(f)          # what it answered to when the dialogue opened
        from .dialogs import ALWAYS_SHOWN, more_fields
        self._always = ALWAYS_SHOWN
        under = more_fields(parent, db)              # the lemma dialogue's More arrow (idea 60)
        for f in self.lists["lemma"]:
            f._more = f.name in under
        self.current: tuple[str, int] | None = None

        outer = QHBoxLayout(self)
        left = QVBoxLayout()
        self.widgets = {}
        self.delete_buttons = {}
        for kind, title in (("lemma", "Lemma fields"), ("token", "Token fields"), ("text", "Text fields")):
            box = QGroupBox(title)
            bl = QVBoxLayout(box)
            head = QHBoxLayout()
            head.addStretch(1)
            head.addWidget(_tool("add", f"Add a {kind} field", lambda k=kind: self._add(k)))
            delete = _tool("delete", "Delete the selected field", lambda k=kind: self._delete(k))
            self.delete_buttons[kind] = delete
            head.addWidget(delete)
            head.addWidget(_tool("up", "Move up", lambda k=kind: self._shift(k, -1)))
            head.addWidget(_tool("down", "Move down", lambda k=kind: self._shift(k, 1)))
            bl.addLayout(head)
            lw = QListWidget()
            lw.currentRowChanged.connect(lambda r, k=kind: self._select(k, r))
            bl.addWidget(lw)
            self.widgets[kind] = lw
            left.addWidget(box)
        outer.addLayout(left, 3)

        mid = QVBoxLayout()
        self.detail = QGroupBox("Field")
        form = QFormLayout(self.detail)
        self.label = QLineEdit()
        self.name = QLineEdit()
        self.name.setToolTip("The XML element name: letters, digits, _ . -; no spaces")
        self.abbr = QLineEdit()
        self.abbr.setMaxLength(12)
        self.abbr.setToolTip("A short name (pht for Phonetic), shown in the edit dialogues when Settings → "
                             "Display → Abbreviate field names is on, and usable in templates ({pht}). A "
                             "field answers to its name, label and abbreviation in any case, with or "
                             "without spaces, so no two fields may share one (Josh, 26 October)")
        self.problem = QLabel()                      # a name that would call another field, or bad characters
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet(f"color: {theme.colour('error').name()};")
        self.problem.hide()
        self.open_rb = QRadioButton("Open (free text)")
        self.closed_rb = QRadioButton("Closed (values from a list)")
        grp = QButtonGroup(self)
        grp.addButton(self.open_rb)
        grp.addButton(self.closed_rb)
        type_row = QHBoxLayout()
        type_row.addWidget(self.open_rb)
        type_row.addWidget(self.closed_rb)
        tw = QWidget()
        tw.setLayout(type_row)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color: {theme.muted()};")
        self.list_editor = ListEditor()
        self.more_cb = QCheckBox("Under More in the lemma dialogue")
        self.more_cb.setToolTip("Behind the lemma dialogue's More arrow, so the dialogue shows only "
                                "the fields you fill in most (Lemma, Gloss and Word Class are always shown)")
        self.more_cb.toggled.connect(self._more_toggled)
        form.addRow("Label", self.label)
        form.addRow("Element name", self.name)
        form.addRow("Abbreviation", self.abbr)
        form.addRow(self.problem)
        form.addRow("Type", tw)
        form.addRow("", self.more_cb)
        form.addRow(self.note)
        form.addRow(self.list_editor)
        mid.addWidget(self.detail)
        outer.addLayout(mid, 3)

        right = QVBoxLayout()
        right.addWidget(QLabel("Example entry in the database file"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(9)
        self.preview.setFont(mono)
        right.addWidget(self.preview, 1)
        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        right.addWidget(b)
        outer.addLayout(right, 4)

        self.label.textEdited.connect(self._edited)
        self.name.textEdited.connect(self._edited)
        self.abbr.textEdited.connect(self._edited)
        self.open_rb.toggled.connect(self._edited)
        self.list_editor.changed = self._edited
        for kind in self.lists:
            self._fill(kind)
        self.widgets["lemma"].setCurrentRow(0)
        self._preview()

    # ---- lists -----------------------------------------------------------
    def _describe(self, f: FieldDef) -> str:
        bits = ["closed" if f.closed else "open"]
        if f.builtin:
            bits.append("built in")
        return f"{f.title}   ({f.name}{'; ' + f.abbr if f.abbr else ''}; {', '.join(bits)})"

    def _fill(self, kind):
        lw = self.widgets[kind]
        r = lw.currentRow()
        lw.blockSignals(True)
        lw.clear()
        for f in self.lists[kind]:
            lw.addItem(QListWidgetItem(self._describe(f)))
        lw.blockSignals(False)
        if 0 <= r < lw.count():
            lw.setCurrentRow(r)

    def _select(self, kind, row):
        if row < 0:
            return
        for other in self.widgets:
            if other == kind:
                continue
            self.widgets[other].blockSignals(True)
            self.widgets[other].clearSelection()
            self.widgets[other].setCurrentRow(-1)
            self.widgets[other].blockSignals(False)
        self.current = (kind, row)
        f = self.lists[kind][row]
        b = self.delete_buttons[kind]
        b.setEnabled(not f.builtin)
        b.setToolTip(f"{f.title} is needed by Lemmatrix: it can be renamed or moved, but not deleted"
                     if f.builtin else "Delete the selected field")
        self.detail.setTitle(f"{kind.capitalize()} field: {f.title}")
        for w in (self.label, self.name, self.abbr, self.open_rb, self.closed_rb):
            w.blockSignals(True)
        self.label.setText(f.label)
        self.name.setText(f.name)
        self.abbr.setText(f.abbr)
        self.open_rb.setChecked(not f.closed)
        self.closed_rb.setChecked(f.closed)
        for w in (self.label, self.name, self.abbr, self.open_rb, self.closed_rb):
            w.blockSignals(False)
        self._show_problem(kind, f)
        self.more_cb.blockSignals(True)
        self.more_cb.setVisible(kind == "lemma")
        self.more_cb.setEnabled(f.role not in self._always)
        self.more_cb.setChecked(bool(getattr(f, "_more", f.role not in self._always)))
        self.more_cb.blockSignals(False)
        fixed_type = f.builtin
        self.open_rb.setEnabled(not fixed_type)
        self.closed_rb.setEnabled(not fixed_type)
        self.name.setReadOnly(f.builtin)
        if f.role == "word-class":
            self.note.setText("Word Class is built in and always closed. Its list of word classes is "
                              "in Edit → Lists → Field lists → Word Class.")
            self.list_editor.setVisible(False)
        else:
            self.note.setText("Needed by Lemmatrix: it can be renamed (Label) and moved, but not deleted."
                              if f.builtin else "")
            self.list_editor.setVisible(f.closed)
            if f.closed and not f.items:
                self._fill_from_data(kind, f)
            self.list_editor.set_items(f.items)

    def _more_toggled(self, on: bool):
        if self.current and self.current[0] == "lemma":
            self.lists["lemma"][self.current[1]]._more = bool(on)

    def more_names(self) -> list[str]:
        """The lemma fields behind the More arrow, as they are named now (new fields: yes)."""
        return [f.name for f in self.lists["lemma"]
                if f.role not in self._always and getattr(f, "_more", True)]

    def _fill_from_data(self, kind, f):
        """Start an empty list from the values already in the data."""
        name = getattr(f, "_orig", None) or f.name
        if kind == "lemma":
            vals = {e.get(name) for e in self.db.entries}
        elif kind == "text":
            vals = {t.get(name) for t in self.db.texts}
        else:
            vals = {t.get(name) for _, t in self.db.all_tokens()}     # utterances too
        f.items = [ListItem(v) for v in sorted(v for v in vals if v)]

    def _edited(self, *_):
        if not self.current:
            return
        kind, row = self.current
        f = self.lists[kind][row]
        f.label = self.label.text().strip()
        f.abbr = self.abbr.text().strip()
        if not f.builtin:
            f.name = self.name.text().strip()
            f.closed = self.closed_rb.isChecked()
        if f.role != "word-class":
            was_visible = self.list_editor.isVisible()
            self.list_editor.setVisible(f.closed)
            if f.closed and not was_visible and not f.items:
                self._fill_from_data(kind, f)
                self.list_editor.set_items(f.items)
            elif f.closed:
                f.items = self.list_editor.items()
        self.widgets[kind].item(row).setText(self._describe(f))
        self._show_problem(kind, f)
        self._preview()

    # ---- names that would call another field (ideas 72 and 73, Josh, 26 October) -----------
    def problem_for(self, kind, f) -> str:
        """Why a field's label, abbreviation or name can't be used, or ""."""
        from .. import fieldkeys
        for what, text in (("label", f.label), ("abbreviation", f.abbr)):
            bad = fieldkeys.label_problem(text)
            if bad:
                return (f"The {what} can't have {bad}: they are a template's own characters, or can't "
                        "be in file names.")
        return fieldkeys.clash(self.lists, kind, f, getattr(f, "_keys", set()))

    def _show_problem(self, kind, f):
        why = self.problem_for(kind, f)
        self.problem.setText(why)
        self.problem.setVisible(bool(why))

    def _add(self, kind):
        name, ok = QInputDialog.getText(self, "Add field", "Name (letters and digits, no spaces), "
                                                          "e.g. Syllables:")
        name = name.strip()
        if not ok or not name:
            return
        if not NAME_RX.match(name) or name.lower() in RESERVED:
            QMessageBox.warning(self, "Fields", f"“{name}” can't be used as a field name. Use letters, "
                                "digits and _ only, starting with a letter.")
            return
        closed = QMessageBox.question(self, "Add field", "Should this be a closed field, with its "
                                      "values chosen from a list?") == QMessageBox.Yes
        f = FieldDef(name, closed=closed)
        f._orig = None
        f._keys = set()
        from .. import fieldkeys
        why = fieldkeys.clash(self.lists, kind, f)
        if why:
            QMessageBox.warning(self, "Fields", why)
            return
        self.lists[kind].append(f)
        self._fill(kind)
        self.widgets[kind].setCurrentRow(len(self.lists[kind]) - 1)
        self._preview()

    def _delete(self, kind):
        lw = self.widgets[kind]
        r = lw.currentRow()
        if r < 0:
            return
        f = self.lists[kind][r]
        if f.builtin:
            QMessageBox.information(self, "Fields", f"{f.title} is built in and can't be deleted.")
            return
        if QMessageBox.question(self, "Delete field", f"Delete the field “{f.title}”? Data already in it "
                                "stays in the file but is no longer shown.") != QMessageBox.Yes:
            return
        del self.lists[kind][r]
        self._fill(kind)
        self._preview()

    def _shift(self, kind, step):
        lw = self.widgets[kind]
        r = lw.currentRow()
        L = self.lists[kind]
        if r < 0 or not 0 <= r + step < len(L):
            return
        L[r], L[r + step] = L[r + step], L[r]
        self._fill(kind)
        lw.setCurrentRow(r + step)
        self._preview()

    # ---- preview ---------------------------------------------------------
    def _preview(self):
        s = copy.deepcopy(self.db.settings)
        s.entry_fields = copy.deepcopy(self.lists["lemma"])
        s.token_fields = copy.deepcopy(self.lists["token"])
        db = Database(metadata=self.db.metadata, settings=s)
        e = Entry(ref="D001", file_gloss="Gloss")
        for f in s.entry_fields:
            if f.multilingual:
                for lang in s.gloss_languages:
                    e.multi.setdefault(f.name, {})[lang] = f"{f.name} ({lang})"
            else:
                value = f.name
                if f.closed:
                    vals = [i.name for i in s.list_items(f)] if f.role == "word-class" else f.all_values()
                    value = vals[0] if vals else f.name
                e.values[f.name] = value
        t = Token(tags=["Plural", "isolation"], speaker="SP1", collected="2026-10-16",
                  file="LXX-VXX_D001_Gloss_PL.wav")
        for f in s.token_fields:
            if f.multilingual:
                t.multi.setdefault(f.name, {})[s.primary_gloss] = f.name
            elif f.role == "pitch":
                t.values[f.name] = "1:42"
            else:
                t.values[f.name] = (f.all_values() or [f.name])[0] if f.closed else f.name
        e.tokens.append(t)
        db.entries.append(e)
        s.text_fields = copy.deepcopy(self.lists["text"])
        from ..model import Text
        tx = Text("T001", "Title", "2026-10-16", ["SP1"], ["JS"], [], "LXX-VXX_T001_Title.wav",
                  "LXX-VXX_T001_Title.TextGrid")
        for f in s.text_fields:
            tx.values[f.name] = (f.all_values() or [f.name])[0] if f.closed else f.name
        db.texts.append(tx)
        root = storage.to_element(db)
        out = []
        for path in ("entry", "texts/text"):
            el = root.find(path)
            ET.indent(el, space="  ")
            out.append(ET.tostring(el, encoding="unicode").strip())
        self.preview.setPlainText("\n\n".join(out))

    # ---- accept ----------------------------------------------------------
    def accept(self):
        for kind in self.lists:
            seen = set()
            for f in self.lists[kind]:
                if not NAME_RX.match(f.name) or f.name.lower() in RESERVED:
                    QMessageBox.warning(self, "Fields", f"“{f.name}” isn't a usable element name.")
                    return
                if f.name in seen:
                    QMessageBox.warning(self, "Fields", f"Two {kind} fields are called “{f.name}”.")
                    return
                seen.add(f.name)
                why = self.problem_for(kind, f)
                if why:
                    QMessageBox.warning(self, "Fields", f"{f.title}: {why}")
                    self.widgets[kind].setCurrentRow(self.lists[kind].index(f))
                    return
        super().accept()

    def apply(self):
        """Write the fields back, following renames in the data."""
        s = self.db.settings
        renames = {"lemma": {}, "token": {}, "text": {}}
        for kind in self.lists:
            for f in self.lists[kind]:
                orig = getattr(f, "_orig", None)
                if orig and orig != f.name:
                    renames[kind][orig] = f.name
                if hasattr(f, "_orig"):
                    del f._orig
                if hasattr(f, "_keys"):
                    del f._keys
        s.entry_fields = self.lists["lemma"]
        s.token_fields = self.lists["token"]
        s.text_fields = self.lists["text"]

        def move(obj, mapping):
            for old, new in mapping.items():
                if old in obj.values:
                    obj.values[new] = obj.values.pop(old)
                if old in obj.multi:
                    obj.multi[new] = obj.multi.pop(old)
                if old in obj.changed:                # a comment's date goes with it
                    obj.changed[new] = obj.changed.pop(old)
        for e in self.db.entries:
            move(e, renames["lemma"])
            for t in e.tokens:
                move(t, renames["token"])
        for u in self.db.utterances:                  # utterances have token fields only
            for t in u.tokens:
                move(t, renames["token"])
        for t in self.db.texts:
            move(t, renames["text"])
        for m in [s.tier_mapping] + [t.tiers for t in self.db.texts if t.tiers is not None]:
            for r in m.rules:                         # the tiers follow renamed token fields
                r.field = renames["token"].get(r.field, r.field)
        self.renames = renames                    # for the workspace to follow (the audit, 25 October)
        return bool(renames["lemma"] or renames["token"] or renames["text"])
