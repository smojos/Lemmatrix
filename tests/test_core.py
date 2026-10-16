"""Tests for the data model, file names, saving and the matrix layout."""

from pathlib import Path

import numpy as np
import pytest

from lemmatrix import audio, matrix, pitch, storage
from lemmatrix.defaults import new_database
from lemmatrix.model import Participant, Token, forbidden_in


@pytest.fixture
def db():
    d = new_database()
    d.metadata.language_code = "LXX"
    d.metadata.language_name = "Sample language"
    d.metadata.variety_code = "VXX"
    d.metadata.participants = [Participant("SP1", "Speaker one")]
    e = d.new_entry("D009", "ɗæær", "goat", "NOUN", speaker="SP1", date="2026-10-16")
    e.tokens[0].set("Phonetic", "ɗæær")
    e.tokens[0].set("Pitch", "21")
    pl = d.new_token(e, ["Plural"], speaker="SP1", date="2026-10-16")
    pl.set("Phonetic", "ɗɪɪʈʰ")
    pl.set("Translation", "goats", "en")
    e.tokens.append(pl)
    gen = d.new_token(e, ["Genitive", "Plural", "before H"], speaker="SP1")
    e.tokens.append(gen)
    d.entries.append(e)
    return d


# ---- file names ---------------------------------------------------------

def test_filenames_drop_empty_separators(db):
    e = db.entries[0]
    assert db.expected_filename(e, e.tokens[0]) == "LXX-VXX-SP1_D009_goat.wav"
    assert db.expected_filename(e, e.tokens[1]) == "LXX-VXX-SP1_D009_goat_PL.wav"
    assert db.expected_filename(e, e.tokens[2]) == "LXX-VXX-SP1_D009_goat_PL-GEN-xH.wav"
    db.metadata.variety_code = ""
    e.tokens[0].speaker = ""
    assert db.expected_filename(e, e.tokens[0]) == "LXX_D009_goat.wav"
    e.tokens[0].speaker = "SP1"
    assert db.expected_filename(e, e.tokens[0]) == "LXX-SP1_D009_goat.wav"


def test_tag_order_is_independent_of_input_order(db):
    e = db.entries[0]
    a = db.new_token(e, ["Genitive", "Plural"])
    b = db.new_token(e, ["Plural", "Genitive"])
    assert db.expected_filename(e, a) == db.expected_filename(e, b)


def test_spaces_in_gloss_are_kept(db):
    e = db.new_entry("V012", "rum", "to run", "VERB")
    db.metadata.variety_code = ""
    assert db.expected_filename(e, e.tokens[0]) == "LXX_V012_to run.wav"


def test_forbidden_characters():
    assert forbidden_in("he/she?") == "/?"
    assert forbidden_in("goat") == ""


# ---- tags -----------------------------------------------------------------

def test_defaults_are_preselected_except_on_citation(db):
    e = db.entries[0]
    assert e.tokens[0].tags == []                         # citation stays tagless
    assert e.tokens[1].tags == ["Plural", "in isolation"]
    v = db.new_entry("V001", "cəm", "eat", "VERB")
    t = db.new_token(v, ["Past", "Negative"])
    assert t.tags == ["Simple", "Past", "Indicative", "Negative", "in isolation"]


def test_defaults_add_nothing_to_file_names(db):
    v = db.new_entry("V001", "cəm", "eat", "VERB")
    db.metadata.variety_code = ""
    t = db.new_token(v, ["Past", "1SG.A"])
    assert db.expected_filename(v, t) == "LXX_V001_eat_1SG.A-PST.wav"


def test_one_tag_per_group():
    d = new_database()
    ts = d.settings.tags
    assert ts.conflicts("VERB", ["1SG.A", "3SG.O"]) == []
    assert ts.conflicts("VERB", ["1SG.A", "3SG.A"])
    assert ts.conflicts("VERB", ["before H", "after L"]) == []
    assert ts.conflicts("VERB", ["before H", "before L"])
    assert ts.conflicts("NOUN", ["Past"])                 # not a noun tag


def test_default_structure_has_no_duplicate_codes():
    assert new_database().settings.tags.duplicate_codes() == []


def test_frames_come_last(db):
    e = db.entries[0]
    t = db.new_token(e, ["f2", "Plural", "before H"])
    assert db.expected_filename(e, t).endswith("_PL-xH-f2.wav")


# ---- references -----------------------------------------------------------

def test_reference_suggestions_never_fill_gaps(db):
    db.entries.append(db.new_entry("D011", "x", "y", "NOUN"))
    assert db.suggest_reference("D") == "D012"
    assert db.suggest_reference("A") == "A001"


# ---- saving -------------------------------------------------------------

def test_round_trip(tmp_path, db):
    path = tmp_path / "test.xml"
    storage.save(db, path)
    back = storage.load(path)
    assert storage.to_string(back) == storage.to_string(db)
    e = back.entries[0]
    assert back.lemma(e) == "ɗæær"
    assert back.gloss(e) == "goat"
    assert e.tokens[1].get("Translation", "en") == "goats"
    assert e.tokens[2].tags == ["Plural", "Genitive", "before H", "in isolation"]


def test_empty_fields_not_written(db):
    text = storage.to_string(db)
    assert "<Comment" not in text
    assert 'tags="Plural, in isolation"' in text


def test_save_keeps_backups(tmp_path, db):
    path = tmp_path / "test.xml"
    for _ in range(13):
        storage.save(db, path)
    backups = list((tmp_path / "Backups").glob("test_*.xml"))
    assert len(backups) == storage.BACKUPS_KEPT


def test_unicode_is_normalised(tmp_path, db):
    e = db.entries[0]
    e.set("Lemma", "é")                      # e + combining acute
    assert db.lemma(e) == "é"


def test_unknown_settings_survive(tmp_path, db):
    import xml.etree.ElementTree as ET
    db.settings.extra.append(ET.fromstring('<analysis syllabification="sonority"/>'))
    path = tmp_path / "t.xml"
    storage.save(db, path)
    assert 'syllabification="sonority"' in path.read_text(encoding="utf-8")
    assert storage.load(path).settings.extra


# ---- pitch ----------------------------------------------------------------

def test_pitch_parsing():
    assert pitch.parse("13 3 31, 5") == [[1, 3], [3], [3, 1], pitch.PAUSE, [5]]
    assert pitch.syllable_count("5 2, 2 3") == 4
    assert pitch.out_of_range("1 6 0", 1, 5) == [0, 6]
    assert pitch.from_dekereke("Aa5") == "12 21 5"


# ---- matrix ---------------------------------------------------------------

def _noun_db():
    d = new_database()
    for ref, lemma, gloss in (("D001", "dɪɪr", "goat"), ("D002", "rʉʉr", "lion")):
        e = d.new_entry(ref, lemma, gloss, "NOUN")
        for tags in (["Singular"], ["Singular", "Genitive"], ["Plural"], ["Plural", "Genitive"],
                     ["Singular", "Genitive", "before H"]):
            e.tokens.append(d.new_token(e, tags))
        d.entries.append(e)
    return d


def test_entry_tag_exactly():
    d = _noun_db()
    sg_gen = frozenset({"Singular", "Genitive"})
    lay = matrix.entry_tag_layout(d, d.entries, [sg_gen])
    assert [r.label for r in lay.rows] == ["SG + GEN"]
    assert len(lay.tokens(0, 0)) == 1                     # not the + xH one


def test_entry_tag_includes_adds_sub_rows():
    d = _noun_db()
    sg_gen = frozenset({"Singular", "Genitive"})
    lay = matrix.entry_tag_layout(d, d.entries, [sg_gen], mode=matrix.INCLUDES)
    assert [r.label for r in lay.rows] == ["SG + GEN", "+ xH"]
    assert len(lay.tokens(1, 1)) == 1


def test_auto_headers_ignore_defaults():
    d = _noun_db()
    lay = matrix.entry_tag_layout(d, d.entries, None)
    # As in the mockup: SG, SG + GEN, PL, PL + GEN.
    assert [r.label for r in lay.rows] == ["Citation", "SG", "SG + GEN", "SG + GEN + xH",
                                           "PL", "PL + GEN"]


def test_includes_with_automatic_headers():
    d = _noun_db()
    lay = matrix.entry_tag_layout(d, d.entries, None, mode=matrix.INCLUDES)
    assert [r.label for r in lay.rows] == ["Citation", "SG", "+ GEN", "+ GEN + xH", "PL", "+ GEN"]


def test_tag_tag_paradigm():
    d = new_database()
    v = d.new_entry("V001", "cəm", "eat", "VERB")
    for s in ("1SG.A", "3SG.A"):
        for o in ("1SG.O", "3SG.O"):
            v.tokens.append(d.new_token(v, [s, o]))
    subj = next(g for p, g in d.settings.tags.leaf_groups_for("VERB") if g.name == "Subject")
    obj = next(g for p, g in d.settings.tags.leaf_groups_for("VERB") if g.name == "Object")
    lay = matrix.tag_tag_layout(d, v, subj, obj)
    r = [x.label for x in lay.rows].index("3SG.A")
    c = [x.label for x in lay.cols].index("1SG.O")
    (entry, tok), = lay.tokens(r, c)
    assert set(tok.tags) >= {"3SG.A", "1SG.O"}
    assert "—" in [x.label for x in lay.cols]            # the citation token has no object


def test_reading_order_is_column_by_column():
    lay = matrix.Layout(rows=[matrix.AxisItem("a"), matrix.AxisItem("b")],
                        cols=[matrix.AxisItem("x"), matrix.AxisItem("y")])
    assert lay.reading_order() == [(0, 0), (1, 0), (0, 1), (1, 1)]


def test_token_filter():
    f = matrix.TokenFilter(tags={"Number": {"Plural"}})
    assert f.accepts(Token(tags=["Plural", "Genitive"]))
    assert not f.accepts(Token(tags=["Singular"]))
    assert matrix.TokenFilter(citation_only=True).accepts(Token())


# ---- audio ----------------------------------------------------------------

def test_wav_metadata(tmp_path):
    p = tmp_path / "x.wav"
    audio.write_wav(p, np.sin(np.linspace(0, 100, 4410)) * 0.5, 44100, 16, artist="SP1", date="2026-10-16")
    info = audio.read_info(p)
    assert info["IART"] == "SP1" and info["ICRD"] == "2026-10-16"
    data, rate = audio.read_wav(p)
    assert rate == 44100 and len(data) == 4410


def test_wav_24_bit(tmp_path):
    p = tmp_path / "y.wav"
    samples = np.array([0.0, 0.5, -0.5, 0.25])
    audio.write_wav(p, samples, 48000, 24)
    data, _ = audio.read_wav(p)
    assert np.allclose(data, samples, atol=1e-5)
