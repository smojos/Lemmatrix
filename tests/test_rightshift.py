# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""α and β are the comparison area's play buttons, and Right Shift+A / B play them (Josh, 24 October)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402



def _played(win, monkeypatch):
    played = []
    monkeypatch.setattr(win, "play_pitch", lambda text: played.append(text))
    return played


def test_letters_are_the_play_buttons_and_no_play_button_is_left(win, monkeypatch):
    from PySide6.QtWidgets import QToolButton
    c = win.comparison
    c.set_tab("pitch")
    played = _played(win, monkeypatch)
    win.show()
    c.alpha.edit.setText("55 21")
    c.beta.edit.setText("13")
    assert c.alpha.content() == {"kind": "pitch", "value": "55 21"}
    assert not c.alpha.findChildren(QToolButton)                     # no play-pitch button in the pad
    assert "Right Shift+A" in c.letters[0].toolTip() and "Right Shift+B" in c.letters[1].toolTip()
    c.letters[1].click()
    c.letters[0].click()
    assert played == ["13", "55 21"]
    c.beta.edit.setText("")
    c.letters[1].click()                                             # an empty pad plays nothing
    assert played == ["13", "55 21"]


def test_right_shift_plays_and_left_shift_types(win, monkeypatch):
    from lemmatrix.ui import rightshift
    c = win.comparison
    c.set_tab("pitch")
    played = _played(win, monkeypatch)
    win.show()
    monkeypatch.setattr(rightshift, "comparison_in", lambda w: c)
    f = rightshift.RightShiftFilter()
    c.alpha.edit.setText("55")
    c.beta.edit.setText("11")
    monkeypatch.setattr(rightshift, "_right_shift_windows", lambda: None)
    monkeypatch.setattr(rightshift.sys, "platform", "linux")
    a = QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.ShiftModifier, "A")
    assert not f.eventFilter(c, a) and played == []                  # left Shift: an A is typed
    down = QKeyEvent(QEvent.KeyPress, Qt.Key_Shift, Qt.ShiftModifier, 62, 0xFFE2, 0)
    f.eventFilter(c, down)                                           # the right Shift goes down
    assert f.eventFilter(c, a) and played == ["55"]
    b = QKeyEvent(QEvent.KeyPress, Qt.Key_B, Qt.ShiftModifier, "B")
    assert f.eventFilter(c, b) and played == ["55", "11"]
    up = QKeyEvent(QEvent.KeyRelease, Qt.Key_Shift, Qt.NoModifier, 62, 0xFFE2, 0)
    f.eventFilter(c, up)
    assert not f.eventFilter(c, a) and played == ["55", "11"]
    monkeypatch.setattr(rightshift, "comparison_in", lambda w: None)  # no comparison area: types
    f.eventFilter(c, down)
    assert not f.eventFilter(c, a)
