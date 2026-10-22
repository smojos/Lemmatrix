# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Josh's tweaks of 22 October: the pitch scratchpad in the main window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_ui import app, win  # noqa: E402,F401


def test_pitch_scratchpad_in_the_main_window(win, monkeypatch):
    played = []
    monkeypatch.setattr(win, "play_pitch", lambda text: played.append(text))
    sp = win.scratchpad
    sp.edit.setText("55 3:3 21")
    assert sp.canvas.text == "55 3:3 21"
    sp.edit.returnPressed.emit()
    assert played == ["55 3:3 21"]
    order = [win.bottom_row.itemAt(i).widget() for i in range(win.bottom_row.count())]
    assert order.index(sp.parentWidget()) + 1 == order.index(win.sess_panel)   # left of Current Session
