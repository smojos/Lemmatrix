# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The paradigm grid used by the Lemma/Tag and Tag/Tag matrices.

Tokens that match the same cell are shown side by side, in tag order, each
with small chips for what it adds (e.g. "+GEN"). Cells whose tags contradict
are greyed out. Headers show their tags as chips.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QStyle, QStyledItemDelegate,
                               QTableView, QToolButton)

from .. import matrix as mx
from ..model import Database
from .icons import icon
from . import theme, widgets
from .widgets import meaning
from .widgets import (chip_metrics, chips_width, draw_pitch, ipa_font, paint_chips,
                      pitch_width, underscore_unit)

PAD = 8          # inside a cell
GAP = 14         # between side-by-side tokens
SOUND_W = 16     # room for the recording symbol at the top right of each token


def draw_sound_mark(p: QPainter, x: float, y: float, state: str):
    """A small speaker: green = recording on disk, red = recorded but missing, grey outline = none;
    a cloud = the recording is online only (OneDrive) and needs internet to play."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPolygonF
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    if state == "cloud":
        from PySide6.QtGui import QPainterPath
        c = theme.colour("sound_cloud")
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)        # overlapping puffs fill solid
        path.addEllipse(QRectF(x, y + 4, 6, 6))
        path.addEllipse(QRectF(x + 3, y + 1.5, 7, 7))
        path.addEllipse(QRectF(x + 7, y + 4, 6, 6))
        path.addRect(QRectF(x + 3, y + 6.5, 7, 3.5))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawPath(path.simplified())
        p.restore()
        return
    color = theme.colour({"ok": "sound_ok", "missing": "sound_missing"}.get(state, "no_sound"))
    body = QPolygonF([QPointF(x, y + 4), QPointF(x + 3, y + 4), QPointF(x + 7, y + 1),
                      QPointF(x + 7, y + 11), QPointF(x + 3, y + 8), QPointF(x, y + 8)])
    if state == "none":
        p.setPen(QPen(color, 1))
        p.setBrush(Qt.NoBrush)
    else:
        p.setPen(Qt.NoPen)
        p.setBrush(color)
    p.drawPolygon(body)
    if state != "none":
        p.setPen(QPen(color, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(x + 5, y + 2.5, 5, 7), -60 * 16, 120 * 16)
        p.drawArc(QRectF(x + 5, y, 8, 12), -60 * 16, 120 * 16)
    p.restore()
IPA_FIELDS = {"Phonetic", "Phonemic"}


class MatrixModel(QAbstractTableModel):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.layout_ = mx.Layout()

    def view_sound_files(self):
        v = self.parent() if hasattr(self, "parent") else None
        return getattr(v, "sound_files", set())

    def set_layout(self, layout: mx.Layout):
        self.beginResetModel()
        self.layout_ = layout
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.layout_.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.layout_.cols)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if role == Qt.UserRole:
            return self.layout_.tokens(r, c)
        if role == Qt.ToolTipRole:
            if (r, c) in self.layout_.greyed:
                return "These tags contradict each other, so this cell can't hold a token."
            entry, tags = self.layout_.target(r, c)
            if entry is None:
                return None
            hits = self.layout_.tokens(r, c)
            lines = [f"{entry.ref}  {self.db.lemma(entry)}  {meaning(self.db.gloss(entry))}"]
            for _, t in hits:
                v = self.parent()
                cloud = getattr(v, "cloud_files", set())
                rec = (("recorded, online only: needs internet to play" if t.file in cloud else "recorded")
                       if t.file in self.view_sound_files() else "recording missing") if t.file \
                    else "not recorded"
                lines.append((" + ".join(mx.chips(self.db, t.tags)) or "Citation") + f"  ({rec})")
                if widgets.SHOW_UNUSUAL:
                    lines += ["  ⚠ " + n for n in mx.unusual_notes(self.db, entry, t.tags)]
            if not hits:
                lines.append("Double-click to add a token here")
            return "\n".join(lines)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        items = self.layout_.cols if orientation == Qt.Horizontal else self.layout_.rows
        if section >= len(items):
            return None
        it = items[section]
        if role == Qt.DisplayRole:
            return it.label
        if role == Qt.UserRole:
            return it.chips if (it.spec and it.spec.match != mx.CITATION) else None
        if role == Qt.UserRole + 1:
            return it.spec.match == mx.LOOSE if it.spec else False
        if role == Qt.FontRole and it.entry is not None:
            return ipa_font(13)
        if role == Qt.ToolTipRole:
            if it.entry is not None:
                return f"{it.entry.ref}  {self.db.lemma(it.entry)}  {meaning(self.db.gloss(it.entry))}"
            if it.spec:
                kind = {mx.CITATION: "Citation", mx.EXACT: "Exact", mx.LOOSE: "Loose"}[it.spec.match]
                tip = f"{kind}: {', '.join(self.db.settings.tags.sort(it.spec.tags)) or 'no tags'}"
                d = self.db.settings.tags.descriptions(it.spec.tags)
                return tip + ("\n" + d if d else "")
        return None


class ChipHeader(QHeaderView):
    """A header that shows its sections' tags as chips in the theme colour."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        self.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        f = self.font()
        self.chip_font = QFont(f)

    def _chips(self, section):
        m = self.model()
        return m.headerData(section, self.orientation(), Qt.UserRole) if m else None

    MAX_TOP_LINES = 2      # tags across the top wrap onto at most two lines

    def _max_lines(self) -> int | None:
        """Tags down the side wrap as far as needed; across the top, onto two lines at most."""
        return None if self.orientation() == Qt.Vertical else self.MAX_TOP_LINES

    def _chip_lines(self, chips, width: float) -> list[list[str]]:
        """The chips in rows that fit the width (a chip wider than the width gets a row of its own)."""
        fm, _ = chip_metrics(self.chip_font)
        lines, line, x = [], [], 0.0
        for t in chips:
            w = fm.horizontalAdvance(t) + 12
            if line and x + w > width:
                lines.append(line)
                line, x = [], 0.0
            line.append(t)
            x += w + 4
        if line:
            lines.append(line)
        return lines

    def min_width(self, labels) -> int:
        """The narrowest section (margins included) that holds the chips in two lines."""
        fm, _ = chip_metrics(self.chip_font)
        full = chips_width(labels, self.chip_font)
        lo = max(fm.horizontalAdvance(t) + 12 for t in labels)
        hi = full
        while lo < hi:                                      # the narrowest width that still fits
            mid = (lo + hi) // 2
            if len(self._chip_lines(labels, mid)) <= self.MAX_TOP_LINES:
                hi = mid
            else:
                lo = mid + 1
        return lo + 24

    def paintSection(self, painter, rect, index):
        chips = self._chips(index)
        if chips is None:
            painter.save()
            super().paintSection(painter, rect, index)
            painter.restore()
            return
        painter.save()
        opt_rect = QRect(rect)
        painter.fillRect(opt_rect, self.palette().button())
        painter.setPen(QPen(theme.colour("grid")))
        painter.drawRect(opt_rect.adjusted(0, 0, -1, -1))
        _, h = chip_metrics(self.chip_font)
        labels = chips or ["(no tags)"]
        loose = self.model().headerData(index, self.orientation(), Qt.UserRole + 1)
        lines = self._chip_lines(labels, rect.width() - 24)
        cap = self._max_lines()
        cut = cap is not None and len(lines) > cap
        if cut:                                             # narrowed by hand: the rest is cut off
            lines = lines[:cap - 1] + [[t for ln in lines[cap - 1:] for t in ln]]
        y = rect.center().y() - (len(lines) * (h + 4) - 4) / 2
        x = rect.left() + 6
        for n, line in enumerate(lines):
            last = n == len(lines) - 1
            x = paint_chips(painter, rect.left() + 6, y, line, self.chip_font,
                            max_right=rect.right() - 14 if last and cut else None)
            y += h + 4
        y -= h + 4
        if loose or cut:
            painter.setPen(theme.colour("muted"))
            painter.drawText(QRectF(x, y, 30, h), Qt.AlignVCenter, "…")
        painter.restore()

    WRAP_WIDTH = 170       # the widest a header of tags down the side grows before it wraps

    def sectionSizeFromContents(self, index):
        s = super().sectionSizeFromContents(index)
        chips = self._chips(index)
        if chips is None:
            return s
        _, h = chip_metrics(self.chip_font)
        labels = chips or ["(no tags)"]
        if self.orientation() == Qt.Vertical:
            w = min(chips_width(labels, self.chip_font) + 24, self.WRAP_WIDTH)
            n = len(self._chip_lines(labels, w - 24))
            return QSize(w, max(s.height(), n * (h + 4) - 4 + 10))   # not the label's own width
        # Across the top: as narrow as two lines allow (the data usually decides the width),
        # as tall as the lines the column's actual width needs.
        w = self.min_width(labels)
        width = max(w, self.sectionSize(index)) if index < self.count() else w
        n = min(self.MAX_TOP_LINES, len(self._chip_lines(labels, width - 24)))
        return QSize(w, max(s.height(), n * (h + 4) - 4 + 10))


class TokenCellDelegate(QStyledItemDelegate):
    """Draws a cell's tokens side by side."""

    def __init__(self, view: "MatrixView"):
        super().__init__(view)
        self.view = view
        self.ipa = ipa_font(13)
        self.plain = QFont(view.font())
        self.small = QFont(view.font())
        self.small.setPointSizeF(max(7.0, self.small.pointSizeF() - 1.5))
        self.unit = underscore_unit(self.ipa)

    # ---- geometry --------------------------------------------------------
    def _lines(self):
        return [f for f in self.view.cell_fields if f != "drawing"]

    def _text(self, t, name):
        return mx.cell_text(self.view.db, t, name)

    def _font(self, name):
        return self.ipa if name in IPA_FIELDS else self.plain

    def chips_for(self, r, c, t):
        lay = self.view.model_.layout_
        db = self.view.db
        spec = lay.spec_at(r, c)
        entry, _ = lay.target(r, c)
        out = mx.extra_chips(db, t, spec, entry, self.view.defaults)
        if widgets.SHOW_UNUSUAL and entry is not None and lay.entry is None and spec is not None:
            # Lemma/Tag: the column's own tags aren't marked in its header (the column spans
            # many lemmas), so an unusual one shows on the token itself.
            out = [c for c in mx.chips(db, set(spec.tags) & set(t.tags), entry)
                   if isinstance(c, mx.Unusual)] + out
        return out

    def block_widths(self, r, c, hits) -> list[int]:
        out = []
        for _, t in hits:
            w = 0.0
            if "drawing" in self.view.cell_fields:
                w = pitch_width(t.get("Pitch"), self.unit)
            for name in self._lines():
                w = max(w, QFontMetrics(self._font(name)).horizontalAdvance(self._text(t, name) or "—"))
            chips = self.chips_for(r, c, t)
            if chips:
                w = max(w, chips_width(chips, self.small))
            out.append(int(w) + 4 + SOUND_W)
        return out

    def chip_row_needed(self, r, c, hits) -> bool:
        return any(self.chips_for(r, c, t) for _, t in hits)

    def cell_height(self, r, c, hits) -> int:
        h = PAD * 2
        if self.chip_row_needed(r, c, hits):
            h += chip_metrics(self.small)[1] + 4
        if "drawing" in self.view.cell_fields:
            h += 26
        for name in self._lines():
            h += QFontMetrics(self._font(name)).height() + 1
        return h

    def cell_width(self, r, c, hits) -> int:
        widths = self.block_widths(r, c, hits)
        return PAD * 2 + sum(widths) + GAP * max(0, len(widths) - 1)

    def block_at(self, r, c, hits, x_in_cell: float) -> int:
        """Which side-by-side token a click at x (inside the cell) hits; -1 for none."""
        x = PAD
        for n, w in enumerate(self.block_widths(r, c, hits)):
            if x - GAP / 2 <= x_in_cell <= x + w + GAP / 2:
                return n
            x += w + GAP
        return -1

    # ---- painting --------------------------------------------------------
    def paint(self, painter: QPainter, option, index):
        r, c = index.row(), index.column()
        lay = self.view.model_.layout_
        painter.save()
        rect = option.rect
        if (r, c) in lay.greyed:
            painter.setClipRect(rect)
            painter.fillRect(rect, theme.colour("greyed"))
            painter.setPen(QPen(theme.colour("hatch"), 1))
            for k in range(-rect.height(), rect.width(), 10):
                painter.drawLine(rect.left() + k, rect.bottom(), rect.left() + k + rect.height(), rect.top())
            painter.restore()
            return
        if option.state & QStyle.State_Selected:
            painter.fillRect(rect, theme.colour("selected_cell"))
        hits = index.data(Qt.UserRole) or []
        if not hits:
            painter.restore()
            return
        db = self.view.db
        widths = self.block_widths(r, c, hits)
        chip_row = self.chip_row_needed(r, c, hits)
        sel = self.view.selected
        x = rect.left() + PAD
        for n, ((e, t), w) in enumerate(zip(hits, widths)):
            y = rect.top() + PAD
            state = "none" if not t.file else (("cloud" if t.file in self.view.cloud_files else "ok")
                                               if t.file in self.view.sound_files else "missing")
            if sel == (r, c, n):
                painter.setPen(QPen(theme.colour("selected_token_line"), 1.5))
                painter.setBrush(theme.colour("selected_token"))
                painter.drawRoundedRect(QRectF(x - 5, rect.top() + 3, w + 10, rect.height() - 6), 5, 5)
            if chip_row:
                chips = self.chips_for(r, c, t)
                if chips:
                    paint_chips(painter, x, y, chips, self.small)
                y += chip_metrics(self.small)[1] + 4
            if "drawing" in self.view.cell_fields:
                draw_pitch(painter, QRectF(x, y, w, 22), t.get("Pitch"), db.settings.pitch_low,
                           db.settings.pitch_high, width=2.2, unit=self.unit)
                y += 26
            for name in self._lines():
                font = self._font(name)
                fm = QFontMetrics(font)
                text = self._text(t, name)
                painter.setFont(font)
                painter.setPen(theme.colour("text") if text else theme.colour("faint"))
                painter.drawText(QRect(int(x), int(y), int(w) + 2, fm.height()),
                                 Qt.AlignLeft | Qt.AlignVCenter, text or "—")
                y += fm.height() + 1
            draw_sound_mark(painter, x + w - SOUND_W + 2, rect.top() + PAD, state)
            x += w + GAP
        painter.restore()

    def sizeHint(self, option, index):
        hits = index.data(Qt.UserRole) or []
        if not hits:
            return QSize(110, 40)
        return QSize(self.cell_width(index.row(), index.column(), hits),
                     self.cell_height(index.row(), index.column(), hits))


class MatrixView(QTableView):
    tokenClicked = Signal(int, int, int)      # row, column, token number in cell (-1: none)
    cellActivated = Signal(int, int, int)     # double-click / Enter
    contextRequested = Signal(int, int, int, object)
    deleteRequested = Signal()
    switchRequested = Signal()
    playRequested = Signal()                  # spacebar
    entryActivated = Signal(object)           # a lemma's header double-clicked (on either axis)

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.defaults = mx.default_names(db)
        self.cell_fields = list(mx.DEFAULT_CELL)
        self.selected: tuple | None = None      # (row, column, token number)
        self.sound_files: set[str] = set()      # recordings present in the sound folder
        self.cloud_files: set[str] = set()      # those that are online-only
        self.model_ = MatrixModel(db)
        self.model_.setParent(self)
        self.setModel(self.model_)
        self.setHorizontalHeader(ChipHeader(Qt.Horizontal, self))
        self.setVerticalHeader(ChipHeader(Qt.Vertical, self))
        self.delegate = TokenCellDelegate(self)
        self.setItemDelegate(self.delegate)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setCornerButtonEnabled(False)
        theme.as_data(self)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.verticalHeader().setMinimumWidth(90)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context)
        for hdr, lines in ((self.verticalHeader(), "rows"), (self.horizontalHeader(), "cols")):
            hdr.sectionDoubleClicked.connect(lambda i, lines=lines: self._header_activated(lines, i))
        self.switch = QToolButton(self)
        self.switch.setIcon(icon("switch", 20))
        self.switch.setToolTip("Swap rows and columns (display only)")
        self.switch.clicked.connect(self.switchRequested.emit)

    def _header_activated(self, lines: str, i: int):
        items = getattr(self.model_.layout_, lines, [])
        if 0 <= i < len(items) and items[i].entry is not None:
            self.entryActivated.emit(items[i].entry)

    def set_database(self, db: Database):
        self.db = db
        self.model_.db = db
        self.defaults = mx.default_names(db)

    def set_layout(self, layout: mx.Layout, cell_fields: list[str]):
        self.cell_fields = list(cell_fields)
        self.defaults = mx.default_names(self.db)
        self.selected = None
        self.model_.set_layout(layout)
        # Sizes from the content (faster than letting Qt measure every cell).
        d = self.delegate
        widths = [0] * len(layout.cols)
        heights = [40] * len(layout.rows)
        for (r, c), hits in layout.cells.items():
            widths[c] = max(widths[c], d.cell_width(r, c, hits))
            heights[r] = max(heights[r], d.cell_height(r, c, hits))
        hh, vh = self.horizontalHeader(), self.verticalHeader()
        for c, w in enumerate(widths):
            hh.resizeSection(c, max(110, w, hh.sectionSizeFromContents(c).width()))
        for r, h in enumerate(heights):
            vh.resizeSection(r, max(h, vh.sectionSizeFromContents(r).height()))
        if layout.cols:                    # its height follows the widths just set (one line or two)
            hh.headerDataChanged(Qt.Horizontal, 0, len(layout.cols) - 1)
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

    # ---- hit testing -----------------------------------------------------
    def _hit(self, pos):
        idx = self.indexAt(pos)
        if not idx.isValid():
            return None
        r, c = idx.row(), idx.column()
        hits = self.model_.layout_.tokens(r, c)
        rect = self.visualRect(idx)
        n = self.delegate.block_at(r, c, hits, pos.x() - rect.left()) if hits else -1
        return r, c, n

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        hit = self._hit(event.position().toPoint())
        if hit:
            self.selected = hit if hit[2] >= 0 else (hit[0], hit[1], -1)
            self.viewport().update()
            self.tokenClicked.emit(*hit)

    def mouseDoubleClickEvent(self, event):
        hit = self._hit(event.position().toPoint())
        if hit:
            self.cellActivated.emit(*hit)

    def _context(self, pos):
        hit = self._hit(pos)
        if hit:
            self.selected = hit
            self.setCurrentIndex(self.model_.index(hit[0], hit[1]))
            self.viewport().update()
            self.contextRequested.emit(*hit, self.viewport().mapToGlobal(pos))

    def keyboardSearch(self, search: str):
        """No type-to-jump: IPA takes several keystrokes per symbol, so jumping only confuses (Josh, 19 October)."""

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            idx = self.currentIndex()
            if idx.isValid():
                n = self.selected[2] if self.selected and self.selected[:2] == (idx.row(), idx.column()) else 0
                hits = self.model_.layout_.tokens(idx.row(), idx.column())
                self.cellActivated.emit(idx.row(), idx.column(), n if hits else -1)
                return
        if event.key() == Qt.Key_Delete:
            self.deleteRequested.emit()
            return
        if event.key() == Qt.Key_Space and not event.modifiers():
            self.playRequested.emit()
            return
        super().keyPressEvent(event)
        idx = self.currentIndex()
        if idx.isValid() and (not self.selected or self.selected[:2] != (idx.row(), idx.column())):
            hits = self.model_.layout_.tokens(idx.row(), idx.column())
            self.selected = (idx.row(), idx.column(), 0 if hits else -1)
            self.viewport().update()

    def selected_token(self):
        """(entry, token) for the selected token, or None."""
        if not self.selected:
            return None
        r, c, n = self.selected
        hits = self.model_.layout_.tokens(r, c)
        if 0 <= n < len(hits):
            return hits[n]
        return None
