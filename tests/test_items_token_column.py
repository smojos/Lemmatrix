# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Debug, 27 October (Josh): in Questions and To Do, a token with many tags no longer widens the
Token column; it keeps its width (the researcher's, remembered) and wraps."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"


LONG = "D009 jɔ̀dʌ́ʌm ‘your goat’ · " + ".".join(["2SG.POSS", "PL", "F1", "GEN", "x1", "NEG", "PST"] * 4)


def _dialogs(win):
    from lemmatrix import notebook as nb
    from lemmatrix.ui.notebook_dialog import QuestionsDialog, TodoDialog
    s = win.doc.notebook.add_session("2026-10-01")
    q = nb.Question("why?", "2026-10-01")
    q.about = LONG
    s.questions = [q]
    t = nb.Question("record it", "2026-10-01")
    t.about = LONG
    s.todos = [t]
    return QuestionsDialog(win), TodoDialog(win)


def test_the_token_column_keeps_its_width_and_wraps(win):
    from lemmatrix.ui.notebook_dialog import TOKEN_WIDTH
    for dlg in _dialogs(win):
        dlg.show()
        h = dlg.tree.header()
        col = dlg.LINK_COLUMN
        assert h.sectionSize(col) == TOKEN_WIDTH
        it = dlg.tree.topLevelItem(0)
        assert LONG in it.text(col)
        row = dlg.tree.visualItemRect(it).height()
        assert row > 2 * dlg.tree.fontMetrics().lineSpacing()      # wrapped onto several lines
        h.resizeSection(col, 300)                                  # dragged by the researcher
        dlg.close()


def test_the_dragged_width_is_remembered(win):
    q, t = _dialogs(win)
    q.tree.header().resizeSection(q.LINK_COLUMN, 333)
    from lemmatrix.ui.notebook_dialog import QuestionsDialog
    again = QuestionsDialog(win)
    assert again.tree.header().sectionSize(again.LINK_COLUMN) == 333
