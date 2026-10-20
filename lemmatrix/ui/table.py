# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""A table with a filter menu on every column: the lemma list and All data.

Each column says how to get its value from a row, whether it is open
(“Filter for…”) or closed (“Choose…”), and for closed columns where its list
comes from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import (QAbstractTableModel, QEvent, QModelIndex, QRectF, QSize, QSortFilterProxyModel,
                            Qt, Signal)
from PySide6.QtGui import QCursor, QFont, QFontMetrics, QPalette
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QLineEdit, QMenu, QStyle, QStyledItemDelegate,
                               QTableView, QToolTip)

from .. import filters as fl
from ..model import ListItem
from . import spellui, theme
from .filter_dialogs import ChooseDialog, FilterForDialog
from .searchmark import SearchDelegate, keep_colour, paint_cell
from .spellui import SpellDelegate
from .widgets import FilterHeader, chips_width, draw_pitch, ipa_font, paint_chips, underscore_unit


@dataclass
class Column:
    key: str
    title: str
    get: Callable                                   # row -> str, or list of str for tags
    closed: bool = False
    tree: Callable[[], list[ListItem]] | None = None  # closed: the list to choose from
    multi: bool = False                             # tags
    unmarked: set = field(default_factory=set)      # tags: group defaults
    edit: Callable | None = None                    # (row, text) -> None, for in-place edits
    ipa: bool = False
    kind: str = "text"                              # text, chips, drawing
    display: Callable | None = None                 # row -> text shown (if not the value)
    tooltip: Callable | None = None
    color: Callable | None = None
    blank_labels: tuple = ("Blanks", "Non-blanks")  # how the filter menu names them for this column
    flag: Callable | None = None                    # row -> bool: an extra filter choice, e.g. Rerecord
    flag_label: str = ""
    lemma_level: bool = False                       # All data: the lemma's, not the token's (double-click
                                                    # goes to the lemma in the lemma list)




def _text(value) -> str:
    if isinstance(value, (list, tuple, set, frozenset)):
        return ", ".join(value)
    return value or ""


class RowModel(QAbstractTableModel):
    edited = Signal(object, str, str)            # row, column key, new text

    def __init__(self):
        super().__init__()
        self.rows: list = []
        self.all_columns: list[Column] = []
        self.columns: list[Column] = []
        self.ipa = ipa_font()

    def set_columns(self, all_columns: list[Column], visible: list[str]):
        self.beginResetModel()
        self.all_columns = all_columns
        by_key = {c.key: c for c in all_columns}
        self.columns = [by_key[k] for k in visible if k in by_key] or all_columns[:1]
        self.endResetModel()

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def column(self, i) -> Column:
        return self.columns[i]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = self.rows[index.row()], self.columns[index.column()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            if col.kind in ("chips", "drawing"):
                return ""
            return col.display(row) if col.display else _text(col.get(row))
        if role == Qt.UserRole:
            return col.get(row)
        if role == Qt.UserRole + 1:
            return row
        if role == Qt.ToolTipRole:
            # Only what the cell doesn't already show (full tag names, file names, suggestions);
            # a cell's own text appears only when it's cut off (FilterTable).
            return col.tooltip(row) if col.tooltip else None
        if role == Qt.FontRole and col.ipa:
            return self.ipa
        if role == Qt.ForegroundRole and col.color:
            return col.color(row)
        if role == Qt.BackgroundRole and not col.edit:
            return theme.colour("read_only")     # grey: not editable here
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.columns[index.column()].edit:
            base |= Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.EditRole):
        col = self.columns[index.column()]
        if role != Qt.EditRole or not col.edit:
            return False
        self.edited.emit(self.rows[index.row()], col.key, str(value))
        return True

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columns[section].title
        return None


class RowFilter(QSortFilterProxyModel):
    searchChanged = Signal()                       # the views repaint their search marks

    def __init__(self):
        super().__init__()
        self.filters: dict[str, object] = {}       # column key -> filter
        self.pinned: str | None = None             # Ctrl+click: the id of the only row shown
        self.search = ""
        self.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.setSortRole(Qt.DisplayRole)

    def refilter(self):
        if hasattr(self, "beginFilterChange"):          # Qt 6.10 and later
            self.beginFilterChange()
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self.invalidateFilter()

    def set_search(self, text):
        self.search = fl.fold_diacritics(text).casefold()
        self.refilter()
        self.searchChanged.emit()

    def set_filter(self, key, flt):
        if flt is None:
            self.filters.pop(key, None)
        else:
            self.filters[key] = flt
        self.refilter()

    def filterAcceptsRow(self, r, parent):
        m: RowModel = self.sourceModel()
        row = m.rows[r]
        if self.pinned is not None and getattr(row, "id", None) != self.pinned:
            return False
        by_key = {c.key: c for c in m.all_columns}
        for key, flt in self.filters.items():
            col = by_key.get(key)
            if col is None:
                continue
            if isinstance(flt, fl.Flagged):
                if not (col.flag and col.flag(row)):
                    return False
            elif not fl.matches(flt, col.get(row), col.unmarked):
                return False
        if self.search:
            for col in m.columns:
                if col.kind == "drawing":
                    continue
                if self.search in fl.fold_diacritics(_text(col.get(row))).casefold():
                    break
            else:
                return False
        return True


class ListEditDelegate(QStyledItemDelegate):
    """In-place editing of a closed field: pick from its list, or type a new value."""

    def __init__(self, values: Callable, parent=None):
        super().__init__(parent)
        self.values = values                      # () -> list of values

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.setEditable(True)
        cb.addItem("")
        cb.addItems(self.values())
        return cb

    def setEditorData(self, editor, index):
        editor.setCurrentText(index.data(Qt.EditRole) or "")

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)

    def initStyleOption(self, opt, index):
        super().initStyleOption(opt, index)
        keep_colour(opt, index)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        paint_cell(self, painter, option, index)


def show_suggestion(ed: QLineEdit, suggestion: str):
    """A predicted translation in an empty field: light grey italics (the placeholder)."""
    pal = ed.palette()
    pal.setColor(QPalette.PlaceholderText, theme.colour("suggestion"))
    ed.setPalette(pal)
    shown = suggestion if (suggestion and not ed.text()) else ""
    ed.setPlaceholderText(shown)
    f = ed.font()
    f.setItalic(bool(shown))
    ed.setFont(f)


class SuggestionDelegate(SpellDelegate):
    """The English translation in All data: an empty cell shows its predicted translation in light
    grey italics; editing the cell shows it too, and → accepts it (as in the token dialogue).
    Words that may be misspelled are underlined (spellui)."""

    def __init__(self, suggest: Callable, speller=None, parent=None):
        super().__init__(speller, parent)
        self.suggest = suggest                    # row -> suggested text, or ""

    def _suggestion(self, index) -> str:
        if index.data(Qt.DisplayRole):
            return ""
        row = index.data(Qt.UserRole + 1)
        return self.suggest(row) if row is not None else ""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        text = self._suggestion(index)
        if not text:
            return
        painter.save()
        f = QFont(option.font)
        f.setItalic(True)
        painter.setFont(f)
        painter.setPen(theme.colour("suggestion"))
        r = option.rect.adjusted(4, 0, -4, 0)
        painter.drawText(r, Qt.AlignVCenter | Qt.AlignLeft,
                         painter.fontMetrics().elidedText(text, Qt.ElideRight, r.width()))
        painter.restore()

    def createEditor(self, parent, option, index):
        ed = QLineEdit(parent)
        ed.setFrame(False)
        ed.setProperty("suggestion", self._suggestion(index))
        ed.textChanged.connect(lambda *_, ed=ed: show_suggestion(ed, ed.property("suggestion")))
        spellui.attach(ed, self.speller)
        return ed

    def setEditorData(self, editor, index):
        super().setEditorData(editor, index)
        show_suggestion(editor, editor.property("suggestion"))

    def eventFilter(self, obj, event):
        if (isinstance(obj, QLineEdit) and event.type() == QEvent.KeyPress
                and event.key() == Qt.Key_Right and not (event.modifiers() & ~Qt.KeypadModifier)
                and not obj.text() and obj.property("suggestion")):
            obj.setText(obj.property("suggestion"))
            return True
        return super().eventFilter(obj, event)


class ChipsDelegate(QStyledItemDelegate):
    """Paints a list of tag labels as chips."""

    def __init__(self, labels: Callable, parent=None, empty: str = "Citation"):
        super().__init__(parent)
        self.labels = labels                      # row -> list of chip labels
        self.empty = empty                        # shown for no tags (utterances: nothing)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        row = index.data(Qt.UserRole + 1)
        labels = self.labels(row)
        if not labels:
            if not self.empty:
                return
            painter.save()
            painter.setPen(theme.colour("dim"))
            painter.drawText(option.rect.adjusted(6, 0, 0, 0), Qt.AlignVCenter, self.empty)
            painter.restore()
            return
        f = option.font
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
        from .widgets import chip_metrics
        _, h = chip_metrics(f)
        paint_chips(painter, option.rect.left() + 4, option.rect.center().y() - h / 2, labels, f,
                    max_right=option.rect.right() - 2)

    def sizeHint(self, option, index):
        row = index.data(Qt.UserRole + 1)
        f = option.font
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
        return QSize(chips_width(self.labels(row), f) + 10, 24)


class DrawingDelegate(QStyledItemDelegate):
    def __init__(self, settings: Callable, parent=None):
        super().__init__(parent)
        self.settings = settings                  # () -> (low, high)
        self.unit = underscore_unit(ipa_font(13))

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        low, high = self.settings()
        draw_pitch(painter, QRectF(option.rect).adjusted(6, 3, -2, -3), index.data(Qt.UserRole) or "",
                   low, high, width=1.8, unit=self.unit, elide=True)

    def sizeHint(self, option, index):
        from .widgets import pitch_width
        return QSize(int(pitch_width(index.data(Qt.UserRole) or "", self.unit)) + 14, 24)


class FilterTable(QTableView):
    """A sortable table whose column headers each have a filter menu."""

    filtersChanged = Signal()
    rowActivated = Signal(object)                 # double-click (outside editable cells) or Enter
    lemmaActivated = Signal(object)               # double-click in a lemma-level column (All data)
    deleteRequested = Signal()
    contextRequested = Signal(object, object)     # row (or None), global position
    playRequested = Signal()                      # spacebar

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model_ = RowModel()
        self.proxy = RowFilter()
        self.proxy.setSourceModel(self.model_)
        self.header_ = FilterHeader(self)
        self.setHorizontalHeader(self.header_)
        self.setModel(self.proxy)
        self.setItemDelegate(SearchDelegate(self))  # marks what the search bar found
        self.proxy.searchChanged.connect(lambda: self.viewport().update())
        self.setSortingEnabled(True)
        self.sortByColumn(-1, Qt.AscendingOrder)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(False)
        theme.as_data(self)
        self.space_plays = False                  # True: the spacebar asks to play (All data)
        self.ctrl_click_pins = False              # True: Ctrl+click shows only that row (the lemma list)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(26)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setResizeContentsPrecision(200)
        self.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.contextRequested.emit(self.row_at(self.indexAt(pos)), self.viewport().mapToGlobal(pos)))
        self.header_.filterClicked.connect(self._filter_menu)
        self.doubleClicked.connect(self._double)
        # Told once the proxy has finished filtering, never from inside it: Bulk edit clears its
        # preview on filtersChanged, and changing the model mid-filter crashed (Josh, 19 October).
        self._filters_timer = QTimer(self)
        self._filters_timer.setSingleShot(True)
        self._filters_timer.setInterval(0)
        self._filters_timer.timeout.connect(self.filtersChanged.emit)
        for sig in (self.proxy.rowsInserted, self.proxy.rowsRemoved, self.proxy.modelReset,
                    self.proxy.layoutChanged):
            sig.connect(lambda *a: self._filters_timer.start())
        self._delegates = []
        self._tip_index = None                    # the cell a tooltip is waiting for
        self._tip_timer = QTimer(self)
        self._tip_timer.setSingleShot(True)
        self._tip_timer.timeout.connect(self._show_tip)

    # ---- tooltips ----------------------------------------------------------
    # Twice Qt's usual wait before a cell's tooltip appears (Josh, 18 October: it came too
    # quickly), and only for what the cell doesn't show: its column's tooltip, or its own
    # text when the column is too narrow for it.
    TIP_FACTOR = 2

    def tip_delay(self) -> int:
        """The extra wait (ms) after Qt's own, which makes the whole wait TIP_FACTOR times Qt's."""
        base = self.style().styleHint(QStyle.SH_ToolTip_WakeUpDelay, None, self) or 700
        return base * (self.TIP_FACTOR - 1)

    def tip_text(self, idx) -> str:
        if not idx.isValid():
            return ""
        tip = idx.data(Qt.ToolTipRole)
        if tip:
            return str(tip)
        text = idx.data(Qt.DisplayRole) or ""
        if not text:
            return ""
        font = idx.data(Qt.FontRole) or self.font()
        room = self.visualRect(idx).width() - 10
        return text if QFontMetrics(font).horizontalAdvance(text) > room else ""

    def viewportEvent(self, event):
        if event.type() == QEvent.ToolTip:
            idx = self.indexAt(event.pos())
            if not self.tip_text(idx):
                QToolTip.hideText()
                self._tip_timer.stop()
                event.ignore()
                return True
            if QToolTip.isVisible() and self._tip_index == idx:
                return True
            self._tip_index = idx
            self._tip_timer.start(self.tip_delay())
            return True
        if event.type() == QEvent.Leave:
            self._tip_timer.stop()
        return super().viewportEvent(event)

    def _show_tip(self):
        idx = self._tip_index
        if idx is None or not idx.isValid():
            return
        here = self.indexAt(self.viewport().mapFromGlobal(QCursor.pos()))
        if here != idx:                           # the mouse moved on meanwhile
            return
        text = self.tip_text(idx)
        if text:
            QToolTip.showText(QCursor.pos(), text, self.viewport(), self.visualRect(idx))

    # ---- setup -----------------------------------------------------------
    def set_columns(self, all_columns: list[Column], visible: list[str]):
        keep = {k: v for k, v in self.proxy.filters.items() if any(c.key == k for c in all_columns)}
        self.model_.set_columns(all_columns, visible)
        self.proxy.filters = keep
        self._refresh_header()
        for d in self._delegates:
            d.deleteLater()
        self._delegates = []
        for i, c in enumerate(self.model_.columns):
            self.setItemDelegateForColumn(i, None)
        self.proxy.refilter()

    def set_delegate(self, key: str, delegate):
        for i, c in enumerate(self.model_.columns):
            if c.key == key:
                self.setItemDelegateForColumn(i, delegate)
                self._delegates.append(delegate)

    def visible_keys(self) -> list[str]:
        return [c.key for c in self.model_.columns]

    def set_rows(self, rows):
        current = self.current_row()
        self.model_.set_rows(rows)
        self.select_row(current)

    # ---- access ----------------------------------------------------------
    def row_at(self, idx):
        if not idx.isValid():
            return None
        return self.model_.rows[self.proxy.mapToSource(idx).row()]

    def current_row(self):
        return self.row_at(self.currentIndex())

    def visible_rows(self) -> list:
        return [self.model_.rows[self.proxy.mapToSource(self.proxy.index(r, 0)).row()]
                for r in range(self.proxy.rowCount())]

    def select_row(self, row):
        if row is None:
            return
        try:
            i = self.model_.rows.index(row)
        except ValueError:
            return
        idx = self.proxy.mapFromSource(self.model_.index(i, 0))
        if idx.isValid():
            self.setCurrentIndex(idx)
            self.scrollTo(idx)

    # ---- filters ---------------------------------------------------------
    def _refresh_header(self):
        self.header_.active = {i for i, c in enumerate(self.model_.columns)
                               if c.key in self.proxy.filters or (self.proxy.pinned and i == 0)}
        self.header_.viewport().update()

    def clear_filters(self):
        self.proxy.filters.clear()
        self.proxy.pinned = None
        self.proxy.refilter()
        self._refresh_header()
        self.filtersChanged.emit()

    def active_filters(self) -> int:
        return len(self.proxy.filters) + (self.proxy.pinned is not None)

    def filter_same_tags(self, row, key: str = "tags"):
        """Right-click → Filter for same: the Tags filter set to exactly this row's tags (Citation if none)."""
        col = next((c for c in self.model_.all_columns if c.key == key), None)
        if col is None or row is None:
            return
        tags = set(col.get(row)) or {fl.CITATION_ITEM}
        self.proxy.set_filter(key, fl.ChoiceFilter(tags, fl.EXACTLY))
        self._refresh_header()
        self.filtersChanged.emit()

    def toggle_pin(self, row):
        """Ctrl+click: show only this row; again (on any row): show them all again."""
        self.proxy.pinned = None if self.proxy.pinned is not None or row is None else getattr(row, "id", None)
        self.proxy.refilter()
        self._refresh_header()
        self.select_row(row)
        self.filtersChanged.emit()

    def pinned_row(self):
        if self.proxy.pinned is None:
            return None
        return next((r for r in self.model_.rows if getattr(r, "id", None) == self.proxy.pinned), None)

    def _filter_menu(self, column: int, pos):
        col = self.model_.columns[column]
        current = self.proxy.filters.get(col.key)
        menu = QMenu(self)
        acts = {}
        blanks, nonblanks = col.blank_labels
        choices = [("Show all", None), (blanks, "blanks"), (nonblanks, "nonblanks")]
        if col.blank_labels != ("Blanks", "Non-blanks"):    # e.g. Soundfile: Present before Missing
            choices[1], choices[2] = choices[2], choices[1]
        if col.flag is not None:
            choices.append((col.flag_label, "flag"))
        for label, kind in choices:
            a = menu.addAction(label)
            a.setCheckable(True)
            a.setChecked((kind is None and current is None)
                         or (kind == "blanks" and isinstance(current, fl.Blanks))
                         or (kind == "nonblanks" and isinstance(current, fl.NonBlanks))
                         or (kind == "flag" and isinstance(current, fl.Flagged)))
            acts[a] = kind
        menu.addSeparator()
        if col.closed:
            special = menu.addAction("Choose…")
            special.setCheckable(True)
            special.setChecked(isinstance(current, fl.ChoiceFilter))
        else:
            special = menu.addAction("Filter for…")
            special.setCheckable(True)
            special.setChecked(isinstance(current, fl.TextFilter))
        if current is not None and hasattr(current, "describe"):
            menu.addSeparator()
            note = menu.addAction(f"Now: {current.describe()}")
            note.setEnabled(False)
        chosen = menu.exec(pos)
        if chosen is None:
            return
        if chosen is special:
            new = self._ask(col, current)
            if new is None:
                return
        else:
            kind = acts.get(chosen, "keep")
            if kind == "keep":
                return
            new = {None: None, "blanks": fl.Blanks(), "nonblanks": fl.NonBlanks(),
                   "flag": fl.Flagged(col.flag_label)}[kind]
        self.proxy.set_filter(col.key, new)
        self._refresh_header()
        self.filtersChanged.emit()

    def _ask(self, col: Column, current):
        if col.closed:
            counts: dict[str, int] = {}
            for row in self.model_.rows:
                v = col.get(row)
                if col.multi and not v:
                    v = [fl.CITATION_ITEM]
                for x in (v if isinstance(v, (list, set, tuple, frozenset)) else [v]):
                    if x:
                        counts[x] = counts.get(x, 0) + 1
            tree = col.tree() if col.tree else []
            known = {i.name for top in tree for i in top.walk()}
            others = sorted(k for k in counts if k not in known and k != fl.CITATION_ITEM)
            if others:
                tree = tree + [ListItem("(other values)", [ListItem(o) for o in others])]
            dlg = ChooseDialog(self, col.title, tree, counts,
                               current if isinstance(current, fl.ChoiceFilter) else None,
                               allow_exactly=col.multi)
            if dlg.exec():
                f = dlg.result_filter()
                f.selected.discard("(other values)")
                return f
            return None
        dlg = FilterForDialog(self, col.title, current if isinstance(current, fl.TextFilter) else None)
        return dlg.result_filter() if dlg.exec() else None

    # ---- keys and clicks -------------------------------------------------
    def mousePressEvent(self, event):
        if self.ctrl_click_pins and event.button() == Qt.LeftButton and event.modifiers() & Qt.ControlModifier:
            idx = self.indexAt(event.position().toPoint())
            if idx.isValid():
                self.toggle_pin(self.row_at(idx))
                event.accept()
                return
        super().mousePressEvent(event)

    def _double(self, idx):
        col = self.model_.columns[idx.column()]
        if col.edit:
            return                              # editing in place
        if col.lemma_level:
            self.lemmaActivated.emit(self.row_at(idx))
            return
        self.rowActivated.emit(self.row_at(idx))

    def keyboardSearch(self, search: str):
        """No type-to-jump: IPA takes several keystrokes per symbol, so jumping only confuses (Josh, 19 October)."""

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.state() != QAbstractItemView.EditingState:
            row = self.current_row()
            if row is not None:
                self.rowActivated.emit(row)
                return
        if event.key() == Qt.Key_Delete and self.state() != QAbstractItemView.EditingState:
            self.deleteRequested.emit()
            return
        if (event.key() == Qt.Key_Space and not event.modifiers()
                and self.state() != QAbstractItemView.EditingState
                and self.space_plays):
            self.playRequested.emit()
            return
        super().keyPressEvent(event)
