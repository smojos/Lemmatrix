# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
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
from ..model import Database, is_utterance
from .icons import icon
from . import conventions, theme, widgets
from .viewmixins import ClickUnselect, WheelZoom
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
    zoom = 1.0           # the view's Ctrl + mouse wheel zoom (the lemma headers' font follows it)

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
        if role == Qt.UserRole + 2:                # a lemma's header (its width is capped)
            return it.entry is not None
        if role == Qt.FontRole and it.entry is not None:
            return ipa_font(round(13 * self.zoom))
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
        self.setTextElideMode(Qt.ElideRight)       # a long lemma ends in … (its width is capped)
        f = self.font()
        self.chip_font = QFont(f)
        self._base_pt = f.pointSizeF()

    def set_zoom(self, zoom: float):
        self.chip_font.setPointSizeF(self._base_pt * zoom)
        f = QFont(self.font())                   # the headers' own labels (Citation, a lemma's form)
        f.setPointSizeF(self._base_pt * zoom)
        self.setFont(f)

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
    LEMMA_WIDTH = 110      # the widest a lemma's header across the top grows (a column's default width)

    def sectionSizeFromContents(self, index):
        s = super().sectionSizeFromContents(index)
        chips = self._chips(index)
        if chips is None:
            m = self.model()
            if m is not None and m.headerData(index, self.orientation(), Qt.UserRole + 2):
                # a long lemma or gloss doesn't stretch its row header or column (Josh, 24 October):
                # no wider than the default, the rest elided (the hover has it all)
                zoom = self.chip_font.pointSizeF() / self._base_pt if self._base_pt else 1.0
                cap = round((self.WRAP_WIDTH if self.orientation() == Qt.Vertical else self.LEMMA_WIDTH) * zoom)
                if s.width() > cap:
                    s = QSize(cap, s.height())
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
        self._base_pt = view.font().pointSizeF()
        self.set_zoom(1.0)

    def set_zoom(self, zoom: float):
        """Fonts and the pitch drawing at the view's zoom (Ctrl + mouse wheel)."""
        from . import widgets                   # the IPA size of Settings → Display, zoomed
        self.ipa = ipa_font(round(widgets.IPA_SIZE * zoom))
        self.plain = QFont(self.view.font())
        self.plain.setPointSizeF(self._base_pt * zoom)
        self.small = QFont(self.view.font())
        self.small.setPointSizeF(max(7.0, (self._base_pt - 1.5) * zoom))
        self.unit = underscore_unit(self.ipa)
        self.draw_h = round(22 * zoom)          # the pitch drawing's height, and its row's (+4)

    # ---- geometry --------------------------------------------------------
    def _lines(self):
        return [f for f in self.view.cell_fields if f != "drawing"]

    UNIT_GAP = 12        # between lined-up units (idea 2)

    def _role(self, name) -> str:
        f = self.view.db.settings.token_field(name.partition(":")[0])
        return f.role if f is not None else ""

    # ---- one layout pass's memory (set_layout): the same answers worked out once each --------
    # Measuring every cell to size the columns asked the same questions (a token's text and units,
    # a text's width, a tag set's chips) hundreds of thousands of times at full size (25 October).
    # Nothing can change during one pass, and the memory is let go when it ends.
    _memo: dict | None = None

    def begin_pass(self):
        self._memo = {}

    def end_pass(self):
        self._memo = None

    def _m(self, key, fn):
        memo = self._memo
        if memo is None:
            return fn()
        if key in memo:
            return memo[key]
        v = memo[key] = fn()
        return v

    def _text(self, t, name):
        """A line's text as shown: the glossing symbols hidden ({big dog} → big dog), the display
        conventions on (idea 26)."""
        from .lines_view import shown
        return self._m(("text", id(t), name), lambda: conventions.wrap(
            self._role(name), shown(mx.cell_text(self.view.db, t, name))))

    def _w(self, name, text) -> int:
        return self._m(("w", name, text), lambda: conventions.width(
            text, self._font(name), conventions.small_caps_on(self._role(name))))

    def _aligned(self, name) -> bool:
        return self._m(("aligned", name), lambda: mx.is_aligned(self.view.db, name, self.view.aligned))

    def _units(self, t, name) -> list[str]:
        from ..interlinear import bare, split_units
        return self._m(("units", id(t), name), lambda: conventions.wrap_units(
            self._role(name), [bare(u) for u in split_units(mx.cell_text(self.view.db, t, name))]))

    def _cols(self, t) -> list[int]:
        """The lined-up columns of a token: each the widest unit at that place in its aligned lines."""
        cols: list[int] = []
        for name in self._lines():
            if not self._aligned(name) or self._role(name) == "constituents":   # drawn over them (idea 91)
                continue
            for i, u in enumerate(self._units(t, name)):
                w = self._w(name, u) + self.UNIT_GAP
                if i < len(cols):
                    cols[i] = max(cols[i], w)
                else:
                    cols.append(w)
        return cols

    def _font(self, name):
        return self.ipa if name in IPA_FIELDS else self.plain

    def chips_for(self, r, c, t):
        lay = self.view.model_.layout_
        spec = lay.spec_at(r, c)
        entry, _ = lay.target(r, c)
        # a lemma's chips depend on it only through its word class (what's unusual, and the note)
        who = ((self.view.db.word_class(entry), is_utterance(entry))
               if entry is not None and self._memo is not None else id(entry))
        return self._m(("chips", id(spec), entry is None, who, tuple(t.tags)),
                       lambda: self._chips_for(lay, spec, entry, t))

    def _chips_for(self, lay, spec, entry, t):
        db = self.view.db
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
                w = self._m(("pitch", t.get("Pitch"), self.unit), lambda: pitch_width(t.get("Pitch"), self.unit))
            cols = self._m(("cols", id(t)), lambda: self._cols(t))
            for name in self._lines():
                if self._cons_drawn(t, name, cols):
                    w = max(w, sum(cols) - self.UNIT_GAP)
                elif self._aligned(name) and self._units(t, name) and self._role(name) != "constituents":
                    w = max(w, sum(cols) - self.UNIT_GAP)
                else:
                    w = max(w, self._w(name, self._text(t, name) or "—"))
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
            h += self.draw_h + 4
        for name in self._lines():
            h += self._line_h(name, hits) + 1
        return h

    def _cons_drawn(self, t, name, cols) -> bool:
        """Whether a token's Constituents line is drawn as brackets over its lined-up words (idea 91)."""
        if self._role(name) != "constituents" or self.view.edit_mode or not cols:
            return False
        from . import constituents_draw as cd
        return cd.drawable(mx.cell_text(self.view.db, t, name), len(cols))

    def _line_h(self, name, hits) -> int:
        """A line's height in a cell: its font's, or the Constituents drawing's (the tallest of the
        cell's tokens)."""
        base = self._m(("h", name), lambda: QFontMetrics(self._font(name)).height())
        if self._role(name) != "constituents" or self.view.edit_mode:
            return base
        from . import constituents_draw as cd
        for _, t in hits:
            cols = self._m(("cols", id(t)), lambda t=t: self._cols(t))
            if self._cons_drawn(t, name, cols):
                base = max(base, cd.height(mx.cell_text(self.view.db, t, name), self.small))
        return base

    def cell_width(self, r, c, hits) -> int:
        widths = self.block_widths(r, c, hits)
        return PAD * 2 + sum(widths) + GAP * max(0, len(widths) - 1)

    def line_rects(self, r, c, hits, rect) -> list:
        """(token number, line key, QRect) for every field line drawn in a cell (edit mode, Ctrl+E)."""
        out = []
        widths = self.block_widths(r, c, hits)
        chip_row = self.chip_row_needed(r, c, hits)
        x = rect.left() + PAD
        for n, w in enumerate(widths):
            y = rect.top() + PAD
            if chip_row:
                y += chip_metrics(self.small)[1] + 4
            if "drawing" in self.view.cell_fields:
                y += self.draw_h + 4
            for name in self._lines():
                h = self._line_h(name, hits)
                out.append((n, name, QRect(int(x), int(y), int(w - SOUND_W) + 2, h)))
                y += h + 1
            x += w + GAP
        return out

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
                draw_pitch(painter, QRectF(x, y, w, self.draw_h), t.get("Pitch"), db.settings.pitch_low,
                           db.settings.pitch_high, width=2.2, unit=self.unit)
                y += self.draw_h + 4
            cols = self._cols(t)
            for name in self._lines():
                font = self._font(name)
                fm = QFontMetrics(font)
                lh = self._line_h(name, hits)
                text = self._text(t, name)
                if self._cons_drawn(t, name, cols):      # brackets over the words (idea 91)
                    from . import constituents_draw as cd
                    cd.paint(painter, x, y, cols, mx.cell_text(db, t, name), self.small,
                             theme.colour("text"), self.UNIT_GAP)
                    y += lh + 1
                    continue
                if self.view.edit_mode:           # edit mode (Ctrl+E): each line shows as a box to type in
                    painter.setPen(QPen(theme.colour("faint"), 1))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRoundedRect(QRectF(x - 2, y, w - SOUND_W + 6, fm.height()), 3, 3)
                painter.setFont(font)
                painter.setPen(theme.colour("text") if text else theme.colour("faint"))
                units = self._units(t, name) if self._aligned(name) and self._role(name) != "constituents" else []
                if units:                         # word by word, under each other (idea 2)
                    ux = x
                    caps = conventions.small_caps_on(self._role(name))
                    for cw, u in zip(cols, units):
                        conventions.draw(painter, QRect(int(ux), int(y), int(cw) + 2, fm.height()),
                                         Qt.AlignLeft | Qt.AlignVCenter, u, font, caps)
                        ux += cw
                else:
                    conventions.draw(painter, QRect(int(x), int(y), int(w) + 2, fm.height()),
                                     Qt.AlignLeft | Qt.AlignVCenter, text or "—", font,
                                     bool(text) and conventions.small_caps_on(self._role(name)))
                y += lh + 1
            draw_sound_mark(painter, x + w - SOUND_W + 2, rect.top() + PAD, state)
            x += w + GAP
        painter.restore()

    def sizeHint(self, option, index):
        hits = index.data(Qt.UserRole) or []
        if not hits:
            return QSize(110, 40)
        return QSize(self.cell_width(index.row(), index.column(), hits),
                     self.cell_height(index.row(), index.column(), hits))


class MatrixView(WheelZoom, ClickUnselect, QTableView):
    tokenClicked = Signal(int, int, int)      # row, column, token number in cell (-1: none)
    fieldEdited = Signal(object, object, str, str)   # entry, token, line key, new text (edit mode)
    cellActivated = Signal(int, int, int)     # double-click / Enter
    contextRequested = Signal(int, int, int, object)
    deleteRequested = Signal()
    switchRequested = Signal()
    columnMoved = Signal(int, int)            # a column dragged from one place to another (its config line)
    playRequested = Signal()                  # spacebar
    entryActivated = Signal(object)           # a lemma's header double-clicked (on either axis)

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.defaults = mx.default_names(db)
        self.cell_fields = list(mx.DEFAULT_CELL)
        self.aligned: set[str] = set()          # the lines that line up word by word (idea 2)
        self.edit_mode = False                  # Ctrl+E: a token's fields edited in place in its cell
        self._editor = None                     # (QLineEdit, entry, token, key, original)
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
        self.horizontalHeader().sectionMoved.connect(self._column_dragged)   # drag a column to reorder
        self.zoom = 1.0                          # Ctrl + mouse wheel; not saved: back to 1 when Lemmatrix closes

    def _column_dragged(self, logical: int, old: int, new: int):
        """A column dragged in the header (Josh, 21 October): the header is put back as it was and
        the matrix's own line is moved instead (columnMoved), so the order is the configuration's."""
        hh = self.horizontalHeader()
        hh.blockSignals(True)
        hh.moveSection(new, old)
        hh.blockSignals(False)
        if old != new:
            self.columnMoved.emit(old, new)

    # ---- zoom (Ctrl + mouse wheel, Ctrl+0; Josh, 21 October) -------------
    # (the wheel, Ctrl+0 and the limits: viewmixins.WheelZoom)
    def set_zoom(self, zoom: float):
        zoom = self.clamp_zoom(zoom)
        if abs(zoom - self.zoom) < 1e-6:
            return
        self.zoom = zoom
        self.delegate.set_zoom(zoom)
        self.model_.zoom = zoom
        for hdr in (self.horizontalHeader(), self.verticalHeader()):
            hdr.set_zoom(zoom)
        selected = self.selected
        self.set_layout(self.model_.layout_, self.cell_fields)   # sizes from the content again
        self.selected = selected
        self.viewport().update()

    def _header_activated(self, lines: str, i: int):
        items = getattr(self.model_.layout_, lines, [])
        if 0 <= i < len(items) and items[i].entry is not None:
            self.entryActivated.emit(items[i].entry)

    def set_database(self, db: Database):
        self.db = db
        self.model_.db = db
        self.defaults = mx.default_names(db)

    def set_layout(self, layout: mx.Layout, cell_fields: list[str], changed=None):
        """Show a layout, its columns and rows sized to their cells. changed: the ids of the
        lemmas edited since the last layout (Lemma/Tag after an edit): every other lemma's cells
        keep the sizes measured before, if nothing else that sizes them has changed (fields,
        zoom, fonts, display conventions…); None measures every cell (the audit, section 8: an
        edit to one lemma measured all 2,400 again, about 2 s at full size)."""
        self.cell_fields = list(cell_fields)
        self.defaults = mx.default_names(self.db)
        self.selected = None
        self.model_.set_layout(layout)
        # Columns of tags can be dragged into another order; lemmas along the top (Lemma/Tag swapped)
        # follow the lemma list, so they can't.
        self.horizontalHeader().setSectionsMovable(bool(layout.cols)
                                                   and all(it.entry is None for it in layout.cols))
        # Sizes from the content (faster than letting Qt measure every cell).
        d = self.delegate
        widths = [0] * len(layout.cols)
        z = getattr(self, "zoom", 1.0)
        heights = [round(40 * z)] * len(layout.rows)
        sizes = self._sizes_kept(layout, changed)
        d.begin_pass()
        try:
            for (r, c), hits in layout.cells.items():
                entry, _ = layout.target(r, c)
                key = (layout.spec_at(r, c), tuple(id(t) for _, t in hits))
                kept = sizes.setdefault((id(entry), entry.id if entry is not None else None), {})
                wh = kept.get(key)
                if wh is None:
                    wh = kept[key] = (d.cell_width(r, c, hits), d.cell_height(r, c, hits))
                widths[c] = max(widths[c], wh[0])
                heights[r] = max(heights[r], wh[1])
        finally:
            d.end_pass()
        hh, vh = self.horizontalHeader(), self.verticalHeader()
        for c, w in enumerate(widths):
            hh.resizeSection(c, max(round(110 * z), w, hh.sectionSizeFromContents(c).width()))
        for r, h in enumerate(heights):
            vh.resizeSection(r, max(h, vh.sectionSizeFromContents(r).height()))
        if layout.cols:                    # its height follows the widths just set (one line or two)
            hh.headerDataChanged(Qt.Horizontal, 0, len(layout.cols) - 1)
        self._place_switch()

    def _sizes_kept(self, layout: mx.Layout, changed) -> dict:
        """The cells' sizes measured before, by lemma, then by the cell's tags and tokens: what
        set_layout may use again. Forgotten when anything that sizes a cell other than the lemma's
        own tokens may have changed, and for the lemmas edited since."""
        from dataclasses import astuple
        context = (id(self.db), getattr(self, "zoom", 1.0), self.font().pointSizeF(),
                   tuple(self.cell_fields), frozenset(self.aligned), frozenset(self.defaults),
                   layout.entry is None, widgets.IPA_SIZE, widgets.SHOW_UNUSUAL,
                   astuple(conventions.CURRENT))
        sizes = getattr(self, "_sizes", None)
        if changed is None or sizes is None or context != getattr(self, "_sizes_context", None):
            sizes = self._sizes = {}
            self._sizes_context = context
        else:
            for k in [k for k in sizes if k[0] in changed]:
                del sizes[k]
        return sizes

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
        pos = event.position().toPoint()
        hit = self._hit(pos)
        # A plain click on the selected token unselects it, as in All data (IDEAS.md idea 14, Josh,
        # 24 October); not in edit mode, and not when the click is the first of a double-click.
        self._arm_unselect(
            hit and hit[2] >= 0 and hit == self.selected and not self.edit_mode
            and event.button() == Qt.LeftButton and not event.modifiers())
        super().mousePressEvent(event)
        if hit:
            self.selected = hit if hit[2] >= 0 else (hit[0], hit[1], -1)
            self.viewport().update()
            self.tokenClicked.emit(*hit)
            if self.edit_mode and event.button() == Qt.LeftButton and hit[2] >= 0:
                line = self._line_at(hit, pos)
                if line is not None:
                    self.start_edit(hit[0], hit[1], hit[2], line[1])

    # ---- edit mode (Ctrl+E, 21 October): a field edited in its cell, without the token dialogue
    def set_edit_mode(self, on: bool):
        self._close_editor(commit=True)
        self.edit_mode = bool(on)
        self.viewport().update()

    def _line_at(self, hit, pos):
        r, c, n = hit
        hits = self.model_.layout_.tokens(r, c)
        rect = self.visualRect(self.model_.index(r, c))
        return next(((k, name, q) for k, name, q in self.delegate.line_rects(r, c, hits, rect)
                     if k == n and q.adjusted(-2, -1, 2, 1).contains(pos)), None)

    def start_edit(self, r: int, c: int, n: int, key: str):
        """Edit one line of a cell's token in place: Enter keeps, Esc drops, Tab and Shift+Tab go
        to the next and previous line of the same token."""
        from PySide6.QtWidgets import QLineEdit
        self._close_editor(commit=True)
        hits = self.model_.layout_.tokens(r, c)
        if not (0 <= n < len(hits)):
            return
        e, t = hits[n]
        rect = self.visualRect(self.model_.index(r, c))
        q = next((q for k, name, q in self.delegate.line_rects(r, c, hits, rect) if k == n and name == key), None)
        if q is None:
            return
        ed = QLineEdit(self.viewport())
        from . import keyboards
        keyboards.tag(ed, key)                   # the line's own keyboard (idea 43)
        ed.setFont(self.delegate._font(key))
        original = mx.cell_text(self.db, t, key)
        ed.setText(original)                     # the glossing symbols show while editing
        ed.setGeometry(q.adjusted(-3, -2, 40, 3))
        ed.installEventFilter(self)
        ed.editingFinished.connect(lambda: self._editor is not None and self._editor[0] is ed
                                   and not getattr(self, "_moving", False) and self._close_editor(commit=True))
        self._editor = (ed, e, t, key, original, (r, c, n))
        self.selected = (r, c, n)
        ed.show()
        ed.setFocus()
        ed.end(False)

    def editing(self) -> bool:
        return self._editor is not None

    def fast_paste(self, editor, up: bool, other_role: str, db) -> bool:
        """📋 fast paste (idea 79): this line's text into the other transcription's line of the
        same token, when it is the line above (Shift+Up) or below (Shift+Down); then edit it."""
        from .fastpaste import role
        if self._editor is None or self._editor[0] is not editor:
            return False
        ed, e, t, key, original, place = self._editor
        keys = self.delegate._lines()
        if key not in keys:
            return False
        i = keys.index(key)
        near = keys[:i][::-1] if up else keys[i + 1:]
        other = next((k for k in near if role(db, k) == other_role), None)
        if other is None or (near and near[0] != other):
            return False                        # only the field right above or below
        text = ed.text()
        self._moving = True
        try:
            self._close_editor(commit=True)
            self.fieldEdited.emit(e, t, other, text)
            self.start_edit(*place, other)
        finally:
            self._moving = False
        return True

    def _close_editor(self, commit: bool, then=None):
        if self._editor is None:
            return
        ed, e, t, key, original, place = self._editor
        self._editor = None
        text = ed.text()
        ed.removeEventFilter(self)
        ed.hide()
        ed.deleteLater()
        self.setFocus()
        if commit and text.strip() != (original or "").strip():
            self.fieldEdited.emit(e, t, key, text)
        if then is not None:
            self.start_edit(*place, then)
        self.viewport().update()

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if self._editor is not None and obj is self._editor[0] and event.type() == QEvent.KeyPress:
            k = event.key()
            if k == Qt.Key_Escape:
                self._close_editor(commit=False)
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._close_editor(commit=True)
                return True
            if k in (Qt.Key_Tab, Qt.Key_Backtab):
                keys = self.delegate._lines()
                key = self._editor[3]
                i = keys.index(key) + (1 if k == Qt.Key_Tab else -1) if key in keys else -1
                self._moving = True
                try:
                    self._close_editor(commit=True, then=keys[i] if 0 <= i < len(keys) else None)
                finally:
                    self._moving = False
                return True
        return super().eventFilter(obj, event)

    # (a click on the selected token unselects it: viewmixins.ClickUnselect)
    def _unselect_key(self):
        return self.selected

    def _unselect(self):
        self.selected = None
        self.clearSelection()
        self.viewport().update()

    def mouseDoubleClickEvent(self, event):
        self._cancel_unselect()                   # a double-click opens; it never unselects
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
        if self.zoom_key(event):                  # Ctrl+0: the zoom back to normal
            return
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
