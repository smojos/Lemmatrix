# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""The splash screen shown while Lemmatrix starts (Josh's design, 20 October).

resources/splash.svg has two placeholders in its small line of text: {version} and {date}
(the copyright year). They're filled in here, then the SVG is drawn at the screen's
resolution.
"""

from __future__ import annotations

import datetime

from PySide6.QtCore import QByteArray, QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QDialog, QSplashScreen

from .. import __version__
from .icons import RESOURCES

BACKGROUND = "#198583"
WIDTH = 600                                    # logical pixels; the SVG is A4 landscape (297 × 210)


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
    pm.fill(QColor(BACKGROUND))                  # the SVG's gradient is partly see-through: Josh exported it on this
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
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
    splash = QSplashScreen(pixmap(), Qt.WindowStaysOnTopHint)
    splash._filter = _CloseOnDialog(splash)
    app.installEventFilter(splash._filter)
    splash.show()
    app.processEvents()
    return splash


def finish(app, splash, window):
    if splash is None:
        return
    app.removeEventFilter(splash._filter)
    splash.finish(window)
