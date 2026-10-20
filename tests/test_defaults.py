"""The defaults of a new database (20 October 2026) and Reset to defaults in Edit → Lists."""

import shutil
from pathlib import Path

import pytest

from lemmatrix import defaults, resets, storage
from lemmatrix.defaults import new_database
from test_ui import app, win  # noqa: F401,E402  (fixtures)
from lemmatrix.model import Group, ListItem, Location, Person, RefCategory, Tag, TagStructure

pytestmark = pytest.mark.real_defaults
SAMPLE = Path(__file__).resolve().parent.parent / "samples"


def names(group: Group) -> list[str]:
    return [t.name for t in group.tags]


def test_tag_structure():
    ts = new_database().settings.tags
    tops = [g.name for g in ts.groups]
    assert tops[:2] == ["Nominal", "Verbal"] and tops[2:] == ["Phonological", "Syntactic", "Instances"]
    nominal, verbal = ts.groups[0], ts.groups[1]
    sub = {g.name: g for g in nominal.groups}
    assert list(sub) == ["Number", "Case", "Possession"]
    assert names(sub["Case"]) == ["Nominative", "Accusative", "Ergative", "Absolutive", "Genitive",
                                  "Pertensive", "Locative"]
    assert [t.code for t in sub["Case"].tags][5:] == ["PER", "LOC"]
    assert names(sub["Possession"]) == ["1SG.POSS", "2SG.POSS", "3SG.POSS", "1PL.POSS", "2PL.POSS", "3PL.POSS"]
    vsub = {g.name: g for g in verbal.groups}
    assert list(vsub) == ["Subject", "Object", "Stem", "Tense", "Aspect", "Mood", "Polarity"]
    assert "NP.A" in names(vsub["Subject"]) and "NP.S" in names(vsub["Subject"]) and "1SG.S" in names(vsub["Subject"])
    assert len(names(vsub["Subject"])) == 14 and names(vsub["Object"])[-1] == "NP.O"
    assert names(vsub["Stem"]) == ["Simple", "Infinitive", "Passive", "Antipassive", "Causative"]
    assert names(vsub["Tense"]) == ["Present", "Past", "Future"]
    assert names(vsub["Mood"]) == ["Indicative", "Imperative", "Interrogative"]
    defaults_ = {g.name: g.default_tag().name for g in (*nominal.groups, *verbal.groups) if g.default_tag()}
    assert defaults_ == {"Number": "Singular", "Case": "Nominative", "Stem": "Simple", "Tense": "Present",
                         "Aspect": "Perfective", "Mood": "Indicative", "Polarity": "Affirmative"}
    for g in (*nominal.groups, *verbal.groups):          # a default has no code: file names leave it out
        assert all(t.file_code() == "" for t in g.tags if t.default)
    assert nominal.usual == ["NOUN"] and verbal.usual == ["VERB"]


def test_lists_people_and_places():
    db = new_database()
    s, md = db.settings, db.metadata
    assert s.text_field("status").all_values() == ["untranscribed", "transcribed", "translated", "analyzed", "finished"]
    genres = s.text_field("genre").all_values()
    assert genres.index("elicited") == genres.index("prayer") + 1 and genres[-1] == "other"
    assert [i.name for i in s.entry_field("ToneClass").items] == ["H", "L", "LH", "HL"]
    infl = s.entry_field("InflectionClass").items
    assert [(i.name, [c.name for c in i.children]) for i in infl] == [("Nominal", ["I", "II"]), ("Verbal", ["I", "II"])]
    assert [p.code for p in md.researchers] == ["RS1", "RS2"]
    assert [p.code for p in md.participants] == ["SP1", "SP2"]
    assert md.location_path("UCL-V") == "Canada › British Columbia › Ucluelet"
    assert md.location_path("PADE") == "Ethiopia › Gambella Regional State › Pade"
    assert "not a known location" in md.location("PADE").description.lower()
    assert "Dixon" in defaults.DIXON_NOTE and "296" in defaults.DIXON_NOTE


def test_new_database_round_trips(tmp_path):
    db = new_database()
    db.path = str(tmp_path / "x.xml")
    storage.save(db, db.path, backup=False)
    back = storage.load(db.path)
    assert back.settings.tags == db.settings.tags
    assert back.metadata.locations == db.metadata.locations
    assert back.settings.entry_field("InflectionClass").items == db.settings.entry_field("InflectionClass").items


def test_the_shipped_sample_opens(tmp_path):
    shutil.copytree(SAMPLE, tmp_path / "s", ignore=shutil.ignore_patterns("*.py"))
    db = storage.load(tmp_path / "s" / "Sample.xml")
    assert db.metadata.language_code == "LXX" and [p.code for p in db.metadata.participants] == ["SP1", "SP2"]
    files = {t.file for _, t in db.all_tokens() if t.file}
    assert files and all((storage.sound_folder(db) / f).exists() for f in files)
    assert len(files) == len([t for _, t in db.all_tokens() if t.file])       # no two tokens share a file


# ---- Reset to defaults --------------------------------------------------------

def test_reset_people_keeps_those_in_use():
    cur = [Person("SP1", "Old name"), Person("ABC", "Used"), Person("ZZZ", "Unused")]
    out, kept = resets.merge_people(defaults.default_participants(), cur, lambda c: c in {"SP1", "ABC"})
    assert [p.code for p in out] == ["SP1", "SP2", "ABC"] and out[0].name == "Old name"
    assert kept == ["SP1", "ABC"]


def test_reset_places_keeps_those_in_use_with_their_parents():
    cur = [Location("Sudan", "SU", children=[Location("Village", "V1"), Location("Other", "V2")]),
           Location("Canada", "CA", children=[Location("Yukon", "YT")])]
    out, kept = resets.merge_locations(defaults.default_locations(), cur, lambda k: k in {"V1", "YT"})
    tops = [x.key for x in out]
    assert tops == ["CA", "ET", "SU"]
    assert [c.key for c in out[2].children] == ["V1"]                     # V2 isn't in use
    assert [c.key for c in out[0].children] == ["BC", "YT"]               # merged into Canada
    assert sorted(kept) == ["V1", "YT"]


def test_reset_lists_categories_and_tags():
    items, kept = resets.merge_items(defaults.tone_classes(), [ListItem("L/H"), ListItem("X")], {"L/H"})
    assert [i.name for i in items] == ["H", "L", "LH", "HL", "L/H"] and kept == ["L/H"]
    cats, kept = resets.merge_categories([RefCategory("A", "Human body")],
                                         [RefCategory("A", "Body"), RefCategory("Z", "Mine"), RefCategory("Y", "x")],
                                         lambda letter: letter in {"A", "Z"})
    assert [(c.letter, c.name) for c in cats] == [("A", "Body"), ("Z", "Mine")]
    old = TagStructure([Group("NOUN", groups=[Group("Case", [Tag("Oblique", "OBL"), Tag("Vocative", "VOC")])])])
    ts, kept = resets.merge_tags(defaults.default_tag_structure(), old, {"Oblique"})
    assert kept == ["Oblique"] and ts.tag("Oblique") is not None and ts.tag("Vocative") is None
    assert ts.tag("Pertensive") is not None


def test_reset_buttons_in_the_lists_dialogue(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from lemmatrix.ui.lists_dialog import ListsDialog
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    db = win.doc.db
    used = {x for _, t in db.all_tokens() for x in t.tags}
    dlg = ListsDialog(win, db, win.doc.notebook)
    dlg._reset("Tag structure", dlg._reset_tags)
    ts = dlg.tags.structure()
    assert ts.tag("Pertensive") is not None and all(ts.tag(n) is not None for n in used)
    dlg._reset("Participants", lambda: dlg._reset_people(dlg.participants, defaults.default_participants(),
                                                         dlg._participant_use))
    assert [p.code for p in dlg.participants.people()][:2] == ["SP1", "SP2"]
    dlg._reset("Locations", dlg._reset_locations)
    assert [x.key for x in dlg.locations.locations()][:2] == ["CA", "ET"]
    tone = next(f for f, _ in dlg.field_lists if f.name == "ToneClass")
    ed = dict((f.name, e) for f, e in dlg.field_lists)["ToneClass"]
    dlg._reset_field(tone, ed)
    in_use = {e.get("ToneClass") for e in db.entries} - {""}
    assert {"H", "L", "LH", "HL"} <= {i.name for i in ed.items()} and in_use <= {i.name for i in ed.items()}
    dlg._reset("Reference categories", dlg._reset_categories)
    dlg._reset("Tier mapping", dlg._reset_tiers)
    assert dlg.tier_editor.mapping().main == "tx"
    dlg.accept()
    dlg.apply()
    win._apply_tags(dlg.tags, dlg.value_renames())
    assert db.settings.tags.tag("Pertensive") is not None
    assert all(set(t.tags) <= {x.name for x, _ in db.settings.tags.tags()} for _, t in db.all_tokens())
