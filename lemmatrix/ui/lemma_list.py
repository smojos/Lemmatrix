"""The lemma list on the left: entries as rows, entry fields as columns."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTableView, QWidgetAction, QCheckBox

from ..model import Database, Entry
from .widgets import FilterHeader, ipa_font

EMPTY = "(empty)"


class LemmaModel(QAbstractTableModel):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.columns: list[tuple[str, str, str]] = []   # (key, title, field name)
        self.ipa = ipa_font()
        self.set_default_columns()

    def set_default_columns(self, visible: list[str] | None = None):
        s = self.db.settings
        cols = [("ref", "Reference", "")]
        for f in s.entry_fields:
            cols.append((f.name, f.title, f.name))
        if visible is None:
            visible = ["ref"] + [f.name for f in s.entry_fields if f.role in ("lemma", "gloss", "word-class")]
        self.all_columns = cols
        self.beginResetModel()
        self.columns = [c for c in cols if c[0] in visible]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.db.entries)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def value(self, e: Entry, col: int) -> str:
        key, _, name = self.columns[col]
        if key == "ref":
            return e.ref
        f = self.db.settings.entry_field(name)
        if f and f.multilingual:
            return e.get(name, self.db.settings.primary_gloss)
        return e.get(name)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        e = self.db.entries[index.row()]
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return self.value(e, index.column())
        if role == Qt.FontRole:
            f = self.db.settings.entry_field(self.columns[index.column()][2])
            if f and f.role == "lemma":
                return self.ipa
        if role == Qt.UserRole:
            return e
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columns[section][1]
        return None

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()


class LemmaFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.column_filters: dict[str, set[str]] = {}    # column key -> allowed values
        self.setSortCaseSensitivity(Qt.CaseInsensitive)

    def set_text(self, text: str):
        self.text = text.casefold()
        self.invalidateFilter()

    def set_column_filter(self, key: str, values: set[str] | None):
        if values is None:
            self.column_filters.pop(key, None)
        else:
            self.column_filters[key] = values
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        m: LemmaModel = self.sourceModel()
        e = m.db.entries[row]
        for c, (key, _, _) in enumerate(m.columns):
            allowed = self.column_filters.get(key)
            if allowed is not None and (m.value(e, c) or EMPTY) not in allowed:
                return False
        if self.text:
            hay = [e.ref, *e.values.values(), *(v for d in e.multi.values() for v in d.values())]
            if not any(self.text in h.casefold() for h in hay):
                return False
        return True


class LemmaList(QTableView):
    """Table of entries with a filter button on every column header."""

    entryActivated = Signal(object)        # double-click / Enter
    currentEntryChanged = Signal(object)
    filtersChanged = Signal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.model_ = LemmaModel(db)
        self.proxy = LemmaFilter()
        self.proxy.setSourceModel(self.model_)
        self.header_ = FilterHeader(self)
        self.setHorizontalHeader(self.header_)
        self.setModel(self.proxy)
        self.setSortingEnabled(True)
        self.sortByColumn(-1, Qt.AscendingOrder)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(26)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setResizeContentsPrecision(200)
        self.header_.filterClicked.connect(self._filter_menu)
        self.doubleClicked.connect(lambda idx: self.entryActivated.emit(self.entry_at(idx)))
        self.selectionModel().currentRowChanged.connect(
            lambda cur, prev: self.currentEntryChanged.emit(self.entry_at(cur)))
        self.proxy.rowsInserted.connect(lambda *a: self.filtersChanged.emit())
        self.proxy.rowsRemoved.connect(lambda *a: self.filtersChanged.emit())
        self.proxy.modelReset.connect(self.filtersChanged.emit)
        self.proxy.layoutChanged.connect(self.filtersChanged.emit)

    # ---- access -------------------------------------------------------
    def set_database(self, db: Database):
        self.model_.db = db
        self.proxy.column_filters.clear()
        self.header_.active.clear()
        self.model_.set_default_columns()
        self.resizeColumnsToContents()

    def entry_at(self, idx) -> Entry | None:
        if not idx.isValid():
            return None
        src = self.proxy.mapToSource(idx)
        return self.model_.db.entries[src.row()]

    def current_entry(self) -> Entry | None:
        return self.entry_at(self.currentIndex())

    def visible_entries(self) -> list[Entry]:
        """Entries passing the search and filters, in the list's current order."""
        return [self.entry_at(self.proxy.index(r, 0)) for r in range(self.proxy.rowCount())]

    def select_entry(self, entry: Entry | None):
        if entry is None or entry not in self.model_.db.entries:
            return
        src = self.model_.index(self.model_.db.entries.index(entry), 0)
        idx = self.proxy.mapFromSource(src)
        if idx.isValid():
            self.setCurrentIndex(idx)
            self.scrollTo(idx)

    def refresh(self):
        current = self.current_entry()
        self.model_.refresh()
        self.select_entry(current)

    def set_visible_columns(self, keys: list[str]):
        self.model_.set_default_columns(keys)
        self.resizeColumnsToContents()

    # ---- column filters ----------------------------------------------
    def _filter_menu(self, column: int, pos):
        key = self.model_.columns[column][0]
        values = sorted({self.model_.value(e, column) or EMPTY for e in self.model_.db.entries},
                        key=str.casefold)
        current = self.proxy.column_filters.get(key, set(values))
        menu = QMenu(self)
        show_all = menu.addAction("Show all")
        menu.addSeparator()
        boxes = []
        for v in values[:300]:
            cb = QCheckBox(v, menu)
            cb.setChecked(v in current)
            wa = QWidgetAction(menu)
            wa.setDefaultWidget(cb)
            menu.addAction(wa)
            boxes.append(cb)
        menu.addSeparator()
        apply = menu.addAction("Apply")
        chosen = menu.exec(pos)
        if chosen is show_all:
            self.proxy.set_column_filter(key, None)
            self.header_.active.discard(column)
        elif chosen is apply or chosen is None:
            picked = {cb.text() for cb in boxes if cb.isChecked()}
            if chosen is None and picked == current:
                return
            if picked == set(values):
                self.proxy.set_column_filter(key, None)
                self.header_.active.discard(column)
            else:
                self.proxy.set_column_filter(key, picked)
                self.header_.active.add(column)
        self.header_.viewport().update()
        self.filtersChanged.emit()

    def clear_filters(self):
        self.proxy.column_filters.clear()
        self.header_.active.clear()
        self.proxy.invalidateFilter()
        self.header_.viewport().update()
        self.filtersChanged.emit()
