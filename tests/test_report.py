# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Help → I found a tick! and Request a feature (IDEAS.md idea 15): emails to the support address."""

import os
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

from test_ui import app, win  # noqa: E402,F401


def test_mailto_links():
    from lemmatrix import __version__, report
    for kind, words in (("bug", "I found a tick!"), ("feature", "feature request")):
        u = urlparse(report.mailto(kind))
        assert u.scheme == "mailto" and u.path == "lemmatrix.support@gmail.com"
        q = parse_qs(u.query)
        assert words in q["subject"][0] and __version__ in q["body"][0]


def test_help_menu_and_lemma_controls_open_the_email(win, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    texts = [a.text() for m in win.menuBar().actions() if m.text() == "&Help" for a in m.menu().actions()]
    assert texts[:2] == ["I found a tick!", "Request a feature"]
    win.tick_button.click()
    win.send_report("feature")
    assert opened[0].startswith("mailto:lemmatrix.support@gmail.com") and "tick" in opened[0]
    assert "feature" in opened[1]
    assert win.tick_button.property("icon_name") == "tick"
