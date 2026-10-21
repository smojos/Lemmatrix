# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Marking what a search bar found, in the grids' cells and a text's lines (19 October).

The searches match with diacritics and capitals ignored (filters.fold_diacritics), so the
marks are found the same way and mapped back onto the text as shown: a match on "deet"
marks "dɪɪtʰ" with its ʰ.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPalette, QTextLayout, QTextOption
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from .. import filters as fl
from . import theme


def _fold(ch: str) -> str:
    return fl.fold_diacritics(ch).casefold()


def terms(query: str) -> list[str]:
    """A search's items: commas separate several, any of which may match (`dog, cat, hare`;
    IDEAS.md idea 29, Josh 21 October); `\\,` is a comma searched for itself (`go\\, walk`).
    Spaces round each item are dropped. A search that is nothing but commas is taken as typed."""
    if not query:
        return []
    out, cur, k = [], [], 0
    while k < len(query):
        ch = query[k]
        if ch == "\\" and query[k + 1:k + 2] == ",":
            cur.append(",")
            k += 2
            continue
        if ch == ",":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        k += 1
    out.append("".join(cur))
    out = [t.strip() for t in out if t.strip()]
    return out or [query]


def found(hay: str, query: str) -> bool:
    """Whether any of the search's items is in `hay` (both already folded and casefolded)."""
    return any(t in hay for t in terms(query))


def spans(text: str, query: str) -> list[tuple[int, int]]:
    """Where the search `query` (already folded and casefolded) is found in `text`: (start, end)
    in `text`'s own characters, the marks after a match included. Each of a search's items
    (separated by commas) is marked."""
    if not text or not query:
        return []
    items = terms(query)
    if len(items) > 1 or items[0] != query:
        merged = sorted(sp for t in items for sp in _spans(text, t))
        out: list[tuple[int, int]] = []
        for a, b in merged:
            if out and a <= out[-1][1]:
                out[-1] = (out[-1][0], max(b, out[-1][1]))
            else:
                out.append((a, b))
        return out
    return _spans(text, query)


def _spans(text: str, query: str) -> list[tuple[int, int]]:
    if not text or not query:
        return []
    folded, owner = [], []
    for i, ch in enumerate(text):
        f = _fold(ch)
        folded.append(f)
        owner.extend([i] * len(f))
    flat = "".join(folded)
    out, at = [], 0
    while True:
        j = flat.find(query, at)
        if j < 0:
            break
        start, end = owner[j], owner[j + len(query) - 1] + 1
        while end < len(text) and not folded[end]:     # the match's own diacritics
            end += 1
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(end, out[-1][1]))
        else:
            out.append((start, end))
        at = j + len(query)
    return out


def fold_query(text: str) -> str:
    return fl.fold_diacritics(text).casefold()


def mark(painter: QPainter, rect: QRectF):
    """A search mark over `rect`: yellow under the text, which stays readable (multiplied on the
    light theme, screened on the dark one)."""
    painter.save()
    if theme.dark():
        painter.setCompositionMode(QPainter.CompositionMode_Screen)
        painter.fillRect(rect, QColor("#7a5e00"))
    else:
        painter.setCompositionMode(QPainter.CompositionMode_Multiply)
        painter.fillRect(rect, QColor("#ffdd55"))
    painter.restore()


def mark_text(painter: QPainter, x: float, top: float, height: float, text: str, query: str, fm,
              limit: float | None = None):
    """Mark the matches in `text`, drawn from `x` with the font metrics `fm`."""
    for a, b in spans(text, query):
        x1 = x + fm.horizontalAdvance(text[:a])
        x2 = x + fm.horizontalAdvance(text[:b])
        if limit is not None:
            x2 = min(x2, limit)
        if x2 > x1:
            mark(painter, QRectF(x1, top, x2 - x1, height))


def mark_wrapped(painter: QPainter, rect: QRectF, text: str, query: str, font: QFont | None = None,
                 centre: bool = False):
    """Mark the matches in word-wrapped text drawn in `rect` (top-aligned, or centred vertically)."""
    found = spans(text, query)
    if not found:
        return
    layout = QTextLayout(text, font or painter.font())
    opt = QTextOption()
    opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(opt)
    layout.beginLayout()
    y = 0.0
    while True:
        tl = layout.createLine()
        if not tl.isValid():
            break
        tl.setLineWidth(rect.width())
        tl.setPosition(QPointF(0, y))
        y += tl.height()
    layout.endLayout()
    top = rect.top() + (max(0.0, (rect.height() - y) / 2) if centre else 0.0)
    for a, b in found:
        for k in range(layout.lineCount()):
            tl = layout.lineAt(k)
            lo, hi = max(a, tl.textStart()), min(b, tl.textStart() + tl.textLength())
            if lo >= hi:
                continue
            x1, x2 = tl.cursorToX(lo)[0], tl.cursorToX(hi)[0]
            r = QRectF(rect.left() + x1, top + tl.y(), x2 - x1, tl.height())
            if r.bottom() <= rect.bottom() + 1:
                mark(painter, r)


def paint_wrapped_cell(delegate: QStyledItemDelegate, painter: QPainter, option, index, query: str):
    """A word-wrapped cell (the notebook's lists): mark what the search found."""
    text = index.data(Qt.DisplayRole)
    if not query or not isinstance(text, str) or not spans(text, query):
        return
    opt = QStyleOptionViewItem(option)
    delegate.initStyleOption(opt, index)
    widget = opt.widget
    style = widget.style() if widget else None
    if style is None:
        return
    rect = QRectF(style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget))
    margin = style.pixelMetric(QStyle.PM_FocusFrameHMargin, None, widget) + 1
    rect.adjust(margin, 0, -margin, 0)
    mark_wrapped(painter, rect, text, query, opt.font, centre=bool(opt.displayAlignment & Qt.AlignVCenter))


def paint_cell(delegate: QStyledItemDelegate, painter: QPainter, option, index):
    """After a cell has been painted: mark what the view's search bar found in its text."""
    query = getattr(index.model(), "search", "")
    if not query:
        return
    text = index.data(Qt.DisplayRole)
    if not isinstance(text, str) or not text:
        return
    if not spans(text, query):
        return
    opt = QStyleOptionViewItem(option)
    delegate.initStyleOption(opt, index)
    widget = opt.widget
    style = widget.style() if widget else None
    if style is None:
        return
    rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget)
    margin = style.pixelMetric(QStyle.PM_FocusFrameHMargin, None, widget) + 1
    fm = opt.fontMetrics
    x0 = rect.left() + margin
    limit = rect.right() - margin
    if fm.horizontalAdvance(text) > limit - x0:              # elided: up to the …
        limit -= fm.horizontalAdvance("…")
    if opt.displayAlignment & Qt.AlignHCenter:
        x0 = rect.left() + (rect.width() - fm.horizontalAdvance(text)) / 2
    elif opt.displayAlignment & Qt.AlignRight:
        x0 = rect.right() - margin - fm.horizontalAdvance(text)
    h = fm.height()
    top = rect.center().y() - h / 2 + 0.5
    mark_text(painter, x0, top, h, text, query, fm, limit)


def keep_colour(opt, index):
    """A cell's own text colour (a grey suggested soundfile name, a red missing one) stays in a
    selected row; the style would otherwise draw it in the selection's text colour."""
    fg = index.data(Qt.ForegroundRole)
    if fg is not None:
        opt.palette.setBrush(QPalette.HighlightedText, QBrush(fg))


class SearchDelegate(QStyledItemDelegate):
    """The grids' plain cells, with the search's matches marked."""

    def initStyleOption(self, opt, index):
        super().initStyleOption(opt, index)
        keep_colour(opt, index)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        paint_cell(self, painter, option, index)
