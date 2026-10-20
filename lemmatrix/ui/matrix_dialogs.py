# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Configure cell, Configure matrix and Save matrix."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QDialog, QDialogButtonBox,
                               QGroupBox, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
                               QMenu, QMessageBox, QPushButton, QRadioButton, QScrollArea, QStyledItemDelegate,
                               QToolButton, QVBoxLayout, QWidget)

from .. import matrix as mx
from ..model import Database
from . import theme
from .icons import icon
from .tagpanel import TagPanel
from .widgets import chip_metrics, paint_chips


def _buttons(dlg) -> QDialogButtonBox:
    b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    b.accepted.connect(dlg.accept)
    b.rejected.connect(dlg.reject)
    return b


# ==========================================================================
# Configure cell
# ==========================================================================

def cell_order(cell: list[str], natural: list[str]) -> list[str]:
    """The ticked lines in their order, each unticked one in its usual place among them (the
    token fields' order), so ticking Morphemes puts it above Translation, not at the end."""
    rank = {k: i for i, k in enumerate(natural)}
    order = [k for k in cell if k in rank]
    for k in natural:
        if k in order:
            continue
        at = next((i for i, x in enumerate(order) if rank[x] > rank[k]), len(order))
        order.insert(at, k)
    return order


class ConfigureCellDialog(QDialog):
    """Which lines a matrix cell shows, and in what order."""

    def __init__(self, parent, db: Database, cell: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Configure cell")
        self.setWindowIcon(icon("gear"))
        self.resize(340, 380)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Tick what each cell shows; drag to reorder."))
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        options = mx.cell_options(db)
        titles = dict(options)
        order = cell_order(cell, [k for k, _ in options])
        for k in order:
            it = QListWidgetItem(titles[k])
            it.setData(Qt.UserRole, k)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if k in cell else Qt.Unchecked)
            self.list.addItem(it)
        lay.addWidget(self.list)
        lay.addWidget(_buttons(self))

    def chosen(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]


# ==========================================================================
# One column (or row) of a matrix
# ==========================================================================

class SpecDialog(QDialog):
    """Pick the tags and match type for one matrix column or row."""

    def __init__(self, parent, db: Database, spec: mx.Spec | None = None,
                 title: str = "Matrix line"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 620)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.group = QButtonGroup(self)
        self.radios = {}
        for key, text, tip in ((mx.CITATION, "Citation", "The token with no tags"),
                               (mx.EXACT, "Exact", "Exactly these tags (group defaults don't count)"),
                               (mx.LOOSE, "Loose", "At least these tags, so SG also shows SG + GEN")):
            rb = QRadioButton(text)
            rb.setToolTip(tip)
            self.group.addButton(rb)
            self.radios[key] = rb
            row.addWidget(rb)
        row.addStretch(1)
        lay.addLayout(row)
        self.tags = TagPanel()
        self.tags.multi = True
        self.tags.on_change = self._update_count
        self.tags.build(db, set(spec.tags) if spec else set())
        hint = QLabel("Ctrl+click to pick more than one tag in a group: you get one line for "
                      "each combination (e.g. 3SG.A, 3PL.A × FUT1, FUT2 = 4 lines).")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.count = QLabel()
        self.count.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.count)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.tags)
        lay.addWidget(scroll, 1)
        lay.addWidget(_buttons(self))
        self.radios[spec.match if spec else mx.LOOSE].setChecked(True)
        for rb in self.radios.values():
            rb.toggled.connect(self._mode)
        self._mode()

    def _mode(self, *_):
        self.tags.set_enabled_all(not self.radios[mx.CITATION].isChecked())
        self._update_count()

    def _update_count(self):
        if not hasattr(self, "count") or not hasattr(self, "radios"):
            return                                # still being built
        n = len(self.specs())
        self.count.setText(f"→ {n} lines" if n > 1 else "")

    def specs(self) -> list:
        """Every line this dialogue makes: one per combination of the picked tags."""
        match = next(k for k, rb in self.radios.items() if rb.isChecked())
        if match == mx.CITATION:
            return [mx.Spec.citation()]
        return [mx.Spec(frozenset(c), match) for c in self.tags.combinations() if c]

    def spec(self) -> mx.Spec:
        specs = self.specs()
        return specs[0] if specs else mx.Spec(frozenset(), next(
            k for k, rb in self.radios.items() if rb.isChecked()))

    def accept(self):
        s = self.spec()
        if s.match != mx.CITATION and not s.tags:
            QMessageBox.information(self, "Matrix column", "Pick at least one tag, or choose Citation.")
            return
        super().accept()


class SpecDelegate(QStyledItemDelegate):
    """Shows a spec as its match type plus tag chips."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        spec: mx.Spec = index.data(Qt.UserRole)
        if spec is None:
            return
        painter.save()
        f = option.font
        kind = {mx.CITATION: "Citation", mx.EXACT: "Exact", mx.LOOSE: "Loose"}[spec.match]
        painter.setPen(theme.colour("text"))
        painter.drawText(QRectF(option.rect).adjusted(8, 0, 0, 0), Qt.AlignVCenter, kind)
        if spec.match != mx.CITATION:
            _, h = chip_metrics(f)
            paint_chips(painter, option.rect.left() + 80, option.rect.center().y() - h / 2,
                        mx.chips(self.db, spec.tags), f)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(300, 30)


class SpecList(QWidget):
    """A list of specs with add / duplicate / remove / up / down, Remove all and Restore all present."""

    def __init__(self, db: Database, specs: list, title: str, parent=None,
                 present=None, present_tip: str = ""):
        super().__init__(parent)
        self.db = db
        self.present = present                    # () -> specs for "Restore all present"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setStyleSheet("font-weight: 600;")
        head.addWidget(lbl)
        head.addStretch(1)
        for name, tip, fn in (("add", "Add a line", self._add),
                              ("duplicate", "Duplicate the selected line, then change what differs",
                               self._duplicate),
                              ("delete", "Remove the selected line", self._remove),
                              ("up", "Move up", lambda: self._shift(-1)),
                              ("down", "Move down", lambda: self._shift(1))):
            b = QToolButton()
            b.setIcon(icon(name, 20))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(lambda *_, fn=fn: fn())   # ignore the 'checked' flag
            head.addWidget(b)
        lay.addLayout(head)
        self.list = QListWidget()
        theme.as_data(self.list)
        self.list.setItemDelegate(SpecDelegate(db, self.list))
        self.list.itemDoubleClicked.connect(self._edit)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list)
        foot = QHBoxLayout()
        clear = QPushButton("Remove all")
        clear.clicked.connect(lambda *_: self.list.clear())
        foot.addWidget(clear)
        if present is not None:
            restore = QPushButton("Restore all present")
            restore.setToolTip(present_tip)
            restore.clicked.connect(lambda *_: self.set_specs(self.present()))
            foot.addWidget(restore)
        foot.addStretch(1)
        lay.addLayout(foot)
        lay.addWidget(QLabel("Double-click a line to change it."))
        for s in specs:
            self._append(s)

    def _append(self, spec, row=None):
        it = QListWidgetItem("")
        it.setData(Qt.UserRole, spec)
        it.setSizeHint(QSize(300, 30))
        if row is None:
            self.list.addItem(it)
        else:
            self.list.insertItem(row, it)
        return it

    def _insert(self, specs, row):
        """Insert lines from row on (None: at the end); selects the last one."""
        it = None
        for k, sp in enumerate(specs):
            it = self._append(sp, None if row is None else row + k)
        if it is not None:
            self.list.setCurrentItem(it)

    def _add(self):
        dlg = SpecDialog(self, self.db)
        if dlg.exec():
            r = self.list.currentRow()
            self._insert(dlg.specs(), r + 1 if r >= 0 else None)

    def _duplicate(self):
        """Open the selected line's settings as a new line just below it."""
        it = self.list.currentItem()
        if it is None:
            return
        dlg = SpecDialog(self, self.db, it.data(Qt.UserRole), title="Duplicate line")
        if dlg.exec():
            self._insert(dlg.specs(), self.list.row(it) + 1)

    def _edit(self, it):
        dlg = SpecDialog(self, self.db, it.data(Qt.UserRole))
        if dlg.exec():
            specs = dlg.specs()
            it.setData(Qt.UserRole, specs[0])
            if len(specs) > 1:                    # the extra combinations go just below
                self._insert(specs[1:], self.list.row(it) + 1)

    def _remove(self):
        r = self.list.currentRow()
        if r >= 0:
            self.list.takeItem(r)

    def _shift(self, step):
        r = self.list.currentRow()
        if r < 0 or not 0 <= r + step < self.list.count():
            return
        it = self.list.takeItem(r)
        self.list.insertItem(r + step, it)
        self.list.setCurrentRow(r + step)

    def _menu(self, pos):
        it = self.list.itemAt(pos)
        m = QMenu(self)
        if it is not None:
            self.list.setCurrentItem(it)
            m.addAction(icon("edit", 16), "Change…").triggered.connect(lambda *_: self._edit(it))
            m.addAction(icon("duplicate", 16), "Duplicate…").triggered.connect(lambda *_: self._duplicate())
            m.addAction(icon("delete", 16), "Remove").triggered.connect(lambda *_: self._remove())
            m.addSeparator()
        m.addAction(icon("add", 16), "Add…").triggered.connect(lambda *_: self._add())
        m.addAction("Remove all").triggered.connect(lambda *_: self.list.clear())
        if self.present is not None:
            m.addAction("Restore all present").triggered.connect(lambda *_: self.set_specs(self.present()))
        m.exec(self.list.viewport().mapToGlobal(pos))

    def set_specs(self, specs):
        self.list.clear()
        for s in specs:
            self._append(s)

    def specs(self) -> list:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]


class ConfigureMatrixDialog(QDialog):
    """Lemma/Tag: the columns. Tag/Tag: the rows (Y) and the columns (X)."""

    def __init__(self, parent, db: Database, config: mx.MatrixConfig, entries=None):
        super().__init__(parent)
        self.db, self.config = db, config.copy()
        tag_tag = config.kind == mx.TAG_TAG
        entries = list(entries or [])
        self.setWindowTitle("Configure matrix")
        self.setWindowIcon(icon("gear"))
        self.resize(900 if tag_tag else 560, 600)
        lay = QVBoxLayout(self)
        intro = QLabel("Each line is a set of tags with a match type: Citation (no tags), "
                       "Exact (exactly these tags; group defaults don't count) or Loose "
                       "(at least these tags).")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        row = QHBoxLayout()
        if tag_tag:
            tip = "One Loose line for each tag the shown lemmas use"
            self.y = SpecList(db, config.y, "Rows (Y)",
                              present=lambda: mx.auto_tag_specs(db, entries), present_tip=tip)
            row.addWidget(self.y)
            self.x = SpecList(db, config.x, "Columns (X)",
                              present=lambda: mx.auto_tag_specs(db, entries), present_tip=tip)
        else:
            self.y = None
            lab = QGroupBox("Rows (Y)")
            ll = QVBoxLayout(lab)
            ll.addWidget(QLabel("Lemma\n(from the lemma list)"))
            lab.setMaximumWidth(160)
            row.addWidget(lab)
            self.x = SpecList(db, config.x, "Columns (X)",
                              present=lambda: mx.auto_specs(db, entries),
                              present_tip="Citation, then one Exact column for every tag "
                                          "combination the shown lemmas have")
        row.addWidget(self.x, 1)
        lay.addLayout(row, 1)
        lay.addWidget(_buttons(self))

    def result_config(self) -> mx.MatrixConfig:
        cfg = self.config.copy()
        cfg.x = self.x.specs()
        if self.y is not None:
            cfg.y = self.y.specs()
        cfg.blank = not cfg.x and not cfg.y
        return cfg


def ask_matrix_name(parent, existing: list[str], current: str = "", title: str = "Save matrix",
                    replace: bool = True) -> str | None:
    name, ok = QInputDialog.getText(parent, title, "Name for this matrix:", text=current)
    name = name.strip()
    if not ok or not name:
        return None
    if name in existing and name != current:
        if not replace:
            QMessageBox.information(parent, title, f"There is already a matrix called “{name}”.")
            return None
        if QMessageBox.question(parent, title, f"Replace the saved matrix “{name}”?") != QMessageBox.Yes:
            return None
    return name
