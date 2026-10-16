"""Filter for…, Choose… and Configure columns dialogues (modelled on FLEx)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QDialog,
                               QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QRadioButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from .. import filters as fl
from ..model import ListItem
from .icons import icon
from .widgets import ipa_font


class FilterForDialog(QDialog):
    """“Filter for items containing…”: search box, where to match, case and diacritics."""

    def __init__(self, parent, title: str, current: fl.TextFilter | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Filter {title} for items containing…")
        self.resize(560, 190)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Enter text to search for:"))
        self.text = QLineEdit(current.text if current else "")
        self.text.setFont(ipa_font(13))
        lay.addWidget(self.text)
        grid = QGridLayout()
        self.group = QButtonGroup(self)
        modes = [("&Anywhere", fl.ANYWHERE, 0, 0), ("At &end", fl.END, 0, 1),
                 ("&Whole item", fl.WHOLE, 1, 0), ("At &start", fl.START, 1, 1),
                 ("Match for &regular expression", fl.REGEX, 2, 0)]
        self.radios = {}
        for text, mode, r, c in modes:
            rb = QRadioButton(text)
            self.group.addButton(rb)
            self.radios[mode] = rb
            grid.addWidget(rb, r, c, 1, 2 if mode == fl.REGEX else 1)
        self.radios[current.mode if current else fl.ANYWHERE].setChecked(True)
        self.case = QCheckBox("Match &case")
        self.case.setChecked(bool(current and current.match_case))
        self.diacritics = QCheckBox("Match &diacritics")
        self.diacritics.setChecked(bool(current and current.match_diacritics))
        self.diacritics.setToolTip("When off, accents and other combining marks are ignored, and so "
                                   "are modifier letters such as ʰ ʷ ʲ ː (so deet finds dɪɪtʰ).")
        grid.addWidget(self.case, 0, 2)
        grid.addWidget(self.diacritics, 1, 2)
        lay.addLayout(grid)
        self.error = QLabel()
        self.error.setStyleSheet("color: #c62828;")
        lay.addWidget(self.error)
        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        lay.addWidget(b)
        self.text.setFocus()

    def result_filter(self) -> fl.TextFilter:
        mode = next(m for m, rb in self.radios.items() if rb.isChecked())
        return fl.TextFilter(self.text.text(), mode, self.case.isChecked(), self.diacritics.isChecked())

    def accept(self):
        f = self.result_filter()
        if not f.text:
            self.error.setText("Type something to search for, or choose Show all.")
            return
        if f.mode == fl.REGEX:
            try:
                f.compiled()
            except Exception as exc:  # re.error
                self.error.setText(f"That regular expression isn't valid: {exc}")
                return
        super().accept()


class ChooseDialog(QDialog):
    """“Choose Items”: a checkable tree of a closed list (or the tag structure)."""

    def __init__(self, parent, title: str, tree: list[ListItem], counts: dict[str, int],
                 current: fl.ChoiceFilter | None = None, allow_exactly: bool = False):
        super().__init__(parent)
        self.setWindowTitle(f"Choose {title}")
        self.resize(420, 520)
        self.counts = counts
        selected = current.selected if current else set()
        lay = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self._items: list[QTreeWidgetItem] = []
        for node in tree:
            self.tree.addTopLevelItem(self._make(node, selected))
        self.tree.expandAll()
        self.tree.itemChanged.connect(self._changed)
        lay.addWidget(self.tree, 1)
        lay.addWidget(QLabel("Clicking a group's box ticks everything under it; "
                             "Ctrl-click ticks only that item."))
        self.usage = QCheckBox("Display usage figures")
        self.usage.toggled.connect(self._show_usage)
        lay.addWidget(self.usage)
        row = QHBoxLayout()
        self.any = QRadioButton("Any selected")
        self.exact = QRadioButton("Exactly selected")
        self.none = QRadioButton("No selected")
        self.exact.setToolTip("Only the exact combination of the ticked tags (group defaults don't count)")
        row.addWidget(self.any)
        if allow_exactly:
            row.addWidget(self.exact)
        row.addWidget(self.none)
        row.addStretch(1)
        mode = current.mode if current else fl.ANY
        {fl.ANY: self.any, fl.EXACTLY: self.exact, fl.NONE: self.none}[mode].setChecked(True)
        lay.addLayout(row)
        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        lay.addWidget(b)

    def _make(self, node: ListItem, selected) -> QTreeWidgetItem:
        it = QTreeWidgetItem([node.name])
        it.setData(0, Qt.UserRole, node.name)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(0, Qt.Checked if node.name in selected else Qt.Unchecked)
        self._items.append(it)
        for c in node.children:
            it.addChild(self._make(c, selected))
        return it

    def _changed(self, item, column):
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            return
        state = item.checkState(0)
        self.tree.blockSignals(True)
        stack = [item.child(i) for i in range(item.childCount())]
        while stack:
            c = stack.pop()
            c.setCheckState(0, state)
            stack.extend(c.child(i) for i in range(c.childCount()))
        self.tree.blockSignals(False)

    def _show_usage(self, on):
        self.tree.blockSignals(True)
        for it in self._items:
            name = it.data(0, Qt.UserRole)
            it.setText(0, f"{name}  ({self.counts.get(name, 0)})" if on else name)
        self.tree.blockSignals(False)

    def result_filter(self) -> fl.ChoiceFilter:
        sel = {it.data(0, Qt.UserRole) for it in self._items if it.checkState(0) == Qt.Checked}
        mode = fl.EXACTLY if self.exact.isChecked() else fl.NONE if self.none.isChecked() else fl.ANY
        return fl.ChoiceFilter(sel, mode)


class ConfigureColumnsDialog(QDialog):
    """Column options on the left, current columns on the right, Add / Remove, up / down."""

    def __init__(self, parent, all_columns: list[tuple[str, str]], current: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Configure Columns")
        self.setWindowIcon(icon("gear"))
        self.resize(720, 400)
        self.titles = dict(all_columns)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Column options"))
        self.options = QListWidget()
        left.addWidget(self.options)
        row.addLayout(left, 1)
        mid = QVBoxLayout()
        mid.addStretch(1)
        self.add_btn = QPushButton("Add >>")
        self.remove_btn = QPushButton("Remove")
        mid.addWidget(self.add_btn)
        mid.addWidget(self.remove_btn)
        mid.addStretch(1)
        row.addLayout(mid)
        right = QVBoxLayout()
        right.addWidget(QLabel("Current columns"))
        self.current = QListWidget()
        right.addWidget(self.current)
        row.addLayout(right, 1)
        arrows = QVBoxLayout()
        arrows.addStretch(1)
        self.up = QPushButton()
        self.up.setIcon(icon("up", 24))
        self.up.setToolTip("Move up")
        self.down = QPushButton()
        self.down.setIcon(icon("down", 24))
        self.down.setToolTip("Move down")
        arrows.addWidget(self.up)
        arrows.addWidget(self.down)
        arrows.addStretch(1)
        row.addLayout(arrows)
        lay.addLayout(row, 1)
        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        lay.addWidget(b)
        for key in current:
            if key in self.titles:
                self._add(self.current, key)
        for key, title in all_columns:
            if key not in current:
                self._add(self.options, key)
        self.add_btn.clicked.connect(self._move_right)
        self.remove_btn.clicked.connect(self._move_left)
        self.options.itemDoubleClicked.connect(lambda _: self._move_right())
        self.current.itemDoubleClicked.connect(lambda _: self._move_left())
        self.up.clicked.connect(lambda: self._shift(-1))
        self.down.clicked.connect(lambda: self._shift(1))
        self.current.setDragDropMode(QAbstractItemView.InternalMove)

    def _add(self, lw, key, row=None):
        it = QListWidgetItem(self.titles[key])
        it.setData(Qt.UserRole, key)
        if row is None:
            lw.addItem(it)
        else:
            lw.insertItem(row, it)
        return it

    def _move_right(self):
        it = self.options.currentItem()
        if it:
            key = it.data(Qt.UserRole)
            self.options.takeItem(self.options.row(it))
            self.current.setCurrentItem(self._add(self.current, key))

    def _move_left(self):
        it = self.current.currentItem()
        if it and self.current.count() > 1:
            key = it.data(Qt.UserRole)
            self.current.takeItem(self.current.row(it))
            self._add(self.options, key)

    def _shift(self, step):
        r = self.current.currentRow()
        if r < 0 or not 0 <= r + step < self.current.count():
            return
        it = self.current.takeItem(r)
        self.current.insertItem(r + step, it)
        self.current.setCurrentRow(r + step)

    def chosen(self) -> list[str]:
        return [self.current.item(i).data(Qt.UserRole) for i in range(self.current.count())]
