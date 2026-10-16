"""The matrix view: All data, Tag/Tag Paradigm and Entry/Tag Paradigm."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QPointF, QRect, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QStackedWidget, QStyle,
                               QStyledItemDelegate, QTableView, QToolButton)

from .. import matrix as mx
from ..model import Database, Entry, Token
from .widgets import PITCH_BLUE, draw_pitch, ipa_font

ALL_DATA, TAG_TAG, ENTRY_TAG = 0, 1, 2
MODE_NAMES = {ALL_DATA: "All data", TAG_TAG: "Tag/Tag Paradigm", ENTRY_TAG: "Entry/Tag Paradigm"}


@dataclass
class ViewState:
    """Everything that defines a matrix layout; saved as a named view."""
    mode: int = ENTRY_TAG
    matching: str = mx.EXACTLY
    switched: bool = False
    headers: list[frozenset] | None = None        # Entry/Tag headers; None = automatic
    row_group: str = ""                           # Tag/Tag group paths, "VERB / Subject"
    col_group: str = ""
    cell_fields: list[str] = field(default_factory=lambda: ["Phonetic", "Phonemic", "Translation"])
    entry_label: str = "lemma"

    def to_dict(self, name: str) -> dict:
        d = {"name": name, "mode": ["all-data", "tag-tag", "entry-tag"][self.mode],
             "matching": self.matching, "switched": "yes" if self.switched else "no",
             "cell-fields": " ".join(self.cell_fields), "entry-label": self.entry_label}
        if self.row_group:
            d["row-group"] = self.row_group
        if self.col_group:
            d["col-group"] = self.col_group
        if self.headers is not None:
            d["headers"] = [sorted(h) for h in self.headers]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ViewState":
        v = cls()
        v.mode = {"all-data": ALL_DATA, "tag-tag": TAG_TAG}.get(d.get("mode"), ENTRY_TAG)
        v.matching = d.get("matching", mx.EXACTLY)
        v.switched = d.get("switched") == "yes"
        v.row_group = d.get("row-group", "")
        v.col_group = d.get("col-group", "")
        if d.get("cell-fields"):
            v.cell_fields = d["cell-fields"].split()
        v.entry_label = d.get("entry-label", "lemma")
        if "headers" in d:
            v.headers = [frozenset(h) for h in d["headers"]]
        return v


def group_path(path) -> str:
    return " / ".join(path)


def find_group(db: Database, path_text: str, word_class: str | None):
    for path, g in db.settings.tags.leaf_groups_for(word_class):
        if group_path(path) == path_text or group_path(path[1:]) == path_text:
            return g
    return None


# ==========================================================================
# All data: one row per token
# ==========================================================================

class AllDataModel(QAbstractTableModel):
    edited = Signal(object, int, str, str)      # entry, token index, field name, new text

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.rows: list[tuple[Entry, int]] = []
        self.columns: list[tuple[str, str]] = []
        self.ipa = ipa_font()
        self.set_columns()

    def set_columns(self):
        cols = [("ref", "Reference"), ("lemma", "Lemma"), ("tags", "Tags"), ("drawn", "Pitch (drawn)")]
        for f in self.db.settings.token_fields:
            cols.append(("f:" + f.name, f.title))
        cols += [("speaker", "Speaker"), ("date", "Date"), ("file", "Sound file")]
        self.columns = cols

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def token(self, row: int) -> tuple[Entry, Token]:
        e, i = self.rows[row]
        return e, e.tokens[i]

    def text(self, row: int, col: int) -> str:
        e, t = self.token(row)
        key = self.columns[col][0]
        s = self.db.settings
        if key == "ref":
            return e.ref
        if key == "lemma":
            return self.db.lemma(e)
        if key == "tags":
            # Group defaults (Simple, in isolation, ...) are unmarked: shown in the tooltip only.
            defaults = mx.default_names(self.db)
            return s.tags.display(self.db.word_class(e), [x for x in t.tags if x not in defaults])
        if key == "drawn":
            return ""
        if key == "speaker":
            return t.speaker
        if key == "date":
            return t.collected
        if key == "file":
            return t.file or self.db.expected_filename(e, t)
        name = key[2:]
        f = s.token_field(name)
        return t.get(name, s.primary_gloss) if f and f.multilingual else t.get(name)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        key = self.columns[index.column()][0]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return self.text(index.row(), index.column())
        if role == Qt.ToolTipRole and key == "tags":
            e, t = self.token(index.row())
            return ", ".join(self.db.settings.tags.sort(self.db.word_class(e), t.tags)) or "Citation (no tags)"
        if role == Qt.ToolTipRole and key == "file":
            e, t = self.token(index.row())
            exp = self.db.expected_filename(e, t)
            if t.file and t.file != exp:
                return f"Recorded as {t.file}\nExpected name: {exp}"
            return None if t.file else "Not recorded yet"
        if role == Qt.ForegroundRole and key == "file":
            e, t = self.token(index.row())
            if not t.file:
                return QColor("#888")
            if t.file != self.db.expected_filename(e, t):
                return QColor("#c62828")
        if role == Qt.FontRole and key in ("lemma", "f:Phonetic", "f:Phonemic"):
            return self.ipa
        if role == Qt.UserRole:
            e, t = self.token(index.row())
            return t.get("Pitch")
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.columns[index.column()][0].startswith("f:"):
            base |= Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.EditRole):
        key = self.columns[index.column()][0]
        if role != Qt.EditRole or not key.startswith("f:"):
            return False
        e, i = self.rows[index.row()]
        self.edited.emit(e, i, key[2:], str(value))
        return True

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section][1]
        return None


class DrawnPitchDelegate(QStyledItemDelegate):
    def __init__(self, db_getter, parent=None):
        super().__init__(parent)
        self.db_getter = db_getter

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        db = self.db_getter()
        text = index.data(Qt.UserRole) or ""
        draw_pitch(painter, QRectF(option.rect).adjusted(2, 2, -2, -2), text,
                   db.settings.pitch_low, db.settings.pitch_high, max_slot=20, width=1.8)

    def sizeHint(self, option, index):
        return QSize(90, 24)


# ==========================================================================
# Paradigm modes: a grid of cells, each holding stacked tokens
# ==========================================================================

class ParadigmModel(QAbstractTableModel):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.layout_ = mx.Layout()

    def set_layout(self, layout: mx.Layout):
        self.beginResetModel()
        self.layout_ = layout
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.layout_.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.layout_.cols)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.UserRole and index.isValid():
            return self.layout_.tokens(index.row(), index.column())
        if role == Qt.ToolTipRole and index.isValid():
            entry, tags = self.layout_.target(index.row(), index.column())
            if entry is None:
                return None
            hits = self.layout_.tokens(index.row(), index.column())
            lines = [f"{entry.ref} {self.db.lemma(entry)} — "
                     f"{self.db.settings.tags.display(self.db.word_class(entry), tags)}"]
            if not hits:
                lines.append("Double-click to add a token here")
            for e, t in hits:
                lines.append(f"{t.speaker or 'no speaker'}: {t.file or 'not recorded'}")
            return "\n".join(lines)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        items = self.layout_.cols if orientation == Qt.Horizontal else self.layout_.rows
        if section >= len(items):
            return None
        it = items[section]
        if role == Qt.DisplayRole:
            return ("    " + it.label) if it.sub else it.label
        if role == Qt.FontRole and it.entry is not None:
            return ipa_font(12)
        if role == Qt.ForegroundRole and it.sub:
            return QColor("#555")
        if role == Qt.ToolTipRole:
            if it.entry is not None:
                return f"{it.entry.ref}  {self.db.lemma(it.entry)}  '{self.db.gloss(it.entry)}'"
            return ", ".join(sorted(it.tags)) or "Citation (no tags)"
        return None


class TokenCellDelegate(QStyledItemDelegate):
    """Draws the tokens of a cell stacked: contour, then the chosen fields."""

    CONTOUR_H = 26

    def __init__(self, view: "ParadigmView"):
        super().__init__(view)
        self.view = view
        self.ipa = ipa_font(13)
        self.plain = view.font()

    def block_height(self) -> int:
        lines = len(self.view.state.cell_fields)
        return self.CONTOUR_H + lines * (QFontMetrics(self.ipa).height() + 1) + 10

    def paint(self, painter: QPainter, option, index):
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor("#dce6fb"))
        hits = index.data(Qt.UserRole) or []
        db = self.view.db
        bh = self.block_height()
        y = option.rect.top() + 4
        for n, (e, t) in enumerate(hits):
            if n:
                painter.setPen(QPen(QColor("#ccc"), 1, Qt.DashLine))
                painter.drawLine(option.rect.left() + 8, y - 3, option.rect.right() - 8, y - 3)
            x = option.rect.left() + 10
            pr = QRectF(x, y, option.rect.width() - 20, self.CONTOUR_H)
            draw_pitch(painter, pr, t.get("Pitch"), db.settings.pitch_low, db.settings.pitch_high,
                       color=PITCH_BLUE, max_slot=26, width=2.2)
            if t.file:                                   # small "has a recording" mark
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#2e7d32"))
                cx, cy = option.rect.right() - 12, y + 8
                painter.drawPolygon(QPolygonF([QPointF(cx - 4, cy - 5), QPointF(cx - 4, cy + 5),
                                               QPointF(cx + 5, cy)]))
            ty = y + self.CONTOUR_H
            fm = QFontMetrics(self.ipa)
            for name in self.view.state.cell_fields:
                f = db.settings.token_field(name)
                if f and f.multilingual:
                    text = t.get(name, db.settings.primary_gloss)
                else:
                    text = t.get(name)
                painter.setFont(self.ipa if name in ("Phonetic", "Phonemic") else self.plain)
                painter.setPen(QColor("#111") if text else QColor("#bbb"))
                shown = text or "—"
                if t.speaker and name == self.view.state.cell_fields[-1] and len(hits) > 1:
                    shown += f"   ({t.speaker})"
                painter.drawText(QRect(int(x), int(ty), option.rect.width() - 20, fm.height()),
                                 Qt.AlignLeft | Qt.AlignVCenter, shown)
                ty += fm.height() + 1
            y += bh
        painter.restore()

    def sizeHint(self, option, index):
        hits = index.data(Qt.UserRole) or []
        if not hits:
            return QSize(170, 40)
        return QSize(170, len(hits) * self.block_height() + 4)


class ParadigmView(QTableView):
    cellActivated = Signal(int, int, int)       # row, column, token index in cell (-1 = empty)
    cellClicked = Signal(int, int)
    switchRequested = Signal()

    def __init__(self, db: Database, state: ViewState, parent=None):
        super().__init__(parent)
        self.db = db
        self.state = state
        self.model_ = ParadigmModel(db)
        self.setModel(self.model_)
        self.delegate = TokenCellDelegate(self)
        self.setItemDelegate(self.delegate)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setCornerButtonEnabled(False)
        self.setWordWrap(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setDefaultSectionSize(180)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.verticalHeader().setMinimumWidth(90)
        self.verticalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setShowGrid(True)
        self.switch = QToolButton(self)
        self.switch.setText("⇄")
        self.switch.setToolTip("Swap rows and columns")
        self.switch.clicked.connect(self.switchRequested.emit)
        self.clicked.connect(lambda idx: self.cellClicked.emit(idx.row(), idx.column()))

    def set_layout(self, layout: mx.Layout):
        self.model_.set_layout(layout)
        self.resizeRowsToContents()
        self._place_switch()

    def _place_switch(self):
        w = self.verticalHeader().width() or 90
        h = self.horizontalHeader().height() or 26
        self.switch.setGeometry(1, 1, max(28, w - 2), max(22, h - 2))
        self.switch.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_switch()

    def updateGeometries(self):
        super().updateGeometries()
        self._place_switch()

    def mouseDoubleClickEvent(self, event):
        idx = self.indexAt(event.position().toPoint())
        if not idx.isValid():
            return super().mouseDoubleClickEvent(event)
        rect = self.visualRect(idx)
        hits = self.model_.layout_.tokens(idx.row(), idx.column())
        block = (event.position().toPoint().y() - rect.top() - 4) // self.delegate.block_height()
        n = int(block) if 0 <= block < len(hits) else (-1 if not hits else len(hits) - 1)
        self.cellActivated.emit(idx.row(), idx.column(), n)


class MatrixStack(QStackedWidget):
    """Holds the All data table and the paradigm table; the main window drives it."""

    def __init__(self, db: Database, state: ViewState, parent=None):
        super().__init__(parent)
        self.all_model = AllDataModel(db)
        self.all_view = QTableView()
        self.all_view.setModel(self.all_model)
        self.all_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.all_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.all_view.setAlternatingRowColors(True)
        self.all_view.verticalHeader().hide()
        self.all_view.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                      | QAbstractItemView.SelectedClicked)
        self.all_view.horizontalHeader().setStretchLastSection(True)
        self.all_view.verticalHeader().setDefaultSectionSize(26)
        self.drawn = DrawnPitchDelegate(lambda: self.all_model.db, self.all_view)
        self.all_view.setItemDelegateForColumn(3, self.drawn)
        self.paradigm = ParadigmView(db, state)
        self.addWidget(self.all_view)
        self.addWidget(self.paradigm)

    def set_database(self, db: Database):
        self.all_model.db = db
        self.all_model.set_columns()
        self.paradigm.db = db
        self.paradigm.model_.db = db
