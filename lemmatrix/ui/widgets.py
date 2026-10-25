# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Small reusable widgets: pitch drawing, flow layout, filter header, fonts."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QHeaderView, QLayout, QSizePolicy, QWidget)

from .. import pitch as pitchmod


_QUOTES = "\"'“”‘’"


def meaning(text: str) -> str:
    """A gloss or translation as shown: in single quotes, ‘goat’ (the Leipzig convention), the
    same everywhere (Josh, 20 October). Quotes already round it aren't doubled."""
    t = (text or "").strip()
    while len(t) >= 2 and t[0] in _QUOTES and t[-1] in _QUOTES:
        t = t[1:-1].strip()
    return f"‘{t}’" if t else ""
from . import theme
from .icons import funnel



# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------

# Settings → Display → IPA font size (this computer): the size every grid, matrix cell and text
# line starts from, at its own zoom. Set at start-up and when Settings changes (set_ipa_size); it
# was applied only to the lemma list and All data, and only after Settings, so a restart put them
# back to 13 and the other views never followed (the audit, 25 October).
IPA_SIZE = 13
_IPA_FAMILY: list = []                    # the family found, once (the system's fonts are many)


def set_ipa_size(size) -> None:
    global IPA_SIZE
    try:
        IPA_SIZE = max(6, int(size))
    except (TypeError, ValueError):
        IPA_SIZE = 13


def ipa_font(size: int | None = None) -> QFont:
    """Charis SIL if it's installed, otherwise a font with good IPA coverage; at the IPA size
    (Settings → Display) unless a size is given."""
    if not _IPA_FAMILY:
        families = set(QFontDatabase.families())
        _IPA_FAMILY.append(next((n for n in ("Charis SIL", "Charis", "Doulos SIL", "Gentium Plus",
                                             "DejaVu Serif", "Segoe UI", "DejaVu Sans") if n in families), ""))
    f = QFont(_IPA_FAMILY[0]) if _IPA_FAMILY[0] else QFont()
    f.setPointSize(IPA_SIZE if size is None else size)
    return f


# --------------------------------------------------------------------------
# Pitch drawing
# --------------------------------------------------------------------------

def underscore_unit(font: QFont) -> float:
    """The width of "_" in a font: one short pitch step is drawn this long."""
    from PySide6.QtGui import QFontMetricsF
    return max(4.0, QFontMetricsF(font).horizontalAdvance("_"))


SYLLABLE_GAP = 1.0     # space between syllables, in underscores
PAUSE_GAP = 2.0        # space for a comma, in underscores (instead of the syllable gap)


def _gaps(items):
    """(gap before, syllable) pairs for a parsed pitch string; gaps are in units."""
    out = []
    pending = 0.0
    for item in items:
        if item == pitchmod.PAUSE:
            pending = PAUSE_GAP if out else 0.0       # a comma widens the gap to the next syllable
            continue
        gap = (max(pending, SYLLABLE_GAP) if out else 0.0)
        out.append((gap, item))
        pending = 0.0
    return out


def pitch_width(text: str, unit: float = 8.0) -> float:
    """How wide a pitch drawing is: steps x unit, plus the gaps between syllables."""
    return sum(unit * (gap + item.length) for gap, item in _gaps(pitchmod.parse(text)))


def draw_pitch(p: QPainter, rect: QRectF, text: str, low: int = 1, high: int = 5,
               color: QColor | None = None, width: float = 2.0, unit: float = 8.0,
               elide: bool = False) -> None:
    """Draw pitch notation as contours inside rect, from the left edge.

    One short step is `unit` wide (about an underscore), a long step twice
    that. Syllables are one unit apart, two across a comma. Points outside the
    display range are drawn past the edge in red, so the scale stays the same
    for every token. With `elide`, a drawing wider than rect is cut off at its
    right edge with an ellipsis, as text is in a narrow column (Josh, 20 October).
    """
    items = pitchmod.parse(text)
    if not items:
        return
    color = color or theme.colour("pitch")
    span = max(high - low, 1)
    top, bottom = rect.top() + 2, rect.bottom() - 2

    def y_of(d: int) -> float:
        return bottom - (d - low) / span * (bottom - top)

    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    if elide and pitch_width(text, unit) + width > rect.width():
        dots = "\u2026"
        dw = p.fontMetrics().horizontalAdvance(dots) + 2
        p.setPen(color)
        p.drawText(QRectF(rect.right() - dw, rect.top(), dw, rect.height()),
                   Qt.AlignRight | Qt.AlignVCenter, dots)
        p.setClipRect(QRectF(rect.left() - width, rect.top() - width,
                             max(0.0, rect.width() - dw), rect.height() + 2 * width),
                      Qt.IntersectClip)
    x = rect.left()
    for gap, item in _gaps(items):
        x += unit * gap
        bad = any(d < low or d > high for d in item.points)
        pen = QPen(theme.colour("error") if bad else color, width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        pts = [QPointF(x, y_of(item.points[0]))]
        for d, step in zip(item.points[1:], item.steps):
            x += unit * step
            pts.append(QPointF(x, y_of(d)))
        p.drawPolyline(QPolygonF(pts))
    p.restore()


class PitchCanvas(QWidget):
    """Shows a pitch string drawn as contours, e.g. in the token dialogue."""

    def __init__(self, parent=None, low: int = 1, high: int = 5, font: QFont | None = None):
        super().__init__(parent)
        self.text = ""
        self.low, self.high = low, high
        self.unit = underscore_unit(font or ipa_font(16))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.set_range(low, high)

    LEVEL = 0.65         # height of one pitch level, in underscores (the drawing's own scale)
    PAD = 8

    def set_range(self, low: int, high: int):
        """The height follows the display range: one level is a fixed fraction of a step."""
        self.low, self.high = low, high
        self.setFixedHeight(int(max(1, high - low) * self.unit * self.LEVEL) + 2 * self.PAD)
        self.update()

    def set_pitch(self, text: str):
        self.text = text
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        # No box of its own (Josh, 23 October): the drawing isn't editable, so it sits on the
        # window's background rather than a text box's white.
        r = QRectF(self.rect()).adjusted(10, self.PAD - 2, -10, -(self.PAD - 2))
        draw_pitch(p, r, self.text, self.low, self.high, width=2.6, unit=self.unit)


# --------------------------------------------------------------------------
# Tag chips
# --------------------------------------------------------------------------

# Chip colours follow the accent colour (the theme colour, #198583 by default).
def chip_fill() -> QColor:
    return theme.colour("chip_fill")


def chip_border() -> QColor:
    return theme.colour("chip_border")


def chip_text() -> QColor:
    return theme.colour("chip_text")


# Unusual tags (not usual for their lemma's word class) are drawn with a dashed amber
# outline, while the warning is on (Settings → General → Warnings; the main window sets this).
SHOW_UNUSUAL = True


def is_unusual(label) -> bool:
    return SHOW_UNUSUAL and getattr(label, "note", None) is not None and type(label).__name__ == "Unusual"


def unusual_pen(width: float = 1.4) -> QPen:
    pen = QPen(theme.colour("warning"), width)
    pen.setStyle(Qt.DashLine)
    return pen


def chip_metrics(font: QFont):
    from PySide6.QtGui import QFontMetrics
    fm = QFontMetrics(font)
    return fm, fm.height() + 4


def chips_width(labels, font: QFont, gap: int = 4) -> int:
    fm, _ = chip_metrics(font)
    return sum(fm.horizontalAdvance(t) + 12 for t in labels) + gap * max(0, len(labels) - 1)


def paint_chips(p: QPainter, x: float, y: float, labels, font: QFont, gap: int = 4,
                filled: bool = True, max_right: float | None = None) -> float:
    """Draw tags as rounded chips in the theme colour from (x, y); returns the x after the last one."""
    fm, h = chip_metrics(font)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setFont(font)
    for t in labels:
        w = fm.horizontalAdvance(t) + 12
        if max_right is not None and x + w > max_right:
            break
        r = QRectF(x, y, w, h)
        odd = is_unusual(t)
        p.setPen(unusual_pen() if odd else QPen(chip_border(), 1))
        p.setBrush(chip_fill() if filled else theme.colour("chip_blank"))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), h / 2.6, h / 2.6)
        p.setPen(theme.colour("warning") if odd else chip_text())
        p.drawText(r, Qt.AlignCenter, t)
        x += w + gap
    p.restore()
    return x


from PySide6.QtWidgets import QAbstractButton  # noqa: E402


class ChipButton(QAbstractButton):
    """A checkable tag chip: white with an outline in the theme colour, filled with it when picked."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.unusual = False                   # drawn with a dashed amber outline when picked
        f = self.font()
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        self.setFont(f)

    def sizeHint(self):
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self.text()) + 22, fm.height() + 10)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        on = self.isChecked()
        border = chip_border()
        if not self.isEnabled():
            border = theme.colour("chip_disabled")
        odd = on and self.unusual and SHOW_UNUSUAL
        p.setPen(unusual_pen(2) if odd else QPen(border.darker(125) if (self.underMouse() or on) else border, 1.5))
        p.setBrush(theme.colour("chip_on") if on else theme.colour("chip_blank"))
        p.drawRoundedRect(r, r.height() / 2.4, r.height() / 2.4)
        p.setPen(theme.colour("chip_disabled_text") if not self.isEnabled() else chip_text() if on
                 else theme.colour("chip_text_off"))
        p.setFont(self.font())
        p.drawText(r, Qt.AlignCenter, self.text())

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


# --------------------------------------------------------------------------
# Flow layout (wraps buttons onto new lines)
# --------------------------------------------------------------------------

class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), dry=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, dry=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _layout(self, rect, dry):
        x, y, line = rect.x(), rect.y(), 0
        for it in self._items:
            w, h = it.sizeHint().width(), it.sizeHint().height()
            if x + w > rect.right() + 1 and line > 0:
                x, y, line = rect.x(), y + line + self._spacing, 0
            if not dry:
                it.setGeometry(QRect(QPoint(x, y), it.sizeHint()))
            x += w + self._spacing
            line = max(line, h)
        return y + line - rect.y()


# --------------------------------------------------------------------------
# Header with a filter button in every column
# --------------------------------------------------------------------------

class FilterHeader(QHeaderView):
    """A horizontal header that draws a small filter button in each section.

    Clicking the button emits filterClicked(column, global_pos); clicking
    elsewhere on the header sorts as usual.
    """

    filterClicked = Signal(int, QPoint)
    BUTTON = 16

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.active: set[int] = set()
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        self.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def _button_rect(self, rect: QRect) -> QRect:
        b = self.BUTTON
        return QRect(rect.right() - b - 3, rect.center().y() - b // 2, b, b)

    def paintSection(self, painter, rect, index):
        painter.save()
        super().paintSection(painter, rect, index)
        painter.restore()
        br = self._button_rect(rect)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        on = index in self.active
        painter.setPen(QPen(theme.accent() if on else theme.colour("filter_off_line"), 1))
        painter.setBrush(theme.accent() if on else theme.colour("filter_off"))
        painter.drawRoundedRect(QRectF(br).adjusted(0.5, 0.5, -0.5, -0.5), 2, 2)
        shape = funnel(QRectF(br.left() + 3, br.top() + 4, br.width() - 6, br.height() - 7.5))
        painter.setBrush(theme.text_on(theme.accent()) if on else theme.colour("filter_off_mark"))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(shape)
        painter.restore()

    def sectionSizeFromContents(self, index):
        s = super().sectionSizeFromContents(index)
        return QSize(s.width() + self.BUTTON + 6, max(s.height(), self.BUTTON + 6))

    def mousePressEvent(self, event):
        idx = self.logicalIndexAt(event.position().toPoint())
        if idx >= 0:
            rect = QRect(self.sectionViewportPosition(idx), 0, self.sectionSize(idx), self.height())
            if self._button_rect(rect).contains(event.position().toPoint()):
                self.filterClicked.emit(idx, self.mapToGlobal(rect.bottomLeft()))
                return
        super().mousePressEvent(event)


def ask(parent, title: str, text: str, go: str, stop: str = "Cancel", icon=None) -> bool:
    """A question whose buttons say what they do ("Reset to defaults" / "Cancel"), for when the
    text doesn't read as a plain yes-or-no question. True if `go` was clicked (Josh, 20 October:
    a message and its buttons must say the same thing)."""
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(icon if icon is not None else QMessageBox.Question, title, text, parent=parent)
    yes = box.addButton(go, QMessageBox.AcceptRole)
    box.addButton(stop, QMessageBox.RejectRole)
    box.setDefaultButton(yes)
    box.exec()
    return box.clickedButton() is yes
