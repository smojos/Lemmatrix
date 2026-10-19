"""A text's lines as cells (agreed with Josh, 19 October).

Each line is a cell with its fields stacked, in the order Configure view sets; the aligned
fields (interlinear, LaTeX-style: spaces separate units, {braces} group, {} is empty) line up
word by word. The symbols are hidden except while a field is being edited. A margin on the
left; long lines scroll sideways; the time (with the speaker, when a text has several, and the
utterances clipped from the line) and the Comment stay pinned at the right edge.

Outside edit mode the lines are things to play, clip and open in Praat. In edit mode a click
on a field (or the Comment) edits it in place: Enter keeps it, Esc drops it, Tab and Shift+Tab
go to the next and previous field (and on into the next line), Up and Down to the same field
of the line above or below, Ctrl+Space plays the line.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QAbstractScrollArea, QDialog, QDialogButtonBox, QLabel,
                               QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from ..interlinear import bare, split_units
from . import searchmark, theme
from .widgets import ipa_font

MARGIN = 24              # the buffer on the left
SIDE_W = 260             # time and Comment, pinned at the right
PAD = 8                  # inside a cell, above and below
GAP = 16                 # between aligned columns
ROW_EXTRA = 6            # a field row's height beyond its font's
TIME_H = 20


@dataclass
class FieldSpec:
    key: str             # "Phonetic", "Translation:en"
    title: str
    ipa: bool = False
    aligned: bool = False
    translation: bool = False


@dataclass
class _Cell:
    y: int
    h: int
    rows: list           # (spec, y offset, height)
    cols: list           # widths of the aligned columns
    width: int


def shown(text: str) -> str:
    """A field's text as shown: the glossing symbols hidden ({big dog} → big dog, {} → nothing)."""
    if "{" not in (text or ""):
        return text or ""
    return " ".join(b for b in (bare(u) for u in split_units(text)) if b)


class LinesView(QAbstractScrollArea):
    playRequested = Signal()
    contextRequested = Signal(object, object)     # the line (or None), global position
    clipActivated = Signal(object)                # double-click on a line's utterances
    editCommitted = Signal(object, str, str)      # line, field key, new text
    currentChanged = Signal(object)               # a line chosen with the mouse or keys
    countChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list = []                      # every line of the text
        self._visible: list = []                  # those the search leaves
        self.fields: list[FieldSpec] = []
        self.comment_key = ""
        self.clips: dict = {}                     # line id -> references of utterances clipped from it
        self.show_speaker = False
        self.edit_mode = False
        self.space_plays = True
        self._search = ""
        self._cells: list[_Cell] = []
        self._tops: list[int] = []
        self._current = None                      # a line id
        self._selected: set = set()               # line ids
        self._anchor = None
        self._editor = None                       # (QLineEdit, line id, key, original text)
        self.menu_key = ""                        # the field right-clicked last
        self.ipa = ipa_font(15)
        self.plain = QFont(self.font())
        self.plain.setPointSizeF(self.plain.pointSizeF() * 1.1)
        self.small = QFont(self.font())
        self.small.setPointSizeF(max(7.0, self.small.pointSizeF() * 0.9))
        self.setFocusPolicy(Qt.StrongFocus)
        self.viewport().setMouseTracking(False)
        self.horizontalScrollBar().setSingleStep(24)
        self.verticalScrollBar().setSingleStep(24)
        theme.as_data(self)

    # ---- data ---------------------------------------------------------------
    def set_fields(self, specs: list[FieldSpec], comment_key: str = ""):
        self._close_editor(commit=True)
        self.fields = list(specs)
        self.comment_key = comment_key
        self._relayout()

    def set_lines(self, lines, clips=None, show_speaker=False):
        """Show these lines; the current and selected ones stay by their times."""
        editing = self._editor
        self.rows = list(lines)
        self.clips = clips or {}
        self.show_speaker = show_speaker
        ids = {ln.id for ln in self.rows}
        self._selected &= ids
        if self._current not in ids:
            self._current = None
        if editing is not None and editing[1] not in ids:
            self._close_editor(commit=False)
        self._filter()

    def set_search(self, text: str):
        self._search = searchmark.fold_query((text or "").strip())   # as the grids' searches
        self._filter()

    def set_edit_mode(self, on: bool):
        self._close_editor(commit=True)
        self.edit_mode = bool(on)
        self.viewport().update()

    def value(self, line, key: str) -> str:
        return line.values.get(key, "") if key else ""

    def _matches(self, line) -> bool:
        if not self._search:
            return True
        hay = searchmark.fold_query(" ".join(list(line.values.values()) + [line.speaker]))
        return self._search in hay or self._search in shown(hay)

    def _filter(self):
        self._visible = [ln for ln in self.rows if self._matches(ln)]
        self._relayout()
        self.countChanged.emit()

    # ---- selection ----------------------------------------------------------------
    def visible_rows(self) -> list:
        return list(self._visible)

    def current_row(self):
        return next((ln for ln in self._visible if ln.id == self._current), None)

    def selected(self) -> list:
        """The selected lines in time order (the current one if none is selected)."""
        out = [ln for ln in self._visible if ln.id in self._selected]
        if not out and self.current_row() is not None:
            out = [self.current_row()]
        return out

    def select_row(self, line, add: bool = False):
        if line is None:
            return
        self._current = line.id
        if not add:
            self._selected = set()
        self._selected.add(line.id)
        self._anchor = line.id
        self._scroll_to(line.id)
        self.viewport().update()

    def selectAll(self):
        self._selected = {ln.id for ln in self._visible}
        self.viewport().update()

    def clearSelection(self):
        self._selected = set()
        self._current = None
        self.viewport().update()

    def _index(self, line_id) -> int | None:
        return next((i for i, ln in enumerate(self._visible) if ln.id == line_id), None)

    # ---- layout ---------------------------------------------------------------------
    def _font(self, spec: FieldSpec) -> QFont:
        return self.ipa if spec.ipa else self.plain

    def _row_h(self, spec: FieldSpec) -> int:
        return QFontMetrics(self._font(spec)).height() + ROW_EXTRA

    def _display(self, line, spec: FieldSpec) -> str:
        text = shown(self.value(line, spec.key))
        return f"‘{text}’" if spec.translation and text else text

    def _units(self, line, spec: FieldSpec) -> list[str]:
        return [bare(u) for u in split_units(self.value(line, spec.key))]

    def _cell(self, line, y: int) -> _Cell:
        rows, cols, top = [], [], PAD
        width = 0
        aligned = [s for s in self.fields if s.aligned]
        for s in aligned:                         # the aligned columns: the widest unit in each
            fm = QFontMetrics(self._font(s))
            for i, u in enumerate(self._units(line, s)):
                w = fm.horizontalAdvance(u) + GAP
                if i < len(cols):
                    cols[i] = max(cols[i], w)
                else:
                    cols.append(w)
        for s in self.fields:
            h = self._row_h(s)
            rows.append((s, top, h))
            top += h
            if s.aligned:
                width = max(width, sum(cols))
            else:
                width = max(width, QFontMetrics(self._font(s)).horizontalAdvance(self._display(line, s)))
        fields_h = top + PAD
        comment = self.value(line, self.comment_key)
        fm = QFontMetrics(self.small)
        box_w = SIDE_W - 20
        text_h = fm.boundingRect(QRect(0, 0, box_w - 12, 2000), Qt.TextWordWrap, comment).height() if comment else 0
        side_h = PAD + TIME_H + max(38, text_h + 14) + PAD
        return _Cell(y, max(fields_h, side_h, 44), rows, cols, width)

    def _relayout(self):
        self._cells, self._tops = [], []
        y = 0
        for ln in self._visible:
            c = self._cell(ln, y)
            self._cells.append(c)
            self._tops.append(y)
            y += c.h + 1
        self._content_h = y
        self._content_w = MARGIN + max((c.width for c in self._cells), default=0) + 32 + SIDE_W
        self._update_bars()
        self._place_editor()
        self.viewport().update()

    def _update_bars(self):
        vp = self.viewport()
        self.verticalScrollBar().setPageStep(vp.height())
        self.verticalScrollBar().setRange(0, max(0, self._content_h - vp.height()))
        self.horizontalScrollBar().setPageStep(vp.width())
        self.horizontalScrollBar().setRange(0, max(0, getattr(self, "_content_w", 0) - vp.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_bars()
        self._place_editor()

    def scrollContentsBy(self, dx, dy):
        self._place_editor()
        self.viewport().update()

    def _scroll_to(self, line_id):
        i = self._index(line_id)
        if i is None:
            return
        c = self._cells[i]
        sb = self.verticalScrollBar()
        if c.y < sb.value():
            sb.setValue(c.y)
        elif c.y + c.h > sb.value() + self.viewport().height():
            sb.setValue(c.y + c.h - self.viewport().height())

    # ---- geometry --------------------------------------------------------------------
    def _side_x(self) -> int:
        return max(MARGIN + 120, self.viewport().width() - SIDE_W)

    def _field_rect(self, i: int, key: str) -> QRect | None:
        c = self._cells[i]
        top = c.y - self.verticalScrollBar().value()
        if key == self.comment_key and key:
            x = self._side_x() + 10
            return QRect(x, top + PAD + TIME_H, SIDE_W - 20, max(30, c.h - PAD * 2 - TIME_H))
        for s, oy, h in c.rows:
            if s.key == key:                      # from the field's start to the side, at least 220 wide
                x = MARGIN - self.horizontalScrollBar().value() - 4
                return QRect(x, top + oy - 1, max(220, self._side_x() - 8 - x), h + 2)
        return None

    def _hit(self, pos) -> tuple[int | None, str]:
        """(visible line index, what: a field key, "comment", "clips", "side" or "")."""
        y = pos.y() + self.verticalScrollBar().value()
        i = bisect.bisect_right(self._tops, y) - 1
        if i < 0 or i >= len(self._cells) or y > self._cells[i].y + self._cells[i].h:
            return None, ""
        c = self._cells[i]
        if pos.x() >= self._side_x():
            if pos.y() + self.verticalScrollBar().value() < c.y + PAD + TIME_H:
                return i, "clips" if self.clips.get(self._visible[i].id) else "side"
            return i, "comment" if self.comment_key else "side"
        oy = y - c.y
        for s, top, h in c.rows:
            if top <= oy < top + h:
                return i, s.key
        return i, ""

    # ---- painting ----------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        base, text = pal.base().color(), pal.text().color()
        dim, accent = theme.colour("dim"), theme.accent()
        p.fillRect(self.viewport().rect(), base)
        vy, vx = self.verticalScrollBar().value(), self.horizontalScrollBar().value()
        h = self.viewport().height()
        first = max(0, bisect.bisect_right(self._tops, vy) - 1)
        side_x = self._side_x()
        line_col = theme.mix(base, text, 0.12)
        for i in range(first, len(self._cells)):
            c = self._cells[i]
            top = c.y - vy
            if top > h:
                break
            ln = self._visible[i]
            sel, cur = ln.id in self._selected, ln.id == self._current
            if sel or cur:
                p.fillRect(QRect(0, top, side_x, c.h), theme.mix(base, accent, 0.16 if sel else 0.07))
            x0 = MARGIN - vx
            for s, oy, rh in c.rows:
                y = top + oy
                if self.edit_mode:                # edit mode: each field shows as a box to type in
                    box = QRectF(x0 - 4, y + 1, max(c.width + 24, 220), rh - 2)
                    p.setPen(QPen(theme.mix(base, text, 0.18), 1))
                    p.setBrush(theme.mix(base, QColor("white") if not theme.dark() else QColor("black"), 0.5))
                    p.drawRoundedRect(box, 3, 3)
                p.setFont(self._font(s))
                if s.aligned:
                    x = x0
                    p.setPen(text)
                    fm = p.fontMetrics()
                    for w, u in zip(c.cols, self._units(ln, s)):
                        p.drawText(QRect(x, y, w, rh), Qt.AlignVCenter | Qt.AlignLeft, u)
                        if self._search:
                            searchmark.mark_text(p, x, y + (rh - fm.height()) / 2, fm.height(), u, self._search, fm)
                        x += w
                    if not self.value(ln, s.key) and self.edit_mode:
                        p.setPen(dim)
                        p.setFont(self.small)
                        p.drawText(QRect(x0, y, 300, rh), Qt.AlignVCenter, s.title)
                else:
                    t = self._display(ln, s)
                    if t:
                        p.setPen(text)
                        p.drawText(QRect(x0, y, c.width + 40, rh), Qt.AlignVCenter | Qt.AlignLeft, t)
                        if self._search:
                            fm = p.fontMetrics()
                            searchmark.mark_text(p, x0, y + (rh - fm.height()) / 2, fm.height(), t, self._search, fm)
                    elif self.edit_mode:
                        p.setPen(dim)
                        p.setFont(self.small)
                        p.drawText(QRect(x0, y, 300, rh), Qt.AlignVCenter, s.title)
            # the side, pinned at the right: time (speaker, clipped utterances) and the Comment
            p.fillRect(QRect(side_x, top, SIDE_W, c.h), theme.mix(base, accent, 0.10) if sel or cur else base)
            p.setPen(QPen(line_col, 1))
            p.drawLine(side_x, top + 4, side_x, top + c.h - 4)
            p.setFont(self.small)
            p.setPen(dim)
            from .texts import clock
            head = f"{clock(ln.start)} – {clock(ln.end)}"
            if self.show_speaker and ln.speaker:
                head += f"   {ln.speaker}"
            p.drawText(QRect(side_x + 10, top + PAD - 2, SIDE_W - 20, TIME_H), Qt.AlignVCenter, head)
            refs = self.clips.get(ln.id)
            if refs:
                p.setPen(accent)
                p.drawText(QRect(side_x + 10, top + PAD - 2, SIDE_W - 20, TIME_H), Qt.AlignVCenter | Qt.AlignRight,
                           ", ".join(refs))
            if self.comment_key:
                box = QRectF(side_x + 10, top + PAD + TIME_H, SIDE_W - 20, max(30, c.h - PAD * 2 - TIME_H))
                p.setPen(QPen(theme.mix(base, text, 0.25), 1))
                p.setBrush(base)
                p.drawRoundedRect(box, 3, 3)
                comment = self.value(ln, self.comment_key)
                p.setPen(text if comment else dim)
                inner = box.adjusted(6, 4, -6, -4)
                p.drawText(inner.toRect(), Qt.TextWordWrap | Qt.AlignTop,
                           comment or ("Comment" if self.edit_mode else ""))
                if comment and self._search:
                    searchmark.mark_wrapped(p, inner, comment, self._search)
            p.setPen(QPen(line_col, 1))
            p.drawLine(0, top + c.h, self.viewport().width(), top + c.h)
        if not self._visible:
            p.setPen(dim)
            p.setFont(self.plain)
            p.drawText(self.viewport().rect().adjusted(MARGIN, 20, -20, 0), Qt.AlignTop | Qt.AlignLeft,
                       "No lines match the search." if self.rows else "")
        p.end()

    # ---- mouse and keys -------------------------------------------------------------------
    def mousePressEvent(self, event):
        self.setFocus()
        i, what = self._hit(event.position().toPoint())
        if i is None:
            return super().mousePressEvent(event)
        ln = self._visible[i]
        if event.button() == Qt.RightButton:
            if ln.id not in self._selected:
                self.select_row(ln)
            return
        mods = event.modifiers()
        if mods & Qt.ControlModifier:
            self._selected ^= {ln.id}
            self._current = ln.id
        elif mods & Qt.ShiftModifier and self._anchor is not None:
            a, b = self._index(self._anchor), i
            if a is not None:
                lo, hi = sorted((a, b))
                self._selected = {x.id for x in self._visible[lo:hi + 1]}
            self._current = ln.id
        else:
            self.select_row(ln)
            if self.edit_mode and what not in ("", "side", "clips"):
                self._start_edit(ln.id, self.comment_key if what == "comment" else what)
        self.viewport().update()
        self.currentChanged.emit(ln)

    def mouseDoubleClickEvent(self, event):
        i, what = self._hit(event.position().toPoint())
        if i is None:
            return
        ln = self._visible[i]
        if what == "clips":
            self.clipActivated.emit(ln)
        elif not self.edit_mode:
            self.select_row(ln)
            self.playRequested.emit()

    def contextMenuEvent(self, event):
        i, what = self._hit(event.pos())
        # the field under the mouse, for the menu's Edit item ("" outside a field)
        self.menu_key = (self.comment_key if what == "comment" else
                         "" if what in ("", "side", "clips") else what) if i is not None else ""
        self.contextRequested.emit(self._visible[i] if i is not None else None, event.globalPos())

    def keyPressEvent(self, event):
        k, mods = event.key(), event.modifiers()
        if k in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_Home, Qt.Key_End):
            self._move(k)
            return
        if k == Qt.Key_Space and not (mods & ~Qt.KeypadModifier) and self.space_plays:
            self.playRequested.emit()
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            cur = self.current_row()
            if cur is not None and self.edit_mode and self._keys():
                self._start_edit(cur.id, self._keys()[0])
            elif cur is not None:
                self.playRequested.emit()
            return
        if k == Qt.Key_A and mods & Qt.ControlModifier:
            self.selectAll()
            return
        super().keyPressEvent(event)

    def _move(self, k):
        if not self._visible:
            return
        i = self._index(self._current)
        n = len(self._visible)
        step = max(1, self.viewport().height() // 90)
        j = {Qt.Key_Up: (i - 1) if i is not None else 0, Qt.Key_Down: (i + 1) if i is not None else 0,
             Qt.Key_PageUp: (i or 0) - step, Qt.Key_PageDown: (i or 0) + step,
             Qt.Key_Home: 0, Qt.Key_End: n - 1}[k]
        j = max(0, min(n - 1, j))
        self.select_row(self._visible[j])
        self.currentChanged.emit(self._visible[j])

    # ---- editing ----------------------------------------------------------------------------
    def title(self, key: str) -> str:
        if key and key == self.comment_key:
            return "Comment"
        return next((s.title for s in self.fields if s.key == key), key)

    def _keys(self) -> list[str]:
        return [s.key for s in self.fields] + ([self.comment_key] if self.comment_key else [])

    def editing(self) -> bool:
        return self._editor is not None

    def start_edit(self, line, key: str):
        self.select_row(line)
        self._start_edit(line.id, key)

    def _start_edit(self, line_id, key: str):
        self._close_editor(commit=True)
        i = self._index(line_id)
        if i is None or not key:
            return
        self._current = line_id
        self._scroll_to(line_id)
        ln = self._visible[i]
        ed = QLineEdit(self.viewport())
        spec = next((s for s in self.fields if s.key == key), None)
        ed.setFont(self._font(spec) if spec is not None else self.small)
        original = self.value(ln, key)
        ed.setText(original)                       # the symbols show while editing
        ed.installEventFilter(self)
        ed.editingFinished.connect(lambda: self._finished(ed))
        self._editor = (ed, line_id, key, original)
        self._place_editor()
        ed.show()
        ed.setFocus()
        ed.end(False)
        self.viewport().update()

    def _place_editor(self):
        if self._editor is None:
            return
        ed, line_id, key, _ = self._editor
        i = self._index(line_id)
        r = self._field_rect(i, key) if i is not None else None
        if r is None:
            return
        ed.setGeometry(r)

    def _finished(self, ed):
        if self._editor is not None and self._editor[0] is ed and not getattr(self, "_moving", False):
            self._close_editor(commit=True)

    def _close_editor(self, commit: bool, then=None):
        if self._editor is None:
            return
        ed, line_id, key, original = self._editor
        self._editor = None
        text = ed.text()
        ed.removeEventFilter(self)
        ed.hide()
        ed.deleteLater()
        line = next((ln for ln in self.rows if ln.id == line_id), None)
        if commit and line is not None and text.strip() != (original or "").strip():
            self.editCommitted.emit(line, key, text)
        self.setFocus()
        if then is not None:
            self._start_edit(*then)
        self.viewport().update()

    def _next_target(self, line_id, key, step: int, vertical: bool = False):
        keys = self._keys()
        i = self._index(line_id)
        if i is None or key not in keys:
            return None
        if vertical:
            j = i + step
            return (self._visible[j].id, key) if 0 <= j < len(self._visible) else None
        k = keys.index(key) + step
        if 0 <= k < len(keys):
            return line_id, keys[k]
        j = i + (1 if step > 0 else -1)
        if 0 <= j < len(self._visible):
            return self._visible[j].id, keys[0] if step > 0 else keys[-1]
        return None

    def eventFilter(self, obj, event):
        if self._editor is not None and obj is self._editor[0] and event.type() == QEvent.KeyPress:
            k, mods = event.key(), event.modifiers()
            _, line_id, key, _ = self._editor
            if k == Qt.Key_Space and mods & Qt.ControlModifier:     # plays; never types a space
                self.playRequested.emit()
                return True
            if k == Qt.Key_Escape:
                self._close_editor(commit=False)
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._close_editor(commit=True)
                return True
            move = None
            if k == Qt.Key_Tab:
                move = self._next_target(line_id, key, 1)
            elif k == Qt.Key_Backtab:
                move = self._next_target(line_id, key, -1)
            elif k in (Qt.Key_Down, Qt.Key_Up):
                move = self._next_target(line_id, key, 1 if k == Qt.Key_Down else -1, vertical=True)
            if k in (Qt.Key_Tab, Qt.Key_Backtab, Qt.Key_Down, Qt.Key_Up):
                self._moving = True
                try:
                    self._close_editor(commit=True, then=move)
                finally:
                    self._moving = False
                if move is not None and k in (Qt.Key_Down, Qt.Key_Up):
                    ln = next((x for x in self._visible if x.id == move[0]), None)
                    if ln is not None:
                        self.currentChanged.emit(ln)
                return True
        return super().eventFilter(obj, event)


class ConfigureViewDialog(QDialog):
    """Configure view: which fields each line shows, in what order (drag), and which line up
    word by word (interlinear). One setting for every text; the Comment is always at the side."""

    def __init__(self, parent, choices: list[tuple[str, str, bool]], specs: list[FieldSpec]):
        super().__init__(parent)
        self.setWindowTitle("Configure view")
        self.resize(420, 420)
        lay = QVBoxLayout(self)
        note = QLabel("Tick what each line shows, and drag to reorder. Fields ticked in “Line up” are "
                      "aligned word by word, as in LaTeX glossing: spaces separate the units, "
                      "{braces} group several words into one, and {} is an empty one.")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Field", "Line up"])
        self.tree.setRootIsDecorated(False)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        shown = {s.key: s for s in specs}
        titles = {k: t for k, t, _ in choices}
        order = [s.key for s in specs if s.key in titles] + [k for k, _, _ in choices if k not in shown]
        for k in order:
            it = QTreeWidgetItem([titles[k], ""])
            it.setData(0, Qt.UserRole, k)
            it.setFlags((it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled) & ~Qt.ItemIsDropEnabled)
            it.setCheckState(0, Qt.Checked if k in shown else Qt.Unchecked)
            it.setCheckState(1, Qt.Checked if k in shown and shown[k].aligned else Qt.Unchecked)
            self.tree.addTopLevelItem(it)
        self.tree.resizeColumnToContents(0)
        lay.addWidget(self.tree, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def chosen(self) -> tuple[list[str], list[str]]:
        keys, aligned = [], []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == Qt.Checked:
                keys.append(it.data(0, Qt.UserRole))
                if it.checkState(1) == Qt.Checked:
                    aligned.append(it.data(0, Qt.UserRole))
        return keys, aligned
