# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Two colours of one's own (Josh, 26 October): Settings → Display → Search highlight, and
Settings → Pitch → Pitch traces in a colour of their own (deselected: the accent, as before)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lemmatrix.ui import theme  # noqa: E402


def teardown_function():
    theme.configure("light", theme.DEFAULT_ACCENT)


def test_defaults_are_as_before():
    theme.configure("light", theme.DEFAULT_ACCENT)
    assert theme.search_mark().name() == "#ffdd55"
    assert theme.colour("pitch_trace") == theme.colour("pitch")
    theme.configure("dark", theme.DEFAULT_ACCENT)
    assert theme.search_mark().name() == "#7a5e00"


def test_own_search_colour_and_pitch_colour():
    theme.configure("light", theme.DEFAULT_ACCENT, "#88ccff", "#aa3300")
    assert theme.search_mark().name() == "#88ccff"
    assert theme.colour("pitch_trace").name() == "#aa3300"
    assert theme.colour("pitch").name() == theme.DEFAULT_ACCENT.lower()      # icons keep the accent
    theme.configure("dark", theme.DEFAULT_ACCENT, "#88ccff", "#aa3300")
    assert theme.search_mark().lightness() < 128                              # darker for the dark theme


def test_settings_save_and_the_checkbox_greys_the_colour(win):
    from lemmatrix.ui.dialogs import PreferencesDialog
    p = win.prefs
    dlg = PreferencesDialog(win, win.doc.db, p)
    assert not dlg.pitch_own.isChecked() and not dlg.pitch_colour.isEnabled()
    dlg.pitch_own.setChecked(True)
    assert dlg.pitch_colour.isEnabled()
    from PySide6.QtGui import QColor
    dlg.pitch_colour.set_colour(QColor("#aa3300"))
    dlg.search_colour.set_colour(QColor("#88ccff"))
    dlg.apply()
    assert p.pitch_colour_on and p.pitch_colour == "#aa3300" and p.search_colour == "#88ccff"
    theme.from_prefs(p)
    assert theme.colour("pitch_trace").name() == "#aa3300"
    p.pitch_colour_on = False                                                # deselected: the accent again
    theme.from_prefs(p)
    assert theme.colour("pitch_trace") == theme.colour("pitch")
    p.search_colour = theme.DEFAULT_SEARCH
    theme.from_prefs(p)
    dlg.reject()


def test_all_buttons_theme_coloured_and_the_bookmark(win):
    from PySide6.QtGui import QColor
    from lemmatrix.ui import icons
    from lemmatrix.ui.dialogs import PreferencesDialog
    green = icons._universal()[0]
    assert green.name() == icons.GREEN.name()                       # as they are by default
    p = win.prefs
    dlg = PreferencesDialog(win, win.doc.db, p)
    dlg.themed_buttons.setChecked(True)
    dlg.bookmark_colour.set_colour(QColor("#cc0066"))
    dlg.apply()
    theme.from_prefs(p)
    a = theme.accent()
    g, r = icons._universal()[:2]
    assert abs(g.hslHueF() - a.hslHueF()) < 0.01 and abs(r.hslHueF() - a.hslHueF()) < 0.01
    assert abs(g.lightnessF() - icons.GREEN.lightnessF()) < 0.02    # a theme-coloured version of itself
    assert icons.icon("add", 18).cacheKey() != icons._icon("add", 18, None, "").cacheKey()
    win._restyle()                                                  # open windows follow
    assert theme.bookmark().name() == "#cc0066"
    p.themed_buttons = False
    p.bookmark_colour = theme.DEFAULT_BOOKMARK
    theme.from_prefs(p)
    assert theme.bookmark().name() == theme.DEFAULT_BOOKMARK and not theme.themed_buttons()
    dlg.reject()
