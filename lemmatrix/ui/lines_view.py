# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
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

Ctrl + mouse wheel zooms the view (Ctrl+0 back to normal); the zoom belongs to this view and
goes when the Texts and utterances window is closed (Josh, 21 October). Outside edit mode,
dragging across the words of a field highlights them, for Create token (IDEAS.md idea 31).
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QAbstractScrollArea, QDialog, QDialogButtonBox, QLabel,
                               QLineEdit, QPlainTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from ..interlinear import bare, split_units
from . import conventions, searchmark, theme
from .icons import icon, themed_icon
from .viewmixins import WheelZoom
from .widgets import ipa_font

MARGIN = 40              # the buffer on the left, with room for the bookmark (idea 32; 24 before)
BOOKMARK_W = 14          # the bookmark ribbon in the margin
SIDE_W = 260             # time and Comment, pinned at the right
PAD = 8                  # inside a cell, above and below
GAP = 16                 # between aligned columns
ROW_EXTRA = 6            # a field row's height beyond its font's
TIME_H = 20
PUSH = 20                # the Push to question and Push to To Do buttons in a Comment box (each)
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = WheelZoom.ZOOM_MIN, WheelZoom.ZOOM_MAX, WheelZoom.ZOOM_STEP   # Ctrl + mouse wheel
DRAG = 4                 # pixels the mouse moves before a press becomes a drag over words
EDGE_PUNCT = "‘’“”'\"«».,;:!?"   # stripped from the ends of words taken from a translation


@dataclass
class FieldSpec:
    key: str             # "Phonetic", "Translation:en"
    title: str
    ipa: bool = False
    aligned: bool = False
    translation: bool = False
    role: str = ""       # the token field's role (phonetic, phonemic, morphemes…): the display conventions


@dataclass
class _Cell:
    y: int
    h: int
    rows: list           # (spec, y offset, height)
    cols: list           # widths of the aligned columns
    width: int
    fields_h: int = 0    # the stacked fields' height (the Comment goes under them in the utterance cell)


class CommentEdit(QPlainTextEdit):
    """The Comment box's editor: the text wraps and starts at the top left, as in a chat box
    (Josh, 21 October), with the same few methods as a QLineEdit for the view's editing."""
    editingFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.setTabChangesFocus(True)
        self.document().setDocumentMargin(3)

    def text(self) -> str:
        return " ".join(self.toPlainText().split("\n"))

    def setText(self, text: str):
        self.setPlainText(text or "")

    def end(self, mark: bool = False):
        c = self.textCursor()
        c.movePosition(c.MoveOperation.End)
        self.setTextCursor(c)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()


def shown(text: str) -> str:
    """A field's text as shown: the glossing symbols hidden ({big dog} → big dog, {} → nothing)."""
    if "{" not in (text or ""):
        return text or ""
    return " ".join(b for b in (bare(u) for u in split_units(text)) if b)


class LinesView(WheelZoom, QAbstractScrollArea):
    playRequested = Signal()
    contextRequested = Signal(object, object)     # the line (or None), global position
    clipActivated = Signal(object)                # double-click on a line's utterances
    editCommitted = Signal(object, str, str)      # line, field key, new text
    currentChanged = Signal(object)               # a line chosen with the mouse or keys
    countChanged = Signal()
    pushRequested = Signal(object)                # the ? on a line's Comment: Push to question
    todoRequested = Signal(object)                # the orange flag beside it: Push to To Do (21 October)
    createTokenRequested = Signal(object, str, str)   # line, field key, the words chosen (idea 31)
    bookmarkToggled = Signal(object)              # the margin's bookmark clicked in edit mode (idea 32)

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
        searchmark.on_power(self, lambda: self._search and self._filter())   # idea 86
        self._cells: list[_Cell] = []
        self._tops: list[int] = []
        self._current = None                      # a line id
        self._selected: set = set()               # line ids
        self._anchor = None
        self._editor = None                       # (QLineEdit, line id, key, original text)
        self.menu_key = ""                        # the field right-clicked last
        self._text_sel = None                     # (line id, field key, first word, last word)
        self._drag = None                         # (line id, field key, word, x) while pressing on a field
        self.bookmark = None                      # the id of the text's bookmarked line (idea 32)
        self.bookmarks_enabled = True             # off in the utterance cell (idea 22)
        self.head_fn = None                       # line -> the side's first line (default: its times)
        self.comment_below = False                # the utterance cell: no side; the Comment under the fields
        self.zoom = 1.0                           # Ctrl + mouse wheel (this view's own, not saved)
        self._base_pt = self.font().pointSizeF()
        self._apply_fonts()
        self.setFocusPolicy(Qt.StrongFocus)
        self.viewport().setMouseTracking(False)
        self.horizontalScrollBar().setSingleStep(24)
        self.verticalScrollBar().setSingleStep(24)
        theme.as_data(self)

    # ---- zoom (Ctrl + mouse wheel) ------------------------------------------------
    def _apply_fonts(self):
        z = self.zoom
        from . import widgets                   # a size above the IPA size of Settings → Display
        self.ipa = ipa_font(round((widgets.IPA_SIZE + 2) * z))
        self.plain = QFont(self.font())
        self.plain.setPointSizeF(self._base_pt * 1.1 * z)
        self.small = QFont(self.font())
        self.small.setPointSizeF(max(7.0, self._base_pt * 0.9 * z))

    @property
    def side_w(self) -> int:
        """The pinned side's width (time and Comment), growing with the zoom; none with the Comment below."""
        return 0 if self.comment_below else round(SIDE_W * max(1.0, self.zoom))

    def set_zoom(self, zoom: float):              # (the wheel and Ctrl+0: viewmixins.WheelZoom)
        zoom = self.clamp_zoom(zoom)
        if abs(zoom - self.zoom) < 1e-6:
            return
        self.zoom = zoom
        self._apply_fonts()
        if self._editor is not None:
            ed, _, key, _ = self._editor
            spec = next((s for s in self.fields if s.key == key), None)
            ed.setFont(self._font(spec) if spec is not None else self.plain)
        self._relayout()
        if self._current is not None:
            self._scroll_to(self._current)

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
        if self._text_sel is not None and self._text_sel[0] not in ids:
            self._text_sel = None
        self._filter()

    def set_search(self, text: str):
        self._search = searchmark.fold_query((text or "").strip())   # as the grids' searches
        self._filter()

    def set_edit_mode(self, on: bool):
        self._close_editor(commit=True)
        self.edit_mode = bool(on)
        self._text_sel = None
        self.viewport().update()

    def value(self, line, key: str) -> str:
        return line.values.get(key, "") if key else ""

    def _matches(self, line) -> bool:
        if not self._search:
            return True
        from .. import search
        hay = [searchmark.fold_query(v or "") for v in list(line.values.values()) + [line.speaker]]
        return search.parse(self._search).matches(hay + [shown(h) for h in hay])   # each field alone

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

    def _role(self, spec: FieldSpec) -> str:
        return spec.role or ("translation" if spec.translation else "")

    def _display(self, line, spec: FieldSpec) -> str:
        """A field as shown: the glossing symbols hidden, the display conventions on (idea 26)."""
        return conventions.wrap(self._role(spec), shown(self.value(line, spec.key)))

    def _units(self, line, spec: FieldSpec) -> list[str]:
        return conventions.wrap_units(self._role(spec), [bare(u) for u in split_units(self.value(line, spec.key))])

    def _w(self, spec: FieldSpec, text: str) -> int:
        """How wide a field's text is drawn (small caps included)."""
        return conventions.width(text, self._font(spec), conventions.small_caps_on(self._role(spec)))

    def _draw_text(self, p, rect, spec: FieldSpec, text: str):
        conventions.draw(p, rect, Qt.AlignVCenter | Qt.AlignLeft, text, self._font(spec),
                         conventions.small_caps_on(self._role(spec)))

    def _cell(self, line, y: int) -> _Cell:
        rows, cols, top = [], [], PAD
        width = 0
        aligned = [s for s in self.fields if s.aligned]
        for s in aligned:                         # the aligned columns: the widest unit in each
            for i, u in enumerate(self._units(line, s)):
                w = self._w(s, u) + GAP
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
                width = max(width, self._w(s, self._display(line, s)))
        fields_h = top + PAD
        comment = self.value(line, self.comment_key)
        fm = QFontMetrics(self.plain)                 # the Comment: the same size as the Translation
        box_w = self.side_w - 20
        text_h = fm.boundingRect(QRect(0, 0, box_w - 12 - 2 * PUSH, 2000), Qt.TextWordWrap,
                                 comment).height() if comment else 0
        if self.comment_below:                    # the Comment takes the room left under the fields
            left = self.viewport().height() - fields_h - 1
            return _Cell(y, fields_h + max(self.comment_min(), left), rows, cols, width, fields_h)
        side_h = PAD + self._time_h() + max(fm.height() + 20, text_h + 14) + PAD
        return _Cell(y, max(fields_h, side_h, 44), rows, cols, width, fields_h)

    def comment_min(self) -> int:
        """The Comment box's least height under the fields (two lines of text)."""
        return QFontMetrics(self.plain).height() * 2 + 20 if self.comment_key else 0

    def needed_height(self) -> int:
        """How tall the view must be to show its first cell whole, Comment included."""
        if not self._cells:
            return 0
        return self._cells[0].fields_h + self.comment_min() + 2 * self.frameWidth() + 2

    def _relayout(self):
        self._cells, self._tops = [], []
        y = 0
        for ln in self._visible:
            c = self._cell(ln, y)
            self._cells.append(c)
            self._tops.append(y)
            y += c.h + 1
        self._content_h = y
        self._content_w = MARGIN + max((c.width for c in self._cells), default=0) + 32 + self.side_w
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
        if self.comment_below:                    # the Comment fills what the height leaves
            self._relayout()
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
    def _time_h(self) -> int:
        return max(TIME_H, QFontMetrics(self.small).height() + 4)

    def _side_x(self) -> int:
        if self.comment_below:
            return self.viewport().width()
        return max(MARGIN + 120, self.viewport().width() - self.side_w)

    def _field_rect(self, i: int, key: str) -> QRect | None:
        c = self._cells[i]
        top = c.y - self.verticalScrollBar().value()
        if key == self.comment_key and key:
            return self._comment_box(c, top).toRect()
        for s, oy, h in c.rows:
            if s.key == key:                      # from the field's start to the side, at least 220 wide
                x = MARGIN - self.horizontalScrollBar().value() - 4
                return QRect(x, top + oy - 1, max(220, self._side_x() - 8 - x), h + 2)
        return None

    def _comment_box(self, c, top: float) -> QRectF:
        """A cell's Comment box (top: the cell's top, in the same coordinates as the result)."""
        if self.comment_below:                    # under the fields, as wide as the cell
            return QRectF(MARGIN - 4, top + c.fields_h, max(60, self.viewport().width() - MARGIN - 4),
                          max(30, c.h - c.fields_h - PAD))
        th = self._time_h()
        return QRectF(self._side_x() + 10, top + PAD + th, self.side_w - 20, max(30, c.h - PAD * 2 - th))

    def _push_rect(self, box: QRectF, todo: bool = False) -> QRectF:
        """The Push to question button, at the top right of a Comment box that has a comment; Push to
        To Do (the flag) just left of it."""
        x = box.right() - PUSH - 1 - (PUSH if todo else 0)
        return QRectF(x, box.top() + 3, PUSH - 3, PUSH - 3)

    def _push_hit(self, box: QRectF, pos) -> str:
        """"push", "push-todo" or "" for a point in a Comment box that has a comment."""
        pt = QPointF(pos)
        return "push" if self._push_rect(box).contains(pt) else \
            "push-todo" if self._push_rect(box, True).contains(pt) else ""

    def _bookmark_rect(self, c, top: float) -> QRectF:
        """Where a line's bookmark sits: in the left margin, pinned (it doesn't scroll sideways)."""
        return QRectF((MARGIN - BOOKMARK_W) / 2 - 2, top + PAD, BOOKMARK_W, min(22.0, c.h - 2 * PAD))

    def _paint_bookmark(self, p: QPainter, r: QRectF, golden: bool):
        """A ribbon with a notch: golden for the text's bookmark, a faint shadow for the others (edit mode)."""
        from PySide6.QtGui import QPolygonF
        notch = r.height() * 0.28
        shape = QPolygonF([QPointF(r.left(), r.top()), QPointF(r.right(), r.top()),
                           QPointF(r.right(), r.bottom()), QPointF(r.center().x(), r.bottom() - notch),
                           QPointF(r.left(), r.bottom())])
        if golden:
            gold = theme.bookmark()                 # Settings → Display → Bookmark colour
            p.setPen(QPen(gold.darker(130), 1))
            p.setBrush(gold)
        else:
            shade = QColor(self.palette().text().color())
            shade.setAlphaF(0.13)
            p.setPen(Qt.NoPen)
            p.setBrush(shade)
        p.drawPolygon(shape)

    def bookmark_row(self):
        return next((ln for ln in self._visible if ln.id == self.bookmark), None)

    def set_bookmark(self, line_id):
        self.bookmark = line_id
        self.viewport().update()

    def _hit(self, pos) -> tuple[int | None, str]:
        """(visible line index, what: a field key, "comment", "push", "push-todo", "clips", "side" or "")."""
        y = pos.y() + self.verticalScrollBar().value()
        i = bisect.bisect_right(self._tops, y) - 1
        if i < 0 or i >= len(self._cells) or y > self._cells[i].y + self._cells[i].h:
            return None, ""
        c = self._cells[i]
        if self.bookmarks_enabled and self._bookmark_rect(c, c.y - self.verticalScrollBar().value()).contains(QPointF(pos)):
            return i, "bookmark"
        if self.comment_below and self.comment_key and y - c.y >= c.fields_h:
            vy = self.verticalScrollBar().value()
            if self.value(self._visible[i], self.comment_key) and \
                    (hit := self._push_hit(self._comment_box(c, c.y - vy), pos)):
                return i, hit
            return i, "comment"
        if pos.x() >= self._side_x():
            if pos.y() + self.verticalScrollBar().value() < c.y + PAD + self._time_h():
                return i, "clips" if self.clips.get(self._visible[i].id) else "side"
            if self.comment_key and self.value(self._visible[i], self.comment_key):
                vy = self.verticalScrollBar().value()
                if hit := self._push_hit(self._comment_box(c, c.y - vy), pos):
                    return i, hit
            return i, "comment" if self.comment_key else "side"
        oy = y - c.y
        for s, top, h in c.rows:
            if top <= oy < top + h:
                return i, s.key
        return i, ""

    # ---- words, for Create token (idea 31) ------------------------------------------------
    def _word_spans(self, i: int, spec: FieldSpec) -> list:
        """A field's words in a visible line: (x start, x end, text), in content coordinates
        (the left margin included). An aligned field's words are its units ({big dog} is one)."""
        ln, c = self._visible[i], self._cells[i]
        out = []
        if spec.aligned:
            x = MARGIN
            for w, u in zip(c.cols, self._units(ln, spec)):
                if u:
                    out.append((x, x + self._w(spec, u), u))
                x += w
            return out
        t = self._display(ln, spec)
        for m in re.finditer(r"\S+", t):
            x = MARGIN + self._w(spec, t[:m.start()])
            out.append((x, x + self._w(spec, m.group()), m.group()))
        return out

    def _word_at(self, i: int, key: str, x: float) -> int:
        """The word of the field at content x (the nearest one before it; -1 if it has none)."""
        spec = next((f for f in self.fields if f.key == key), None)
        spans = self._word_spans(i, spec) if spec is not None else []
        if not spans:
            return -1
        k = 0
        for j, (a, b, _) in enumerate(spans):
            if x >= a - GAP / 2:
                k = j
        return k

    def text_selection(self):
        """(line, field key, the words highlighted) or None. A translation's words lose the
        quotes and the punctuation at their ends ("my dog." → "my dog")."""
        ts = self._text_sel
        if ts is None:
            return None
        line_id, key, a, b = ts
        i = self._index(line_id)
        spec = next((f for f in self.fields if f.key == key), None)
        if i is None or spec is None:
            return None
        spans = self._word_spans(i, spec)
        a, b = max(0, a), min(len(spans) - 1, b)
        if a > b:
            return None
        ln = self._visible[i]
        if spec.aligned:
            words = " ".join(w for _, _, w in spans[a:b + 1])
        else:
            t = self._display(ln, spec)
            found = list(re.finditer(r"\S+", t))
            words = t[found[a].start():found[b].end()]
            if not spec.ipa:
                words = words.strip(EDGE_PUNCT + " ")
        if conventions.CURRENT.on:                # the display conventions' brackets, slashes, quotes
            words = words.strip(conventions.DECORATIONS + " ")
        return (ln, key, words) if words.strip() else None

    def select_words(self, line, key: str, first: int, last: int):
        """Highlight words of a line's field (first to last, counted from 0)."""
        self._text_sel = (line.id, key, min(first, last), max(first, last))
        self.viewport().update()

    def clear_text_selection(self):
        if self._text_sel is not None:
            self._text_sel = None
            self.viewport().update()

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
                ts = self._text_sel
                if ts is not None and ts[0] == ln.id and ts[1] == s.key:   # words highlighted (idea 31)
                    spans = self._word_spans(i, s)
                    if spans:
                        a, b = max(0, ts[2]), min(len(spans) - 1, ts[3])
                        if a <= b:
                            p.fillRect(QRectF(spans[a][0] - vx - 2, y + 2, spans[b][1] - spans[a][0] + 4, rh - 4),
                                       theme.mix(base, accent, 0.40))
                p.setFont(self._font(s))
                if s.aligned:
                    x = x0
                    p.setPen(text)
                    fm = p.fontMetrics()
                    for w, u in zip(c.cols, self._units(ln, s)):
                        self._draw_text(p, QRect(x, y, w, rh), s, u)
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
                        self._draw_text(p, QRect(x0, y, c.width + 40, rh), s, t)
                        if self._search:
                            fm = p.fontMetrics()
                            searchmark.mark_text(p, x0, y + (rh - fm.height()) / 2, fm.height(), t, self._search, fm)
                    elif self.edit_mode:
                        p.setPen(dim)
                        p.setFont(self.small)
                        p.drawText(QRect(x0, y, 300, rh), Qt.AlignVCenter, s.title)
            # the side, pinned at the right: time (speaker, clipped utterances) and the Comment
            if not self.comment_below:
                self._paint_side(p, ln, c, top, sel or cur)
            if self.comment_key:
                box = self._comment_box(c, top)
                p.setPen(QPen(theme.mix(base, text, 0.25), 1))
                p.setBrush(base)
                p.drawRoundedRect(box, 3, 3)
                comment = self.value(ln, self.comment_key)
                p.setPen(text if comment else dim)
                p.setFont(self.plain if comment else self.small)
                inner = box.adjusted(6, 4, -6 - (2 * PUSH if comment else 0), -4)
                p.drawText(inner.toRect(), Qt.TextWordWrap | Qt.AlignTop,
                           comment or ("Comment" if self.edit_mode else ""))
                if comment:                       # Push to question and To Do, as beside the token dialogue's Comment
                    icon("push-question", PUSH).paint(p, self._push_rect(box).toRect())
                    icon("push-todo", PUSH).paint(p, self._push_rect(box, True).toRect())
                if comment and self._search:
                    searchmark.mark_wrapped(p, inner, comment, self._search)
            if self.bookmarks_enabled and (ln.id == self.bookmark or self.edit_mode):   # the bookmark (idea 32)
                br = self._bookmark_rect(c, top)
                p.fillRect(QRectF(0, top, MARGIN - 4, c.h), theme.mix(base, accent, 0.16 if sel else 0.07)
                           if sel or cur else base)
                self._paint_bookmark(p, br, ln.id == self.bookmark)
            p.setPen(QPen(line_col, 1))
            p.drawLine(0, top + c.h, self.viewport().width(), top + c.h)
        if not self._visible:
            p.setPen(dim)
            p.setFont(self.plain)
            p.drawText(self.viewport().rect().adjusted(MARGIN, 20, -20, 0), Qt.AlignTop | Qt.AlignLeft,
                       "No lines match the search." if self.rows else "")
        p.end()

    def _paint_side(self, p, ln, c, top, marked: bool):
        """The side pinned at the right: the line's times (speaker, clipped utterances)."""
        pal = self.palette()
        base, text = pal.base().color(), pal.text().color()
        dim, accent = theme.colour("dim"), theme.accent()
        side_x, side_w = self._side_x(), self.side_w
        p.fillRect(QRect(side_x, top, side_w, c.h), theme.mix(base, accent, 0.10) if marked else base)
        p.setPen(QPen(theme.mix(base, text, 0.12), 1))
        p.drawLine(side_x, top + 4, side_x, top + c.h - 4)
        p.setFont(self.small)
        p.setPen(dim)
        from .texts import clock
        head = self.head_fn(ln) if self.head_fn is not None else f"{clock(ln.start)} – {clock(ln.end)}"
        if self.show_speaker and ln.speaker:
            head += f"   {ln.speaker}"
        th = self._time_h()
        if getattr(ln, "missing_main", False):    # only other tiers have text here (21 October)
            head += "   no main-tier segment"
            p.setPen(theme.colour("error"))
        p.drawText(QRect(side_x + 10, top + PAD - 2, side_w - 20, th), Qt.AlignVCenter, head)
        refs = self.clips.get(ln.id)
        if refs:
            p.setPen(accent)
            p.drawText(QRect(side_x + 10, top + PAD - 2, side_w - 20, th), Qt.AlignVCenter | Qt.AlignRight,
                       ", ".join(refs))

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
        if what == "bookmark" and event.button() == Qt.LeftButton:
            if self.edit_mode:                    # golden, or (again) gone
                self.bookmarkToggled.emit(ln)
            return
        keys = {f.key for f in self.fields}
        self.clear_text_selection()
        if (event.button() == Qt.LeftButton and not self.edit_mode and what in keys
                and not event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
            x = event.position().x() + self.horizontalScrollBar().value()
            self._drag = (ln.id, what, self._word_at(i, what, x), event.position().x())
        if what in ("push", "push-todo"):
            self.select_row(ln)
            self.viewport().update()
            self.currentChanged.emit(ln)
            (self.pushRequested if what == "push" else self.todoRequested).emit(ln)
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

    def mouseMoveEvent(self, event):
        d = self._drag
        if d is None or not event.buttons() & Qt.LeftButton:
            return super().mouseMoveEvent(event)
        line_id, key, start, x0 = d
        i = self._index(line_id)
        if i is None or start < 0:
            return
        if self._text_sel is None and abs(event.position().x() - x0) < DRAG:
            return
        k = self._word_at(i, key, event.position().x() + self.horizontalScrollBar().value())
        self._text_sel = (line_id, key, min(start, k), max(start, k))
        self.viewport().update()

    def mouseReleaseEvent(self, event):
        self._drag = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        i, what = self._hit(event.position().toPoint())
        if i is None:
            return
        ln = self._visible[i]
        if what in ("push", "push-todo", "bookmark"):
            return
        if what == "clips":
            self.clipActivated.emit(ln)
        elif not self.edit_mode:
            self.select_row(ln)
            self.playRequested.emit()

    def contextMenuEvent(self, event):
        i, what = self._hit(event.pos())
        # the field under the mouse, for the menu's Edit item ("" outside a field)
        self.menu_key = (self.comment_key if what in ("comment", "push", "push-todo") else
                         "" if what in ("", "side", "clips", "bookmark") else what) if i is not None else ""
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
        if self.zoom_key(event):                  # Ctrl+0: the zoom back to normal
            return
        if k == Qt.Key_Escape and self._text_sel is not None:
            self.clear_text_selection()
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
        spec = next((s for s in self.fields if s.key == key), None)
        if key == self.comment_key:               # wraps, from the top left (Josh, 21 October)
            ed = CommentEdit(self.viewport())
            ed.setFont(self.plain)
        else:
            ed = QLineEdit(self.viewport())
            ed.setFont(self._font(spec) if spec is not None else self.plain)
            ed.setContextMenuPolicy(Qt.CustomContextMenu)
            ed.customContextMenuRequested.connect(lambda pos, ed=ed: self._editor_menu(ed, pos))
        from . import keyboards
        keyboards.tag(ed, key)                     # the field's own keyboard (idea 43)
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

    def _editor_menu(self, ed, pos):
        """The editor's usual menu, with Create token from the words selected in it (idea 31)."""
        m = ed.createStandardContextMenu()
        words = ed.selectedText().strip()
        if self._editor is not None and self._editor[0] is ed:
            _, line_id, key, _ = self._editor
            spec = next((s for s in self.fields if s.key == key), None)
            if words and spec is not None and not spec.ipa:
                words = words.strip(EDGE_PUNCT + " ")
            first = m.actions()[0] if m.actions() else None
            a = QAction(themed_icon("text-token", 16), f"Create token from “{words}”…" if words
                        else "Create token (select words first)", m)
            a.setEnabled(bool(words))
            line = next((x for x in self.rows if x.id == line_id), None)
            a.triggered.connect(lambda *_: line is not None and self.createTokenRequested.emit(line, key, words))
            m.insertAction(first, a)
            if first is not None:
                m.insertSeparator(first)
        m.exec(ed.mapToGlobal(pos))
        m.deleteLater()

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
                if mods & Qt.ShiftModifier:                         # the window's pitch (the scratchpad)
                    from .ctrlspace import run_shortcut
                    run_shortcut(self, pitch=True)
                else:
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
        note = QLabel("Select what each line shows, and drag to reorder. Fields selected in “Line up” are "
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
