"""Small reusable widgets: pitch drawing, flow layout, filter header, fonts."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QHeaderView, QLayout, QSizePolicy, QStyle, QStyleOptionHeader,
                               QWidget)

from .. import pitch as pitchmod

PITCH_BLUE = QColor("#1f4fd1")
OUT_OF_RANGE = QColor("#c62828")


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------

def ipa_font(size: int = 13) -> QFont:
    """Charis SIL if it's installed, otherwise a font with good IPA coverage."""
    families = set(QFontDatabase.families())
    for name in ("Charis SIL", "Charis", "Doulos SIL", "Gentium Plus", "DejaVu Serif",
                 "Segoe UI", "DejaVu Sans"):
        if name in families:
            f = QFont(name)
            f.setPointSize(size)
            return f
    f = QFont()
    f.setPointSize(size)
    return f


# --------------------------------------------------------------------------
# Pitch drawing
# --------------------------------------------------------------------------

def draw_pitch(p: QPainter, rect: QRectF, text: str, low: int = 1, high: int = 5,
               color: QColor = PITCH_BLUE, width: float = 2.0, max_slot: float = 34.0) -> None:
    """Draw pitch digits as contours inside rect.

    Each syllable gets its own slot (wider for long or contour syllables); a
    comma leaves a gap. Digits outside the display range are drawn past the
    edge in red, so the scale stays the same for every token.
    """
    items = pitchmod.parse(text)
    if not items:
        return
    span = max(high - low, 1)
    pad = 3.0
    top, bottom = rect.top() + pad, rect.bottom() - pad
    units = sum(max(1, len(i)) if i != pitchmod.PAUSE else 0.6 for i in items)
    slot = min(max_slot, (rect.width() - 2 * pad) / max(units, 1))
    x = rect.left() + pad

    def y_of(d: int) -> float:
        frac = (d - low) / span
        return bottom - frac * (bottom - top)

    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    for item in items:
        if item == pitchmod.PAUSE:
            x += slot * 0.6
            continue
        w = slot * max(1, len(item))
        inner_l, inner_r = x + slot * 0.15, x + w - slot * 0.15
        bad = any(d < low or d > high for d in item)
        pen = QPen(OUT_OF_RANGE if bad else color, width)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        if len(set(item)) == 1:                     # level (short or long)
            y = y_of(item[0])
            p.drawLine(QPointF(inner_l, y), QPointF(inner_r, y))
        else:                                       # contour through each point
            n = len(item)
            pts = [QPointF(inner_l + (inner_r - inner_l) * i / (n - 1), y_of(d))
                   for i, d in enumerate(item)]
            p.drawPolyline(QPolygonF(pts))
        x += w
    p.restore()


def pitch_width(text: str, slot: float = 34.0) -> float:
    items = pitchmod.parse(text)
    return 6 + slot * sum(max(1, len(i)) if i != pitchmod.PAUSE else 0.6 for i in items)


class PitchCanvas(QWidget):
    """Shows a pitch string drawn as contours, e.g. in the token dialogue."""

    def __init__(self, parent=None, low: int = 1, high: int = 5):
        super().__init__(parent)
        self.text = ""
        self.low, self.high = low, high
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_pitch(self, text: str):
        self.text = text
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().base())
        r = QRectF(self.rect()).adjusted(6, 4, -6, -4)
        draw_pitch(p, r, self.text, self.low, self.high, width=2.6, max_slot=48)
        bad = pitchmod.out_of_range(self.text, self.low, self.high)
        if bad:
            p.setPen(OUT_OF_RANGE)
            p.drawText(self.rect().adjusted(0, 0, -6, -2), Qt.AlignRight | Qt.AlignBottom,
                       f"outside {self.low}-{self.high}: {' '.join(map(str, bad))}")


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
        painter.setPen(QPen(QColor("#1f4fd1") if on else QColor("#555"), 1))
        painter.setBrush(QColor("#1f4fd1") if on else QColor("#f4f4f4"))
        painter.drawRoundedRect(QRectF(br).adjusted(0.5, 0.5, -0.5, -0.5), 2, 2)
        funnel = QPolygonF([QPointF(br.left() + 3, br.top() + 4), QPointF(br.right() - 3, br.top() + 4),
                            QPointF(br.center().x() + 1.5, br.center().y() + 1),
                            QPointF(br.center().x() + 1.5, br.bottom() - 3),
                            QPointF(br.center().x() - 1.5, br.bottom() - 4),
                            QPointF(br.center().x() - 1.5, br.center().y() + 1)])
        painter.setBrush(QColor("white") if on else QColor("#333"))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(funnel)
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
