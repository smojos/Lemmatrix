"""The tag conversion dialogue: what happens to the tags when lemmas change word class.

Opened whenever a word class change would leave tags behind: from bulk edit's Set value,
from the lemma list and from the entry dialogue. Each tag the tokens use gets a choice:

    Convert to   a tag of the new class (pre-set when the new class has a tag of that name)
    New tag      a tag made in the new class, with its code and group
    Delete       taken off the tokens

Tags open to every word class are kept as they are. Nothing is chosen for you otherwise,
so Continue only works once every tag has a choice. Choices can be saved by name
("VERB → NOUN (nominalisation)") for the next time.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QInputDialog,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from .. import bulk
from ..model import Conversion, Database, TagAction, nfc
from . import theme
from .dialogs import NoForbidden
from .icons import icon

CHOOSE, CONVERT, NEW, DELETE = 0, 1, 2, 3
KINDS = {CONVERT: bulk.CONVERT, NEW: bulk.NEW, DELETE: bulk.DELETE}


def _leaf_group_names(db: Database, wc: str) -> list[str]:
    w = db.settings.tags.word_class(wc)
    if w is None:
        return []
    names = []
    for top in w.groups:
        for _, g in top.leaf_groups():
            if g.name not in names:
                names.append(g.name)
        if top.name not in names:
            names.append(top.name)
    return names


class _RowWidgets:
    def __init__(self, dlg: "TagConversionDialog", s: bulk.Stranded):
        self.stranded = s
        db, new_wc = dlg.db, dlg.new_wc
        ts = db.settings.tags
        self.action = QComboBox()
        self.action.addItems(["Choose…", "Convert to", "New tag", "Delete"])
        if not new_wc:
            self.action.model().item(NEW).setEnabled(False)       # new tags need a word class
        self.stack = QStackedWidget()
        self.stack.addWidget(QLabel(""))
        self.target = QComboBox()
        for t, g in ts.tags_for(new_wc or None):
            self.target.addItem(f"{t.name}   ({g.name})", t.name)
        self.stack.addWidget(self.target)
        new = QWidget()
        nl = QHBoxLayout(new)
        nl.setContentsMargins(0, 0, 0, 0)
        old = ts.find(s.from_class or None, s.name)
        self.name = QLineEdit(s.name)
        self.name.setPlaceholderText("name")
        self.name.setToolTip("The new tag's name (no commas)")
        self.code = NoForbidden(old[0].code if old else "")
        self.code.setPlaceholderText("code")
        self.code.setToolTip("Its code in sound file names")
        self.code.setMaximumWidth(80)
        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItems(_leaf_group_names(db, new_wc))
        self.group.setCurrentText(s.group or "New tags")
        self.group.setToolTip(f"The group of {new_wc} it goes in; type a new name to make a group")
        self.group.setMinimumWidth(140)
        nl.addWidget(self.name, 3)
        nl.addWidget(self.code)
        nl.addWidget(QLabel("in"))
        nl.addWidget(self.group, 2)
        self.stack.addWidget(new)
        gone = QLabel("taken off the tokens")
        gone.setStyleSheet(f"color: {theme.muted()};")
        self.stack.addWidget(gone)
        self.action.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.action.currentIndexChanged.connect(lambda *_: dlg._check())
        self.target.currentIndexChanged.connect(lambda *_: dlg._check())
        for ed in (self.name, self.code):
            ed.textChanged.connect(lambda *_: dlg._check())
        self.group.currentTextChanged.connect(lambda *_: dlg._check())
        self.set(s.suggested)

    def set(self, a: TagAction | None):
        a = a or TagAction()
        idx = {bulk.CONVERT: CONVERT, bulk.NEW: NEW, bulk.DELETE: DELETE}.get(a.kind, CHOOSE)
        if a.kind == bulk.CONVERT:
            i = self.target.findData(a.tag)
            if i < 0:
                idx = CHOOSE
            else:
                self.target.setCurrentIndex(i)
        elif a.kind == bulk.NEW:
            self.name.setText(a.tag)
            self.code.setText(a.code)
            self.group.setCurrentText(a.group)
        self.action.setCurrentIndex(idx)
        self.stack.setCurrentIndex(idx)

    def get(self) -> TagAction:
        i = self.action.currentIndex()
        if i == CONVERT:
            return TagAction(bulk.CONVERT, self.target.currentData() or "")
        if i == NEW:
            return TagAction(bulk.NEW, nfc(self.name.text()).strip(), nfc(self.code.text()).strip(),
                             nfc(self.group.currentText()).strip())
        if i == DELETE:
            return TagAction(bulk.DELETE)
        return TagAction()


class TagConversionDialog(QDialog):
    def __init__(self, parent, db: Database, entries, new_wc: str, on_saved=None):
        super().__init__(parent)
        self.db, self.new_wc = db, new_wc
        self.on_saved = on_saved                  # called when the saved conversions change
        self.stranded, kept = bulk.stranded_tags(db, entries, new_wc)
        moving = [e for e in entries if db.word_class(e) != new_wc]
        self.from_classes = sorted({db.word_class(e) or "(none)" for e in moving})
        self.setWindowTitle("Convert tags")
        lay = QVBoxLayout(self)
        n = len(moving)
        head = QLabel(f"<b>{n} lemma{'s' if n != 1 else ''}</b> change from "
                      f"<b>{', '.join(self.from_classes)}</b> to <b>{new_wc or '(none)'}</b>. "
                      "Choose what happens to each tag their tokens use.")
        head.setWordWrap(True)
        lay.addWidget(head)

        saved = QHBoxLayout()
        saved.addWidget(QLabel("Saved conversion"))
        self.saved = QComboBox()
        self.saved.setMinimumWidth(220)
        self.saved.activated.connect(lambda i: self._load(i))
        saved.addWidget(self.saved, 1)
        b = QPushButton("Save conversion…")
        b.setToolTip("Save these choices under a name, to use them again")
        b.clicked.connect(lambda *_: self._save())
        saved.addWidget(b)
        d = QToolButton()
        d.setIcon(icon("delete", 18))
        d.setToolTip("Delete the chosen saved conversion")
        d.setAutoRaise(True)
        d.clicked.connect(lambda *_: self._delete())
        saved.addWidget(d)
        lay.addLayout(saved)

        self.table = QTableWidget(len(self.stranded), 5)
        self.table.setHorizontalHeaderLabels(["Tag", "From", "Tokens", "Action", "Becomes"])
        self.table.verticalHeader().hide()
        self.rows: list[_RowWidgets] = []
        for r, s in enumerate(self.stranded):
            w = _RowWidgets(self, s)
            self.rows.append(w)
            for c, text in enumerate((s.name, f"{s.from_class or '(none)'} › {s.group}" if s.group
                                      else s.from_class or "(none)", str(s.tokens))):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled)
                if c == 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)
            self.table.setCellWidget(r, 3, w.action)
            self.table.setCellWidget(r, 4, w.stack)
        hh = self.table.horizontalHeader()
        for c in range(4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        lay.addWidget(self.table, 1)

        if kept:
            k = QLabel("Kept as they are (open to every word class): "
                       + ", ".join(f"{name} ({count})" for name, count in kept.items()))
            k.setWordWrap(True)
            k.setStyleSheet(f"color: {theme.muted()};")
            lay.addWidget(k)
        note = QLabel("Tags the new class also has are pre-set to convert to it. Creating a new tag "
                      "adds it to the tag structure.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {theme.muted()};")
        lay.addWidget(note)
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setStyleSheet(f"color: {theme.colour('error_text').name()};")
        lay.addWidget(self.problems)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Continue")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self._fill_saved()
        self.resize(820, min(640, 260 + 34 * max(3, len(self.stranded))))
        self._check()

    # ---- choices -----------------------------------------------------
    def actions(self) -> dict[str, TagAction]:
        return {w.stranded.name: w.get() for w in self.rows}

    def problems_now(self) -> list[str]:
        return bulk.check_conversion(self.db, self.new_wc, self.actions(), self.stranded)

    def _check(self):
        msgs = self.problems_now()
        open_ = sum(1 for w in self.rows if w.action.currentIndex() == CHOOSE)
        shown = [m for m in msgs if not m.startswith("Choose what happens")]
        if open_:
            shown.insert(0, f"{open_} tag{'s' if open_ != 1 else ''} still need{'s' if open_ == 1 else ''} "
                            "a choice.")
        self.problems.setText("\n".join(shown[:6]))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not msgs)

    def accept(self):
        if self.problems_now():
            return
        super().accept()

    # ---- saved conversions ---------------------------------------------
    def _matching(self) -> list[Conversion]:
        return [c for c in self.db.settings.conversions if c.to_class == self.new_wc]

    def _fill_saved(self, select: str = ""):
        self.saved.clear()
        self.saved.addItem("(none)", "")
        for c in self._matching():
            self.saved.addItem(f"{c.name}   ({c.from_class or '(none)'} → {c.to_class or '(none)'})", c.name)
        if select:
            self.saved.setCurrentIndex(max(0, self.saved.findData(select)))

    def _load(self, i: int):
        name = self.saved.itemData(i)
        conv = next((c for c in self._matching() if c.name == name), None)
        if conv is None:
            return
        for w in self.rows:
            if w.stranded.name in conv.actions:
                w.set(conv.actions[w.stranded.name])
        self._check()

    def _save(self):
        default = self.saved.currentData() or f"{' + '.join(self.from_classes)} → {self.new_wc or '(none)'}"
        name, ok = QInputDialog.getText(self, "Save conversion", "Name:", text=default)
        name = nfc(name).strip()
        if not ok or not name:
            return
        convs = self.db.settings.conversions
        old = next((c for c in convs if c.name == name), None)
        actions = {k: v for k, v in self.actions().items() if v.kind}
        if old is not None:
            if QMessageBox.question(self, "Save conversion", f"Replace the saved conversion “{name}”?") \
                    != QMessageBox.Yes:
                return
            old.actions.update(actions)          # keeps choices for tags not in this change
            old.from_class, old.to_class = " + ".join(self.from_classes), self.new_wc
        else:
            convs.append(Conversion(name, " + ".join(self.from_classes), self.new_wc, actions))
        self._fill_saved(name)
        if self.on_saved:
            self.on_saved()

    def _delete(self):
        name = self.saved.currentData()
        if not name:
            return
        if QMessageBox.question(self, "Delete conversion", f"Delete the saved conversion “{name}”?") \
                != QMessageBox.Yes:
            return
        self.db.settings.conversions[:] = [c for c in self.db.settings.conversions if c.name != name]
        self._fill_saved()
        if self.on_saved:
            self.on_saved()
