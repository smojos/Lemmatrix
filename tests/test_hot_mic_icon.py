# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""🔥 hot mic's Record and Stop icons (IDEAS.md idea 68; Josh's drawings, 28 October): his
microphone and stop square before his flame, on a transparent background, never theme coloured;
the Record button wears the stop one while recording."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor  # noqa: E402


def _img(name, themed, monkeypatch):
    from lemmatrix.ui import icons, theme
    monkeypatch.setattr(theme, "themed_buttons", lambda: themed)
    return icons.icon(name, 80).pixmap(80, 80).toImage()


def test_drawn_from_joshs_files():
    from lemmatrix.ui import icons
    for f in (icons.HOT_MIC_FILE, icons.HOT_MIC_STOP_FILE):
        assert f.exists() and "#ff8900" in f.read_text(encoding="utf-8")


def test_transparent_and_orange_whatever_the_buttons(app, monkeypatch):
    for name in ("record-hot", "stop-hot"):
        for themed in (False, True):
            img = _img(name, themed, monkeypatch)
            assert img.pixelColor(3, 3).alpha() == 0, (name, themed)          # no square any more
            oranges = sum(1 for x in range(0, 80, 2) for y in range(0, 80, 2)
                          if (c := img.pixelColor(x, y)).alpha() > 200
                          and abs(c.hue() - QColor("#ff8900").hue()) <= 8 and c.saturation() > 200)
            assert oranges > 50, (name, themed, oranges)


def test_stop_follows_hot_mic(monkeypatch):
    from lemmatrix import advanced
    from lemmatrix.ui import recording_panel as rp
    monkeypatch.setattr(advanced, "hot_mic", lambda: True)
    assert (rp.record_icon(), rp.stop_icon()) == ("record-hot", "stop-hot")
    monkeypatch.setattr(advanced, "hot_mic", lambda: False)
    assert (rp.record_icon(), rp.stop_icon()) == ("record", "stop")
