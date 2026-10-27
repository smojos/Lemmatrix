# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""α and β are the phonetics scratchpad's play buttons, and Ctrl+1 / Ctrl+2 play them (Josh, 24
October; Ctrl+1/2/3 since 27 October, in place of Right Shift+A / B, so capitals type as ever)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


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
    assert "Ctrl+1" in c.letters[0].toolTip() and "Ctrl+2" in c.letters[1].toolTip()
    c.letters[1].click()
    c.letters[0].click()
    assert played == ["13", "55 21"]
    c.beta.edit.setText("")
    c.letters[1].click()                                             # an empty pad plays nothing
    assert played == ["13", "55 21"]


def test_ctrl_1_and_2_play_from_a_field_and_shift_types_capitals(win, monkeypatch):
    c = win.comparison
    c.set_tab("pitch")
    played = _played(win, monkeypatch)
    win.show()
    win.activateWindow()
    QApplication.processEvents()
    c.alpha.edit.setText("55")
    c.beta.edit.setText("11")
    box = win.lemmas_search if hasattr(win, "lemmas_search") else c.beta.edit
    box.setFocus()
    QTest.keyClick(win.windowHandle(), Qt.Key_1, Qt.ControlModifier)   # through Qt's shortcut map
    QTest.keyClick(win.windowHandle(), Qt.Key_2, Qt.ControlModifier)
    assert played == ["55", "11"]
    c.alpha.edit.setFocus()
    c.alpha.edit.clear()
    QTest.keyClicks(c.alpha.edit, "AB", Qt.ShiftModifier)            # capitals type as ever
    assert played == ["55", "11"]


def test_ctrl_3_plays_gamma_only_while_it_shows(win, monkeypatch):
    c = win.comparison
    c.set_tab("pitch")
    win.show()
    QApplication.processEvents()
    assert not c.has_gamma() and not c.play_key("3")
    sizes = win.right_split.sizes()
    win.right_split.setSizes([sizes[0] - 250, sizes[1] + 250])
    QApplication.processEvents()
    assert c.has_gamma() and "Ctrl+3" in c.letters[2].toolTip()
    played = _played(win, monkeypatch)
    c.gamma.edit.setText("13")
    win.activateWindow()
    QTest.keyClick(win.windowHandle(), Qt.Key_3, Qt.ControlModifier)
    assert played == ["13"]
    win.right_split.setSizes(sizes)
    QApplication.processEvents()
