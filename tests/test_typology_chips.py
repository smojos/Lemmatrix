# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Settings → Typology as chips (Josh, 28 October; DESIGN.md 3.1): Pitch, Morphology and Syntax,
a search bar for chips, any number per feature (no "both"), the pitch kind fixed with an ⓘ."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from lemmatrix import defaults, storage, typology  # noqa: E402


def _dlg(win):
    from lemmatrix.ui.dialogs import PreferencesDialog
    return PreferencesDialog(win, win.doc.db, win.prefs)


def test_the_page_has_pitch_morphology_and_syntax(win):
    from PySide6.QtWidgets import QGroupBox
    box = _dlg(win).typology_box
    assert [g.title() for g in box.findChildren(QGroupBox)] == ["Pitch", "Morphology", "Syntax"]
    texts = [l.text() for l in box.findChildren(__import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel)]
    assert not any("type" in t.lower() for t in texts)
    assert box.pitch_chip.text() == "Tonal" and "✕" not in box.pitch_chip.text()


def test_search_adds_chips_and_a_click_removes_them(win):
    dlg = _dlg(win)
    box = dlg.typology_box
    assert box.chosen[typology.ORDER] == []
    box._chosen("SVO")
    box._chosen("topic-initial")
    box._chosen("segmental")
    box._chosen("non-concat")
    assert box.chosen[typology.ORDER] == ["SVO", "topic-initial"]
    assert box.chosen[typology.MORPHOLOGY] == ["segmental", "non-concatenative"]
    assert "SVO · Constituent order" not in box.offered()                      # chosen: not offered again
    box.remove(typology.ORDER, "SVO")
    dlg.apply()
    assert typology.values(win.doc.db, typology.ORDER) == ["topic-initial"]
    assert typology.values(win.doc.db, typology.MORPHOLOGY) == ["segmental", "non-concatenative"]
    assert getattr(dlg, "kind_requested", None) is None                        # the kind isn't set here


def test_the_pitch_info_goes_to_settings_pitch(win):
    from PySide6.QtWidgets import QTabWidget
    dlg = _dlg(win)
    tabs = dlg.findChild(QTabWidget)
    dlg.typology_box.pitch_info.click()
    assert tabs.tabText(tabs.currentIndex()) == "Pitch"
    assert "Settings → Pitch" in dlg.typology_box.pitch_info.toolTip()


def test_several_values_round_trip_as_repeated_features(tmp_path):
    db = defaults.new_database()
    typology.set_values(db.metadata.typology, typology.ORDER, ["SVO", "topic-initial"])
    typology.set_values(db.metadata.typology, typology.MORPHOLOGY, [])
    p = tmp_path / "x.xml"
    storage.save(db, p)
    text = p.read_text(encoding="utf-8")
    assert '<feature id="order" value="SVO" wals="81A" />' in text
    assert '<feature id="order" value="topic-initial" />' in text
    assert '<feature id="morphology" value="unspecified" />' in text
    back = storage.load(p)
    assert typology.values(back, typology.ORDER) == ["SVO", "topic-initial"]
    assert typology.values(back, typology.MORPHOLOGY) == []
    storage.save(back, p)
    assert p.read_text(encoding="utf-8") == text                                # stable


def test_an_old_both_opens_as_two_chips():
    assert typology.values({"morphology": "both"}, typology.MORPHOLOGY) == ["segmental", "non-concatenative"]
    assert typology.values({"order": "unspecified"}, typology.ORDER) == []


def test_the_accents_default_is_jennifers_blue(win):
    assert _dlg(win).accent.reset.toolTip() == "Jennifer's blue"
