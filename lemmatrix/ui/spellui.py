"""Spelling in the windows: red wavy underlines and their right-click menu (spelling.py checks).

Underlines go in the token dialogue's English translation, the lemma dialogue's English gloss,
the lemma list's English gloss and All data's gloss and translation columns; not the matrices.

Plain Qt text fields can't style single words, so a field gets a transparent layer on top
(SpellOverlay) that draws the lines; the field itself is unchanged. Table cells are painted
by SpellDelegate.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtGui import QAction, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLineEdit, QMenu, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from . import theme


class Speller:
    """What the windows ask: the unknown words in a text, corrections, adding to the word list.

    spans(text) -> [(start, end, word)]; suggest(word) -> [str]; add(word) adds it to the
    database's word list.
    """

    def __init__(self, spans: Callable, suggest: Callable, add: Callable):
        self.spans, self.suggest, self.add = spans, suggest, add


def draw_squiggle(painter: QPainter, x1: float, x2: float, y: float):
    """A red wavy line from x1 to x2 at y."""
    if x2 - x1 < 2:
        return
    path = QPainterPath(QPointF(x1, y))
    step, up, x = 2.0, True, x1
    while x < x2:
        x = min(x + step, x2)
        path.lineTo(QPointF(x, y - 1.5 if up else y + 0.5))
        up = not up
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(theme.colour("error"), 1.1))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)
    painter.restore()


def spelling_items(word: str, speller: Speller, replace: Callable) -> list:
    """Menu items (text, icon, action, enabled) for a misspelled word: its corrections
    (replace(new)), then "Add to the word list"."""
    sugg = speller.suggest(word)[:5]
    items = [(f"“{word}” may be misspelled", "", lambda: None, False)]
    items += [(f"    {s}", "", (lambda s=s: replace(s)), True) for s in sugg]
    if not sugg:
        items.append(("    (no suggestions)", "", lambda: None, False))
    items.append((f"Add “{word}” to the word list", "", lambda: speller.add(word), True))
    return items


# --------------------------------------------------------------------------
# Text fields
# --------------------------------------------------------------------------

class SpellOverlay(QWidget):
    """A transparent layer over a QLineEdit that draws the underlines."""

    def __init__(self, ed: QLineEdit, speller: Speller):
        super().__init__(ed)
        self.ed, self.speller = ed, speller
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setGeometry(ed.rect())
        ed.installEventFilter(self)
        ed.textChanged.connect(self.update)
        ed.cursorPositionChanged.connect(lambda *_: self.update())
        ed.setContextMenuPolicy(Qt.CustomContextMenu)
        ed.customContextMenuRequested.connect(self._menu)
        self.show()

    def eventFilter(self, obj, event):
        if obj is self.ed and event.type() in (QEvent.Resize, QEvent.Show):
            self.setGeometry(self.ed.rect())
            self.raise_()
        return False

    def _x_of(self, i: int) -> float:
        """The x of character i: from the cursor's place, which takes any scrolling into account."""
        ed = self.ed
        fm = ed.fontMetrics()
        text = ed.displayText()
        p = ed.cursorPosition()
        cursor_x = ed.cursorRect().center().x()
        return cursor_x + fm.horizontalAdvance(text[:i]) - fm.horizontalAdvance(text[:p])

    def paintEvent(self, event):
        ed = self.ed
        text = ed.text()
        if not text or ed.echoMode() != QLineEdit.Normal:
            return
        spans = self.speller.spans(text)
        if not spans:
            return
        fm = ed.fontMetrics()
        r = ed.cursorRect()
        y = r.center().y() + fm.ascent() / 2 + 2.5
        left, right = 2, self.width() - 2
        painter = QPainter(self)
        for start, end, _ in spans:
            x1, x2 = self._x_of(start), self._x_of(end)
            x1, x2 = max(x1, left), min(x2, right)
            if x2 > x1:
                draw_squiggle(painter, x1, x2, y)
        painter.end()

    def _menu(self, pos):
        ed = self.ed
        menu = ed.createStandardContextMenu()
        i = ed.cursorPositionAt(pos)
        hit = next(((s, e, w) for s, e, w in self.speller.spans(ed.text()) if s <= i <= e), None)
        if hit is not None:
            s, e, w = hit
            first = menu.actions()[0] if menu.actions() else None
            for text, _, fn, on in spelling_items(w, self.speller,
                                                  lambda new, s=s, e=e: self._replace(s, e, new)):
                a = QAction(text, menu)
                a.setEnabled(on)
                a.triggered.connect(lambda *_, fn=fn: fn())
                menu.insertAction(first, a)
            if first is not None:
                menu.insertSeparator(first)
        menu.exec(ed.mapToGlobal(pos))
        menu.deleteLater()

    def _replace(self, start: int, end: int, new: str):
        text = self.ed.text()
        self.ed.setText(text[:start] + new + text[end:])
        self.ed.setCursorPosition(start + len(new))


def attach(ed: QLineEdit, speller: Speller | None) -> SpellOverlay | None:
    """Underline unknown English words in a text field."""
    if speller is None:
        return None
    return SpellOverlay(ed, speller)


# --------------------------------------------------------------------------
# Table cells
# --------------------------------------------------------------------------

class SpellDelegate(QStyledItemDelegate):
    """Paints a cell as usual, then underlines its unknown words; its editor gets them too."""

    def __init__(self, speller: Speller | None, parent=None):
        super().__init__(parent)
        self.speller = speller

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if self.speller is None:
            return
        text = index.data(Qt.DisplayRole) or ""
        if not text:
            return
        spans = self.speller.spans(text)
        if not spans:
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
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
        y = rect.center().y() + fm.ascent() / 2 + 2.5
        for start, end, _ in spans:
            x1 = x0 + fm.horizontalAdvance(text[:start])
            x2 = min(x0 + fm.horizontalAdvance(text[:end]), limit)
            if x2 > x1:
                draw_squiggle(painter, x1, x2, y)

    def createEditor(self, parent, option, index):
        ed = super().createEditor(parent, option, index)
        if isinstance(ed, QLineEdit):
            attach(ed, self.speller)
        return ed
