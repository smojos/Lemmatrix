# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The splash screen shown while Lemmatrix starts (Josh's design, 20 October).

resources/splash.svg has two placeholders in its small line of text: {version} and {date}
(the copyright year). They're filled in here, then the SVG is drawn at the screen's
resolution.
"""

from __future__ import annotations

import datetime
import time

from PySide6.QtCore import QByteArray, QEvent, QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QDialog, QSplashScreen

from .. import __version__
from .icons import RESOURCES

BACKGROUND = "#198583"
WIDTH = 600                                    # logical pixels; the SVG is A4 landscape (297 × 210)
RADIUS = 14                                    # its corners are rounded off slightly (Josh, 21 October)


def svg_text(year: int | None = None) -> str:
    text = (RESOURCES / "splash.svg").read_text(encoding="utf-8")
    return (text.replace("{version}", f"Version {__version__}")
                .replace("{date}", str(year or datetime.date.today().year)))


def pixmap(width: int = WIDTH) -> QPixmap:
    r = QSvgRenderer(QByteArray(svg_text().encode("utf-8")))
    size = r.defaultSize()
    height = round(width * size.height() / size.width())
    screen = QGuiApplication.primaryScreen()
    ratio = screen.devicePixelRatio() if screen else 1.0
    pm = QPixmap(round(width * ratio), round(height * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, width, height), RADIUS, RADIUS)
    p.setClipPath(clip)
    p.fillRect(QRectF(0, 0, width, height), QColor(BACKGROUND))   # the SVG's gradient is partly see-through: Josh exported it on this
    r.render(p, QRectF(0, 0, width, height))
    p.end()
    return pm


class _CloseOnDialog(QObject):
    """Any dialogue (a warning, the welcome box) closes the splash, so it's never hidden behind it."""

    def __init__(self, splash):
        super().__init__(splash)
        self.splash = splash

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QDialog) and self.splash.isVisible():
            self.splash.close()
        return False


def show(app) -> QSplashScreen | None:
    """Show the splash screen now; returns it (None if it can't be drawn)."""
    if not (RESOURCES / "splash.svg").exists():
        return None
    splash = QSplashScreen(pixmap(), Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
    splash.setAttribute(Qt.WA_TranslucentBackground)      # so the rounded corners show what's behind
    splash._filter = _CloseOnDialog(splash)
    app.installEventFilter(splash._filter)
    splash.show()
    app.processEvents()
    splash._shown = time.monotonic()                     # on screen from now
    return splash


def finish(app, splash, window, seconds: float = 0.0):
    """Close the splash once the window is up, but not before it has been shown for `seconds`
    (Settings → Display → Splash screen). A click, or any dialogue, closes it sooner."""
    if splash is None:
        return

    def done():
        app.removeEventFilter(splash._filter)
        if splash.isVisible():
            splash.finish(window)

    left = seconds - (time.monotonic() - splash._shown)
    if left > 0 and splash.isVisible():
        QTimer.singleShot(round(left * 1000), done)
    else:
        done()
