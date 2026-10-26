# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Questions whose buttons say what they do (the audit, section 8, step 8; Josh, 26 October: "I
like all your suggestions"): no Yes/No boxes left, and ask() and choose() themselves."""

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

UI = Path(__file__).resolve().parent.parent / "lemmatrix" / "ui"


def test_no_yes_no_questions_left():
    """Only Save / Discard / Cancel on closing with unsaved changes stays a standard box."""
    left = []
    for f in UI.glob("*.py"):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"QMessageBox\.question\(", line):
                left.append(f"{f.name}:{n}")
    assert len(left) == 1 and left[0].startswith("main_window.py"), left


def _press(monkeypatch, label):
    from PySide6.QtWidgets import QMessageBox

    def exec_(box):
        b = next(x for x in box.buttons() if x.text() == label)
        box._test_answer = b
        return 0
    monkeypatch.setattr(QMessageBox, "exec", exec_)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._test_answer)


def test_ask_and_choose_name_their_buttons(app, monkeypatch):
    from lemmatrix.ui import widgets
    seen = []
    from PySide6.QtWidgets import QMessageBox
    real_exec = QMessageBox.exec

    _press(monkeypatch, "Delete token")
    assert widgets.real_ask(None, "Delete token", "Delete it?", "Delete token") is True
    _press(monkeypatch, "Cancel")
    assert widgets.real_ask(None, "Delete token", "Delete it?", "Delete token") is False
    _press(monkeypatch, "Back up without saving")
    assert widgets.real_choose(None, "Full backup", "Save first?",
                               ["Save, then back up", "Back up without saving"]) == 1
    _press(monkeypatch, "Cancel")
    assert widgets.real_choose(None, "Full backup", "Save first?",
                               ["Save, then back up", "Back up without saving"]) is None
    _press(monkeypatch, "Open: free text")
    assert widgets.real_choose(None, "Add field", "Closed?", ["Closed: from a list", "Open: free text"],
                               cancel=None, escape=1) == 1
    assert real_exec is not None and not seen
