# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The whiteboard window (IDEAS.md idea 45, Josh's mockup of 22 October 2026): Tools → Whiteboard
(Ctrl+Shift+W), a bit of an Easter egg, with no button of its own. The board itself is
lemmatrix/whiteboard.py (strokes, sizes, file names; no Qt).

It looks like a real whiteboard: a grey frame, the white sheet (landscape A5 in shape) and a tray
along the bottom with the buttons at its left, Josh's duster and his four markers lying in it
(his drawing, with gradients, a shine and soft shadows added).

- **Click** a marker or the duster to pick it; over the board a circle shows the size and colour of
  what you're drawing with. The **mouse wheel** over the board changes that size.
- The duster **rubs out** where it passes; **double-click** it to wipe the board (asks first).
- **Ctrl+Z** and **Ctrl+Y** undo and redo strokes (Wipe included), in the whiteboard only.
- **Blackboard** turns the board black and redraws every stroke in chalk colours.
- **Save** writes a PNG into the main folder's Whiteboard folder straight away (Ctrl+S; the arrow
  gives Save as JPEG); **Copy** puts the drawing on the clipboard (Ctrl+C); **Link to hypothesis…**
  saves first if there are new strokes, then links the drawing (Cogitate, DESIGN.md 3.14).
- A pen draws thinner when pressed lightly; the mouse and touch draw at full size.
- The drawing is kept in the database's workspace until it is wiped.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QImage, QKeySequence, QLinearGradient, QPainter,
                           QPainterPath, QPen, QShortcut, QTransform)
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QMenu, QMessageBox, QScrollArea,
                               QToolButton, QToolTip, QVBoxLayout, QWidget)

from .. import hypotheses as hy
from .. import whiteboard as wb
from . import theme
from .icons import icon

MARGIN = 14                          # the grey frame round the sheet
TRAY_GAP = 10                        # between the sheet's border and the tray's lip
TRAY_H = 86
FRAME_W = wb.SHEET_W + 2 * MARGIN
FRAME_H = MARGIN + wb.SHEET_H + TRAY_GAP + TRAY_H

FRAME_GREY = QColor("#a3a3a3")       # Josh's frame
BORDER_GREY = QColor("#989898")      # and the board's edge

NAMES = {"black": "Black marker", "red": "Red marker", "blue": "Blue marker", "green": "Green marker",
         wb.ERASER: "Eraser"}

from .whiteboard_art import blackboard_icon, duster_image, marker_image  # Josh's artwork (ARTWORK.md)



# ---- drawing the ink --------------------------------------------------------------------

def draw_stroke(p: QPainter, s: wb.Stroke, blackboard: bool, start: int = 0):
    """Draw a stroke (from point `start`) on an ink layer: a marker in its colour, the eraser
    clearing the layer. Each segment is as wide as its points' average width, round-capped."""
    if not s.points:
        return
    p.save()
    if s.tool == wb.ERASER:
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        col = QColor(0, 0, 0)
    else:
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        col = QColor(wb.colour(s.tool, blackboard))
    pts = s.points
    if len(pts) == 1:
        w = s.width(0)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(*pts[0]), w / 2, w / 2)
        p.restore()
        return
    pen = QPen(col)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    if s.pressure is None:                         # one width: one path, smooth joins
        pen.setWidthF(float(s.size))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        a = max(0, start - 1)
        path = QPainterPath(QPointF(*pts[a]))
        for x, y in pts[a + 1:]:
            path.lineTo(x, y)
        p.drawPath(path)
    else:
        p.setBrush(Qt.NoBrush)
        for i in range(max(1, start), len(pts)):
            pen.setWidthF((s.width(i - 1) + s.width(i)) / 2)
            p.setPen(pen)
            p.drawLine(QPointF(*pts[i - 1]), QPointF(*pts[i]))
    p.restore()


def render(board: wb.Board, scale: float = 1.0, dpr: float = 1.0) -> QImage:
    """The board as it looks: the board's colour, then the ink (rubbed out where the eraser went)."""
    w, h = round(wb.SHEET_W * scale * dpr), round(wb.SHEET_H * scale * dpr)
    ink = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    ink.fill(Qt.transparent)
    p = QPainter(ink)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale * dpr, scale * dpr)
    for s in board.strokes:
        draw_stroke(p, s, board.blackboard)
    p.end()
    out = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    out.fill(QColor(wb.BOARD[board.blackboard]))
    p = QPainter(out)
    p.drawImage(0, 0, ink)
    p.end()
    return out


# ---- the sheet ------------------------------------------------------------------------

class Sheet(QWidget):
    """The board itself: draws, rubs out, shows the size circle, and keeps an ink layer."""

    changed = Signal()                  # a stroke finished (the window keeps the history)
    sizeChanged = Signal()

    def __init__(self, board: wb.Board, parent=None):
        super().__init__(parent)
        self.board = board
        self.setFixedSize(wb.SHEET_W, wb.SHEET_H)
        self.setMouseTracking(True)
        self.setCursor(Qt.BlankCursor)
        self.setAttribute(Qt.WA_TabletTracking, True)
        self.current: wb.Stroke | None = None
        self.hover: QPointF | None = None
        self.before: list[wb.Stroke] | None = None
        self.ink: QImage | None = None
        self.rebuild()

    # ---- the ink layer ------------------------------------------------------------
    def _dpr(self) -> float:
        return max(1.0, self.devicePixelRatioF())

    def rebuild(self):
        """Draw every stroke again (undo, Blackboard, opening)."""
        dpr = self._dpr()
        img = QImage(round(wb.SHEET_W * dpr), round(wb.SHEET_H * dpr), QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(dpr, dpr)
        for s in self.board.strokes:
            draw_stroke(p, s, self.board.blackboard)
        p.end()
        self.ink = img
        self.update()

    def _draw_more(self, s: wb.Stroke, start: int):
        if self.ink is None or abs(self.ink.width() - round(wb.SHEET_W * self._dpr())) > 1:
            return self.rebuild()
        p = QPainter(self.ink)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(self._dpr(), self._dpr())
        draw_stroke(p, s, self.board.blackboard, start)
        p.end()
        a = s.points[max(0, start - 1):]
        xs, ys = [x for x, _ in a], [y for _, y in a]
        r = s.size / 2 + 3
        self.update(QRectF(min(xs) - r, min(ys) - r, max(xs) - min(xs) + 2 * r,
                           max(ys) - min(ys) + 2 * r).toAlignedRect())

    # ---- drawing ------------------------------------------------------------------
    def begin(self, pos: QPointF, pressure: float | None = None):
        t = self.board.tool
        self.before = list(self.board.strokes)
        self.current = wb.Stroke(t, self.board.sizes.get(t, wb.DEFAULT_SIZE[t]))
        self.current.add(pos.x(), pos.y(), pressure)
        self._draw_more(self.current, 0)

    def extend(self, pos: QPointF, pressure: float | None = None):
        s = self.current
        if s is None:
            return
        n = len(s.points)
        if s.add(pos.x(), pos.y(), pressure):
            self._draw_more(s, n)                   # the new segment only

    def finish(self):
        s = self.current
        self.current = None
        if s is None or not s.points:
            return
        self.board.strokes.append(s)
        self.changed.emit()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.begin(e.position())
        self.hover = e.position()

    def mouseMoveEvent(self, e):
        old = self.hover
        self.hover = e.position()
        if self.current is not None and e.buttons() & Qt.LeftButton:
            self.extend(e.position())
        self._update_circle(old)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.finish()

    def tabletEvent(self, e):
        """A pen: its pressure sets the width (a light touch draws thinner)."""
        pos, pr = e.position(), e.pressure()
        old = self.hover
        self.hover = pos
        tp = e.type()
        if tp == e.Type.TabletPress:
            self.begin(pos, pr)
        elif tp == e.Type.TabletMove:
            if self.current is not None and e.buttons() & Qt.LeftButton:
                self.extend(pos, pr)
        elif tp == e.Type.TabletRelease:
            self.finish()
        self._update_circle(old)
        e.accept()

    def wheelEvent(self, e):
        """The mouse wheel over the board: the size of what you're drawing with."""
        steps = round(e.angleDelta().y() / 120) or (1 if e.angleDelta().y() > 0 else -1 if e.angleDelta().y() else 0)
        if not steps:
            return
        t = self.board.tool
        self.board.sizes[t] = wb.step_size(t, self.board.sizes.get(t, wb.DEFAULT_SIZE[t]), steps)
        self.hover = e.position()
        self.update()
        self.sizeChanged.emit()
        e.accept()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def _update_circle(self, old: QPointF | None):
        r = self.board.sizes.get(self.board.tool, 4) / 2 + 4
        for pt in (old, self.hover):
            if pt is not None:
                self.update(QRectF(pt.x() - r, pt.y() - r, 2 * r, 2 * r).toAlignedRect())

    # ---- showing it ---------------------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(wb.BOARD[self.board.blackboard]))
        if self.ink is not None:
            p.drawImage(QRectF(0, 0, wb.SHEET_W, wb.SHEET_H), self.ink)
        if self.hover is not None:                  # the circle: the size and colour of the tool
            p.setRenderHint(QPainter.Antialiasing)
            t = self.board.tool
            d = self.board.sizes.get(t, 4)
            edge = QColor("#f4f4f4") if self.board.blackboard else QColor("#555555")
            if t == wb.ERASER:
                pen = QPen(edge, 1.2, Qt.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
            else:
                c = QColor(wb.colour(t, self.board.blackboard))
                p.setPen(QPen(edge, 1))
                fill = QColor(c)
                fill.setAlpha(150)
                p.setBrush(fill)
            p.drawEllipse(self.hover, max(1.5, d / 2), max(1.5, d / 2))
            if d > 8:                                # the centre, where the stroke goes
                p.setPen(Qt.NoPen)
                p.setBrush(edge)
                p.drawEllipse(self.hover, 1.1, 1.1)
        p.end()


# ---- the tray ------------------------------------------------------------------------

class Tray(QWidget):
    """The ledge along the bottom: the duster and the four markers, each picked with a click."""

    picked = Signal(str)
    wipeAsked = Signal()

    # where each thing lies: centre x, centre y, length, angle (degrees), flipped (cap to the right)
    PLACES = {wb.ERASER: (330, 46, 108, -10, False),     # where Josh's mockup has them, with room to click
              "blue": (520, 28, 124, 2, False),
              "black": (545, 62, 124, -7, True),
              "green": (668, 30, 124, 0, False),
              "red": (695, 62, 124, 3, False)}

    def __init__(self, board: wb.Board, parent=None):
        super().__init__(parent)
        self.board = board
        self.setFixedSize(FRAME_W, TRAY_H)
        self.setMouseTracking(True)
        self._images: dict = {}
        self.plate = QRectF()                      # the buttons' plate (set by the window)

    def _image(self, key: str) -> QImage:
        bb = self.board.blackboard if key != wb.ERASER else False
        k = (key, bb)
        if k not in self._images:
            length = self.PLACES[key][2]
            self._images[k] = duster_image(length) if key == wb.ERASER else marker_image(key, length, bb)
        return self._images[k]

    def _transform(self, key: str) -> QTransform:
        cx, cy, length, angle, flip = self.PLACES[key]
        img = self._image(key)
        w, h = img.width() / img.devicePixelRatio(), img.height() / img.devicePixelRatio()
        t = QTransform()
        t.translate(cx, cy)
        t.rotate(angle)
        if flip:
            t.scale(-1, 1)
        t.translate(-w / 2, -h / 2)
        return t

    def hit(self, pos: QPointF) -> str | None:
        """What is under the mouse (the topmost thing drawn), by its picture's own shape."""
        for key in reversed(self.order()):
            img = self._image(key)
            inv, ok = self._transform(key).inverted()
            if not ok:
                continue
            q = inv.map(pos)
            dpr = img.devicePixelRatio()
            x, y = int(q.x() * dpr), int(q.y() * dpr)
            if 0 <= x < img.width() and 0 <= y < img.height() and img.pixelColor(x, y).alpha() > 40:
                return key
        return None

    def order(self) -> list[str]:
        return [wb.ERASER, "blue", "green", "black", "red"]   # drawn in this order (red on top)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        g = QLinearGradient(0, 0, 0, TRAY_H)          # the ledge: a light lip, then shade towards the front
        g.setColorAt(0.0, QColor("#cfcfcf"))
        g.setColorAt(0.07, QColor("#b9b9b9"))
        g.setColorAt(0.75, QColor("#a2a2a2"))
        g.setColorAt(1.0, QColor("#8c8c8c"))
        p.fillRect(self.rect(), g)
        p.setPen(QPen(QColor("#e2e2e2"), 1))
        p.drawLine(0, 0, self.width(), 0)
        if not self.plate.isEmpty():                  # a lighter plate, so the buttons read on the grey
            p.setPen(QPen(QColor("#9a9a9a"), 0.8))
            p.setBrush(QColor("#dedede"))
            p.drawRoundedRect(self.plate, 7, 7)
        for key in self.order():
            img = self._image(key)
            t = self._transform(key)
            w, h = img.width() / img.devicePixelRatio(), img.height() / img.devicePixelRatio()
            shadow = QImage(img.size(), QImage.Format_ARGB32_Premultiplied)   # a soft shadow on the ledge
            shadow.fill(Qt.transparent)
            sp = QPainter(shadow)
            sp.drawImage(0, 0, img)
            sp.setCompositionMode(QPainter.CompositionMode_SourceIn)
            sp.fillRect(shadow.rect(), QColor(0, 0, 0, 255))
            sp.end()
            shadow.setDevicePixelRatio(img.devicePixelRatio())
            for dx, dy, a in ((2.5, 3.5, 0.10), (1.5, 2.5, 0.12), (3.5, 4.5, 0.07), (2.0, 3.0, 0.10)):
                p.save()
                p.setOpacity(a)
                p.setTransform(t * QTransform.fromTranslate(dx, dy))
                p.drawImage(QRectF(0, 0, w, h), shadow)
                p.restore()
            p.save()
            p.setTransform(t)
            p.drawImage(QRectF(0, 0, w, h), img)
            p.restore()
        p.end()

    def refresh(self):
        self.update()

    def mouseMoveEvent(self, e):
        key = self.hit(e.position())
        self.setCursor(Qt.PointingHandCursor if key else Qt.ArrowCursor)
        if key:
            tip = NAMES[key] + (": click to rub out, double-click to wipe the board" if key == wb.ERASER
                                else ": click to draw with it")
            self.setToolTip(tip + " (the mouse wheel over the board sets the size)")
        else:
            self.setToolTip("")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            key = self.hit(e.position())
            if key:
                self.picked.emit(key)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton and self.hit(e.position()) == wb.ERASER:
            self.picked.emit(wb.ERASER)
            self.wipeAsked.emit()


class Frame(QWidget):
    """The grey frame, the board's edge, and the sheet and tray inside it."""

    def __init__(self, sheet: Sheet, tray: Tray, parent=None):
        super().__init__(parent)
        self.setFixedSize(FRAME_W, FRAME_H)
        sheet.setParent(self)
        sheet.move(MARGIN, MARGIN)
        tray.setParent(self)
        tray.move(0, MARGIN + wb.SHEET_H + TRAY_GAP)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), FRAME_GREY)
        r = QRectF(MARGIN - 2.5, MARGIN - 2.5, wb.SHEET_W + 5, wb.SHEET_H + 5)
        p.setPen(QPen(BORDER_GREY, 5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 4, 4)
        p.setPen(QPen(QColor("#bdbdbd"), 1))            # a little shine on the frame's top edge
        p.drawLine(QPointF(1, 1), QPointF(self.width() - 1, 1))
        p.end()


# ---- the window -----------------------------------------------------------------------

class WhiteboardWindow(QDialog):
    def __init__(self, main):
        super().__init__(main, Qt.Window)
        self.main = main
        self.doc = main.doc
        self.setWindowTitle("Whiteboard")
        self.board = wb.Board.from_json(self.doc.ws.get_dict("whiteboard"))
        self.past: list[list[wb.Stroke]] = []          # undo, in the whiteboard only
        self.future: list[list[wb.Stroke]] = []

        self.sheet = Sheet(self.board)
        self.tray = Tray(self.board)
        self.frame = Frame(self.sheet, self.tray)
        self.sheet.changed.connect(self._stroke_done)
        self.sheet.sizeChanged.connect(self._keep)
        self.tray.picked.connect(self.pick)
        self.tray.wipeAsked.connect(self.ask_wipe)

        # the buttons, at the left of the tray (Josh's "other options here as buttons")
        bar = QWidget(self.tray)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 0, 0, 0)
        bl.setSpacing(2)

        def tool(ic, tip, fn, checkable=False):
            b = QToolButton()
            b.setIcon(ic)
            b.setIconSize(QSize(24, 24))
            b.setAutoRaise(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tip)
            b.setCheckable(checkable)
            if checkable:
                b.toggled.connect(fn)
            else:
                b.clicked.connect(lambda *_: fn())
            bl.addWidget(b)
            return b
        self.wipe_btn = tool(icon("delete", 24), "Wipe the board (or double-click the eraser)", self.ask_wipe)
        self.blackboard_btn = tool(blackboard_icon(24), "Blackboard: a black board, in chalk colours",
                                   self.set_blackboard, checkable=True)
        self.blackboard_btn.setChecked(self.board.blackboard)
        self.save_btn = tool(icon("save-solid", 24, theme.colour("pitch").name()),
                             "Save as PNG in the Whiteboard folder (Ctrl+S)", lambda: self.save("png"))
        menu = QMenu(self.save_btn)
        self.save_png_action = menu.addAction("Save as PNG", lambda: self.save("png"))
        self.save_jpeg_action = menu.addAction("Save as JPEG", lambda: self.save("jpg"))
        self.save_btn.setMenu(menu)
        self.save_btn.setPopupMode(QToolButton.MenuButtonPopup)
        self.copy_btn = tool(icon("duplicate", 24), "Copy the drawing to the clipboard (Ctrl+C)", self.copy)
        self.link_btn = tool(icon("cogitate", 24, theme.colour("pitch").name()),
                             "Link to hypothesis… (saves the drawing first if it has new strokes)",
                             self.link_to_hypothesis)
        bar.adjustSize()
        bar.move(0, (TRAY_H - bar.height()) // 2)
        self.tray.plate = QRectF(4, bar.y() - 5, bar.width() + 2, bar.height() + 10)
        self.button_bar = bar

        scroll = QScrollArea()                         # a smaller window hides part of the board
        scroll.setWidget(self.frame)
        scroll.setAlignment(Qt.AlignCenter)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #a3a3a3; } QScrollArea > QWidget > QWidget { background: #a3a3a3; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)

        for keys, fn in ((QKeySequence.Undo, self.undo), (QKeySequence.Redo, self.redo),
                         ("Ctrl+Y", self.redo), (QKeySequence.Save, lambda: self.save("png")),
                         (QKeySequence.Copy, self.copy)):
            QShortcut(QKeySequence(keys), self, fn)

        from .winstate import fit_to_screen, keep
        fit_to_screen(self, FRAME_W + 4, FRAME_H + 4)
        keep(self, main.prefs, "window/whiteboard")

    # ---- the tools ------------------------------------------------------------------
    def pick(self, tool: str):
        if tool in wb.TOOLS:
            self.board.tool = tool
            self.sheet.update()
            self._keep()

    def set_blackboard(self, on: bool):
        if bool(on) == self.board.blackboard:
            return
        self.board.blackboard = bool(on)
        if self.blackboard_btn.isChecked() != self.board.blackboard:
            self.blackboard_btn.setChecked(self.board.blackboard)
        self.sheet.rebuild()
        self.tray.refresh()
        self.board.changed = True                      # saved as it looks: a different picture now
        self._keep()

    # ---- history ---------------------------------------------------------------------
    def _stroke_done(self):
        self.past.append(self.sheet.before if self.sheet.before is not None else [])
        self.future.clear()
        self.board.changed = True
        self._keep()

    def _set_strokes(self, strokes):
        self.board.strokes[:] = strokes
        self.board.changed = True
        self.sheet.rebuild()
        self._keep()

    def undo(self):
        if self.past:
            self.future.append(list(self.board.strokes))
            self._set_strokes(self.past.pop())

    def redo(self):
        if self.future:
            self.past.append(list(self.board.strokes))
            self._set_strokes(self.future.pop())

    def ask_wipe(self):
        from . import widgets
        if not self.board.strokes:
            return False
        if not widgets.ask(self, "Whiteboard",
                           "Wipe the whiteboard? (Ctrl+Z brings it back while the whiteboard is open.)", "Wipe"):
            return False
        self.wipe()
        return True

    def wipe(self):
        self.past.append(list(self.board.strokes))
        self.future.clear()
        self._set_strokes([])

    def _keep(self):
        """Into the database's workspace (written a moment later): kept until wiped."""
        self.doc.ws_set("whiteboard", self.board.to_json())

    # ---- saving, copying, linking ------------------------------------------------------
    def image(self) -> QImage:
        """The whole sheet as it looks, at the saving size (about 190 dpi on A5)."""
        return render(self.board, wb.SAVE_SCALE)

    def _need_database(self) -> bool:
        if self.doc.db.path:
            return True
        QMessageBox.information(self, "Whiteboard", "Save the database first: drawings go in its Whiteboard folder.")
        return False

    def save(self, ext: str = "png"):
        """Save as PNG (or JPEG) in the Whiteboard folder straight away; returns the file's path."""
        if not self._need_database():
            return None
        path = wb.new_path(self.doc.db.path, "jpg" if ext in ("jpg", "jpeg") else "png")
        img = self.image()
        ok = img.convertToFormat(QImage.Format_RGB32).save(str(path), "JPEG", 92) if path.suffix == ".jpg" \
            else img.save(str(path), "PNG")
        if not ok:
            QMessageBox.warning(self, "Whiteboard", f"The drawing couldn't be saved as {path}.")
            return None
        self.board.saved = wb.relative(self.doc.db.path, path)
        self.board.changed = False
        self._keep()
        QToolTip.showText(self.save_btn.mapToGlobal(QPoint(0, -30)),
                          f"Saved as {path.name} in the Whiteboard folder", self.save_btn)
        return path

    def copy(self):
        QApplication.clipboard().setImage(self.image())
        QToolTip.showText(self.copy_btn.mapToGlobal(QPoint(0, -30)), "Copied to the clipboard", self.copy_btn)

    def link_to_hypothesis(self):
        """Link to hypothesis…: the drawing as saved (saved now if it has new strokes)."""
        if not self._need_database():
            return None
        if self.board.changed or wb.resolve(self.doc.db.path, self.board.saved) is None:
            if self.save("png") is None:
                return None
        return self.main.link_to_hypothesis(hy.drawing_link(self.board.saved), self)
