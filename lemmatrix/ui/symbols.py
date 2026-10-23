# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Σymbols (Josh, 22 October): at the top of every ordinary text field's right-click menu (the one
with Undo, Redo, Cut, Copy, Paste…), a Σymbols item opens a small square grid of symbols that are
hard to type; double-clicking one puts it in at the cursor and closes the grid.

The symbols are a flat list, Edit → Lists → Symbols, kept in the database's workspace (what you
work with, not the data). One filter on the whole program adds the item, so every field has it."""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QDialog, QLayout, QLineEdit, QMenu,
                               QPlainTextEdit, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout)

DEFAULT = ["⟶", "⟵", "∅", "σ", "μ", "ω", "φ", "ι", "α", "β", "∴"]
LABEL = "Σymbols"
STANDARD = {"edit-undo", "edit-redo", "edit-cut", "edit-copy", "edit-paste", "select-all"}   # Qt's own items

_current: list[str] = list(DEFAULT)


def current() -> list[str]:
    return list(_current)


def set_current(symbols) -> None:
    """The open database's list (from its workspace)."""
    global _current
    _current = [s for s in (symbols or []) if isinstance(s, str) and s]


def _editor_of(menu: QMenu):
    """The text field a standard context menu belongs to, or None (read-only fields, spin and
    date boxes, other menus)."""
    if not any(a.objectName() in STANDARD for a in menu.actions()):
        return None
    w = menu.parent()
    while w is not None and not isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit)):
        w = w.parent()
    if w is None or w.isReadOnly():
        return None
    if isinstance(w, QLineEdit) and isinstance(w.parent(), QAbstractSpinBox):
        return None
    return w


def insert(editor, symbol: str):
    if isinstance(editor, QLineEdit):
        editor.insert(symbol)
    else:
        editor.insertPlainText(symbol)
    editor.setFocus()


class SymbolGrid(QDialog):
    """The small square grid: double-click a symbol to put it in."""

    def __init__(self, editor, symbols: list[str]):
        super().__init__(editor.window(), Qt.Popup)
        self.editor = editor
        n = max(1, len(symbols))
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        self.table = QTableWidget(rows, cols)
        t = self.table
        t.horizontalHeader().hide()
        t.verticalHeader().hide()
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionMode(QTableWidget.SingleSelection)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        f = t.font()
        f.setPointSizeF(f.pointSizeF() * 1.5)
        t.setFont(f)
        side = max(34, t.fontMetrics().height() + 14)
        for i, s in enumerate(symbols):
            it = QTableWidgetItem(s)
            it.setTextAlignment(Qt.AlignCenter)
            it.setToolTip(f"{s}  U+{ord(s[0]):04X}" if len(s) == 1 else s)
            t.setItem(i // cols, i % cols, it)
        t.horizontalHeader().setMinimumSectionSize(side)   # Qt's own minimum is wider than a symbol
        t.verticalHeader().setMinimumSectionSize(side)
        for c in range(cols):
            t.setColumnWidth(c, side)
        for r in range(rows):
            t.setRowHeight(r, side)
        fw = 2 * t.frameWidth()
        t.setFixedSize(cols * side + fw, rows * side + fw)
        t.cellDoubleClicked.connect(self._chosen)
        lay.addWidget(t)
        lay.setSizeConstraint(QLayout.SetFixedSize)          # just the grid, no room around it
        if not symbols:
            t.setToolTip("No symbols: add some in Edit → Lists → Symbols")

    def _chosen(self, r, c):
        it = self.table.item(r, c)
        if it is not None and it.text():
            insert(self.editor, it.text())
        self.close()


class SymbolsFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QMenu) and not obj.property("lmx_symbols"):
            editor = _editor_of(obj)
            if editor is not None:
                obj.setProperty("lmx_symbols", True)
                act = QAction(LABEL, obj)
                act.setToolTip("Put in a symbol that's hard to type (Edit → Lists → Symbols)")
                pos = editor.mapToGlobal(editor.cursorRect().bottomLeft()) if hasattr(editor, "cursorRect") \
                    else obj.pos()
                act.triggered.connect(lambda *_, e=editor, p=pos: open_grid(e, p))
                first = obj.actions()[0] if obj.actions() else None
                obj.insertAction(first, act)
                obj.insertSeparator(first)
        return False


def open_grid(editor, pos=None) -> SymbolGrid:
    g = SymbolGrid(editor, current())
    g.adjustSize()
    if pos is not None:
        g.move(pos)
    g.show()
    return g


def install(app) -> SymbolsFilter:
    f = SymbolsFilter(app)
    app.installEventFilter(f)
    return f
