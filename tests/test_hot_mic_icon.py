# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""🔥 hot mic's icon (IDEAS.md idea 68, Josh's mockup, 27 October): the Record button's purple square
and white cup and stand, a flame rising out of the cup that stays orange when All buttons theme
coloured is on."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor  # noqa: E402


def _flame_pixel(app, themed: bool, monkeypatch) -> QColor:
    from lemmatrix.ui import icons, theme
    monkeypatch.setattr(theme, "themed_buttons", lambda: themed)
    img = icons.icon("record-hot", 80).pixmap(80, 80).toImage()
    # the flame's outer orange, left of its core, about two thirds of the way down
    return img.pixelColor(round(img.width() * 0.37), round(img.height() * 0.50))


def test_the_flame_stays_orange(app, monkeypatch):
    for themed in (False, True):
        c = _flame_pixel(app, themed, monkeypatch)
        assert abs(c.hue() - QColor("#f5821f").hue()) <= 12 and c.saturation() > 150, (themed, c.name())


def test_the_square_follows_the_buttons(app, monkeypatch):
    from lemmatrix.ui import icons, theme
    monkeypatch.setattr(theme, "themed_buttons", lambda: False)
    plain = icons.icon("record-hot", 80).pixmap(80, 80).toImage().pixelColor(12, 40)
    assert plain.name() == icons.PURPLE.name()
