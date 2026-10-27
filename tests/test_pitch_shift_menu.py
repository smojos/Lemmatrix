# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Tweak, 27 October (Josh): the Pitch field and the pitch drawing in the token and utterance
dialogues have Raise pitch and Lower pitch in their right-click menus."""

from PySide6.QtWidgets import QMenu


def _dialog(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    dlg = TokenDialog(win, [Slot(win.doc.db.entries[0], 0)], 0)
    dlg.show()
    return dlg


_MENUS = []      # kept alive while the test reads their actions


def _items(dlg) -> dict:
    m = QMenu()
    _MENUS.append(m)
    dlg._add_shift_items(m)
    return {a.text(): a for a in m.actions() if a.text()}


def test_raise_and_lower_from_the_pitch_field(win):
    dlg = _dialog(win)
    try:
        s = win.doc.db.settings
        s.pitch_low, s.pitch_high = 1, 5
        ed = dlg.pitch_edit
        assert ed is not None
        ed.setText("3 2:4")
        items = _items(dlg)
        assert items["Raise pitch"].isEnabled() and items["Lower pitch"].isEnabled()
        dlg.shift_pitch(1)
        assert ed.text() == "4 3:5" and dlg.canvas.text == "4 3:5"     # the drawing follows
        items = _items(dlg)
        assert not items["Raise pitch"].isEnabled()                    # 5 is the top of the range
        assert "highest" in items["Raise pitch"].toolTip()
        dlg.shift_pitch(1)                                             # refused: nothing changes
        assert ed.text() == "4 3:5"
        dlg.shift_pitch(-1)
        assert ed.text() == "3 2:4"
        ed.undo()                                                      # the field's own undo
        assert ed.text() == "4 3:5"
        ed.setText("")
        assert not any(a.isEnabled() for a in _items(dlg).values())    # nothing to shift
    finally:
        dlg.reject()


def test_the_utterance_dialogue_has_them_too():
    from lemmatrix.ui.token_dialog import TokenDialog
    from lemmatrix.ui.utterances import UtteranceDialog
    assert issubclass(UtteranceDialog, TokenDialog)
    assert UtteranceDialog.shift_pitch is TokenDialog.shift_pitch
    assert UtteranceDialog._canvas_menu is TokenDialog._canvas_menu
