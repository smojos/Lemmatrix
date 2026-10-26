# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Hiding the pitch system (IDEAS.md idea 9; DESIGN.md 3.5): Settings → Pitch → Show the pitch
system and View → Hide pitch system. Hiding is a view of the open database, in its workspace: it
never changes the data, and everything comes back as it was (Josh, 23 October: preserve and
protect the data)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LEMMATRIX_SETTINGS"] = "Lemmatrix-tests"

import pytest  # noqa: E402

from lemmatrix import matrix as mx, pitchview  # noqa: E402
from lemmatrix import workspace as wsmod  # noqa: E402

LEMMA_TAG = 1


@pytest.fixture(autouse=True)
def _shown_again():
    yield
    pitchview.load(None)                       # never leave the next test with pitch hidden


# ---- the model (no Qt) ------------------------------------------------------------------------

class _S:
    class _F:
        def __init__(self, name, role):
            self.name, self.role = name, role

    token_fields = [_F("Phonetic", "phonetic"), _F("Pitch", "pitch"), _F("Translation", "translation")]


def test_the_setting_lives_in_the_workspace():
    ws = wsmod.Workspace()
    pitchview.load(ws)
    assert pitchview.shown() and all(pitchview.shown(p) for p in pitchview.PARTS)
    pitchview.store(ws, False)
    assert ws.get(pitchview.KEY) is False and not pitchview.shown(pitchview.TOKENS)
    assert not pitchview.shown(pitchview.UTTERANCES) and not pitchview.shown(pitchview.SCRATCHPADS)
    pitchview.load(wsmod.Workspace())          # another database: its own (shown)
    assert pitchview.shown()
    pitchview.load(ws)
    assert not pitchview.shown()
    pitchview.store(ws, True)                  # shown is the default: nothing written
    assert pitchview.KEY not in ws.values and pitchview.shown()


def test_keys_hidden_and_kept_where_they_were():
    s = _S()
    pitchview.store(None, False)
    assert pitchview.is_pitch_key("drawing", s) and pitchview.is_pitch_key("f:Pitch", s)
    assert pitchview.is_pitch_key("Pitch", s) and not pitchview.is_pitch_key("f:Phonetic", s)
    saved = ["ref", "drawing", "f:Phonetic", "f:Pitch", "f:Translation"]
    assert pitchview.visible(saved, s) == ["ref", "f:Phonetic", "f:Translation"]
    # chosen while hidden: Translation moved before Phonetic, Speaker added
    chosen = ["ref", "f:Translation", "f:Phonetic", "speaker"]
    assert pitchview.keep_hidden(saved, chosen, s) == ["ref", "drawing", "f:Translation", "f:Phonetic",
                                                       "f:Pitch", "speaker"]
    assert pitchview.keep_hidden(["drawing", "Phonetic"], ["Phonetic"], s) == ["drawing", "Phonetic"]
    pitchview.store(None, True)
    assert pitchview.keep_hidden(saved, chosen, s) == chosen    # shown: as chosen


# ---- the main window ------------------------------------------------------------------------

def _hide(win):
    win.set_pitch_shown(False)
    assert not pitchview.shown() and win.pitch_view_action.isChecked()


def test_hiding_never_changes_the_data(win):
    doc = win.doc
    doc.save()
    before = open(doc.db.path, "rb").read()
    steps = doc.undo.count()
    _hide(win)
    assert not doc.dirty and doc.undo.count() == steps          # a view setting: no undo step
    assert doc.workspace.get(pitchview.KEY) is False
    doc.save()
    assert open(doc.db.path, "rb").read() == before
    win.set_pitch_shown(True)
    doc.save()
    assert open(doc.db.path, "rb").read() == before
    assert doc.workspace.get(pitchview.KEY) is None


def test_all_data_columns_hidden_and_kept(win):
    win.doc.ws_set("columns/alldata", win._default_all_keys())
    _hide(win)
    keys = [c.key for c in win.all_table.model_.columns]
    assert "drawing" not in keys and "f:Pitch" not in keys and "f:Phonetic" in keys
    assert all(c.key not in ("drawing", "f:Pitch") for c in win._all_columns())   # not offered either
    assert "drawing" in win.doc.ws.get_list("columns/alldata")                     # the setup kept
    from lemmatrix.ui import main_window
    chosen = [k for k in keys if k != "speaker"]

    class Dlg:
        def __init__(self, *a):
            pass

        def exec(self):
            return True

        def chosen(self):
            return chosen
    import unittest.mock as um
    with um.patch.object(main_window, "ConfigureColumnsDialog", Dlg):
        win.configure_all_columns()             # Configure columns while hidden
    saved = win.doc.ws.get_list("columns/alldata")
    assert "speaker" not in saved and "drawing" in saved and "f:Pitch" in saved
    win.set_pitch_shown(True)
    keys = [c.key for c in win.all_table.model_.columns]
    assert keys.index("drawing") < keys.index("f:Phonetic") < keys.index("f:Pitch")   # back where they were


def test_matrix_cells_and_configure_cell(win):
    from lemmatrix.ui.matrix_dialogs import ConfigureCellDialog
    win.tabs.setCurrentIndex(LEMMA_TAG)
    cfg = win.config_for(LEMMA_TAG)
    cfg.x = [mx.Spec.citation()]
    cfg.cell = ["drawing", "Phonetic", "Pitch", "Translation"]
    win.refresh()
    assert win.lt_view.cell_fields == cfg.cell
    _hide(win)
    assert win.lt_view.cell_fields == ["Phonetic", "Translation"]
    assert cfg.cell == ["drawing", "Phonetic", "Pitch", "Translation"]   # the configuration kept
    dlg = ConfigureCellDialog(win, win.doc.db, cfg.cell, win.aligned_set())
    offered = [dlg.list.topLevelItem(i).data(0, 0x0100) for i in range(dlg.list.topLevelItemCount())]
    assert "drawing" not in offered and "Pitch" not in offered
    assert dlg.chosen() == cfg.cell                                     # OK as it is: nothing lost
    win.set_pitch_shown(True)
    assert win.lt_view.cell_fields == cfg.cell


def test_token_dialogue_without_pitch(win):
    from lemmatrix.ui.token_dialog import Slot, TokenDialog
    e = next(x for x in win.doc.db.entries if x.tokens and x.tokens[0].get("Pitch"))
    pitch = e.tokens[0].get("Pitch")
    _hide(win)
    dlg = TokenDialog(win, [Slot(e, 0)], 0)
    assert "Pitch" not in dlg.edits
    assert dlg.canvas.isHidden() and dlg.pitch_play.isHidden() and dlg.drawing_label.isHidden()
    played = []
    win.play_pitch = lambda text: played.append(text)
    dlg._play_pitch()
    dlg.edits["Phonetic"].setText("55 3:3")       # would ask "Pitch?" with pitch shown
    assert dlg.check_pitch_like()
    dlg.edits["Phonetic"].setText(e.tokens[0].get("Phonetic"))
    dlg.edits["Translation"].setText("changed here")
    dlg._ok()
    assert e.tokens[0].get("Pitch") == pitch and e.tokens[0].get("Translation") == "changed here"
    assert played == []


def test_menus_and_keys(win):
    played = []
    win.play_pitch = lambda text: played.append(text)
    win.all_table.select_row(win.all_table.visible_rows()[0])
    assert any(i[0].startswith("Play pitch") for i in win._token_items())
    _hide(win)
    assert not any(i[0].startswith("Play pitch") for i in win._token_items())
    assert win._pitch_items() == []                     # Raise and Lower pitch
    win.play_selected_pitch()                           # Ctrl+Shift+Space: nothing
    assert played == []
    rows = [k for _, r in win.shortcut_rows() for k, _ in r]
    assert not any("Ctrl+Shift+Space" in k for k in rows)


def test_bulk_edit_and_tier_mapping(win):
    from lemmatrix.ui.texts import field_choices
    win.open_bulk_edit()
    b = win.bulk_window
    names = [b.s_which.itemData(i) for i in range(b.s_which.count())]
    assert "pitch" in names
    _hide(win)                                           # Bulk edit follows at once
    names = [b.s_which.itemData(i) for i in range(b.s_which.count())]
    assert "pitch" not in names and names
    assert all(t.role != "pitch" for t in b._targets())
    assert all(f != "Pitch" for _, f, _ in field_choices(win.doc.db))
    assert any(f == "Pitch" for _, f, _ in field_choices(win.doc.db, ("Pitch", "")))   # a rule kept
    b.close()


def test_comparison_area_keeps_alpha_and_beta(win):
    c = win.comparison
    c.set_tab("pitch")
    assert not c.alpha.isHidden() and c.tabs.isTabEnabled(0) and c.tabs.tabText(0) == "Pitch"
    _hide(win)
    # the Pitch tab says no pitch and can't be chosen; Segments is shown (idea 46, Josh)
    assert c.alpha.isHidden() and c.beta.isHidden()
    assert c.tabs.tabText(0) == "no pitch" and not c.tabs.isTabEnabled(0) and c.current() == "segment"
    assert not c.seg_alpha.isHidden()
    assert all(not lbl.isHidden() for lbl in c.letters[:2])      # α and β stay at the left edge
    assert win.prefs.comparison_tab == "pitch"                    # switched for it, not remembered
    next(x for x in c.note_menu().actions() if x.text() == "Unhide pitch").trigger()   # right-click
    assert pitchview.shown() and c.current() == "pitch" and not c.alpha.isHidden()


def test_settings_tick(win):
    from lemmatrix.ui.dialogs import PreferencesDialog
    dlg = PreferencesDialog(win, win.doc.db, win.prefs)
    assert not dlg.pitch_hide.isChecked() and dlg.low.isEnabled()
    dlg.pitch_hide.setChecked(True)                                # Hide the pitch system (26 October)
    assert not dlg.low.isEnabled() and not dlg.voice.isEnabled()  # greyed under it
    box = dlg.low.parentWidget()
    assert not box.isEnabled() and box.title() == "This database"  # the whole box, its heading and labels
    dlg.apply()
    assert not pitchview.shown() and win.doc.workspace.get(pitchview.KEY) is False


def test_utterances_window_follows(win):
    win.open_utterances()
    w = win.utterances_window
    assert "drawing" in [c.key for c in w._columns()]
    _hide(win)
    assert "drawing" not in [c.key for c in w.table.model_.columns]
    assert w.texts.comparison.alpha.isHidden() and w.texts.comparison.tabs.tabText(0) == "no pitch"
    w.close()


def test_kept_when_the_database_is_opened_again(win, tmp_path):
    from lemmatrix import storage
    _hide(win)
    win.doc.write_workspace()
    path = win.doc.db.path
    pitchview.load(None)
    win.load_database(storage.load(path))
    assert not pitchview.shown() and win.pitch_view_action.isChecked()
    assert win.comparison.alpha.isHidden()
