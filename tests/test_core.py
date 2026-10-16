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
    assert db.expected_filename(e, e.tokens[0]) == "LXX-VXX_D009_goat.wav"
    assert db.expected_filename(e, e.tokens[1]) == "LXX-VXX_D009_goat_PL.wav"
    assert db.expected_filename(e, e.tokens[2]) == "LXX-VXX_D009_goat_PL-GEN-xH.wav"
    db.metadata.variety_code = ""
    assert db.expected_filename(e, e.tokens[0]) == "LXX_D009_goat.wav"


def test_speaker_is_optional_in_the_pattern(db):
    e = db.entries[0]
    db.settings.filename_pattern = "{language}-{variety}-{speaker}_{reference}_{gloss}_{tags}"
    assert db.expected_filename(e, e.tokens[0]) == "LXX-VXX-SP1_D009_goat.wav"
    e.tokens[0].speaker = ""
    assert db.expected_filename(e, e.tokens[0]) == "LXX-VXX_D009_goat.wav"


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

def test_pitch_notation():
    syl = pitch.parse("4:42 42:1, 14")
    assert [x.points for x in syl if x != pitch.PAUSE] == [[4, 4, 2], [4, 2, 1], [1, 4]]
    assert [x.steps for x in syl if x != pitch.PAUSE] == [[2, 1], [1, 2], [1]]
    assert syl[2] == pitch.PAUSE
    assert pitch.parse("1::1")[0].steps == [3]
    assert pitch.parse("5")[0].points == [5, 5]                # a lone digit is a short level
    assert pitch.normalise("5 2, 13 1:1") == "55 22, 13 1:1"
    assert pitch.syllable_count("5 2, 2 3") == 4
    assert pitch.out_of_range("11 66 00", 1, 5) == [0, 6]
    assert pitch.problems(":13", 1, 5)                          # stray colon is flagged
    assert not pitch.problems("1:4", 1, 5)


def test_old_pitch_is_doubled_on_load(tmp_path, db):
    path = tmp_path / "p.xml"
    storage.save(db, path)
    text = path.read_text(encoding="utf-8").replace("<Pitch>21</Pitch>", "<Pitch>2 1</Pitch>")
    path.write_text(text, encoding="utf-8")
    assert storage.load(path).entries[0].tokens[0].get("Pitch") == "22 11"


# ---- filters --------------------------------------------------------------

def test_text_filters():
    from lemmatrix.filters import TextFilter, ANYWHERE, WHOLE, START, END, REGEX
    assert TextFilter("deet").matches("dɪɪʈʰ") is False         # ʈ is a different letter
    assert TextFilter("deet").matches("dɪɪtʰ")                  # ʰ ignored
    assert TextFilter("deet", WHOLE).matches("dɪɪtʰ")
    assert not TextFilter("deet", WHOLE, match_diacritics=True).matches("dɪɪtʰ")
    assert TextFilter("a").matches("á")
    assert TextFilter("Goat", WHOLE).matches("goat")
    assert not TextFilter("Goat", WHOLE, match_case=True).matches("goat")
    assert TextFilter("go", START).matches("goat") and TextFilter("at", END).matches("goat")
    assert TextFilter(r"^d.*l$", REGEX).matches("dɪɪr")
    assert not TextFilter("[", REGEX).matches("x")              # bad pattern matches nothing


def test_choice_filters():
    from lemmatrix.filters import ChoiceFilter, Blanks, NonBlanks, matches, ANY, NONE, EXACTLY
    assert matches(ChoiceFilter({"NOUN"}), "NOUN") and not matches(ChoiceFilter({"NOUN"}), "VERB")
    assert matches(ChoiceFilter({"NOUN"}, NONE), "VERB")
    tags = ["Plural", "Genitive", "in isolation"]
    assert matches(ChoiceFilter({"Plural"}), tags)
    assert not matches(ChoiceFilter({"Plural"}, EXACTLY), tags, {"in isolation"})
    assert matches(ChoiceFilter({"Plural", "Genitive"}, EXACTLY), tags, {"in isolation"})
    assert matches(Blanks(), "") and matches(NonBlanks(), "x") and matches(Blanks(), [])


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


def S(*tags, match=matrix.EXACT):
    return matrix.Spec(frozenset(tags), match)


def test_exact_ignores_defaults_loose_takes_extras():
    d = _noun_db()
    cfg = matrix.MatrixConfig(x=[matrix.Spec.citation(), S("Singular", match=matrix.LOOSE),
                                 S("Plural")])
    lay = matrix.lemma_tag_layout(d, d.entries, cfg)
    assert [c.label for c in lay.cols] == ["Citation", "SG …", "PL"]
    assert len(lay.tokens(0, 0)) == 1                       # citation
    assert len(lay.tokens(0, 1)) == 3                       # SG, SG+GEN, SG+GEN+xH side by side
    assert [t.tags[:2] for _, t in lay.tokens(0, 1)][0] == ["Singular", "in isolation"]
    assert len(lay.tokens(0, 2)) == 1                       # exact PL (has in isolation too)


def test_extra_chips_for_side_by_side_tokens():
    d = _noun_db()
    spec = S("Singular", match=matrix.LOOSE)
    lay = matrix.lemma_tag_layout(d, d.entries, matrix.MatrixConfig(x=[spec]))
    defaults = matrix.default_names(d)
    labels = [matrix.extra_chips(d, t, spec, "NOUN", defaults) for _, t in lay.tokens(0, 0)]
    assert labels == [[], ["+GEN"], ["+GEN", "+xH"]]


def test_automatic_columns():
    d = _noun_db()
    lay = matrix.lemma_tag_layout(d, d.entries, None)
    assert [c.label for c in lay.cols] == ["Citation", "SG", "SG + GEN", "SG + GEN + xH",
                                           "PL", "PL + GEN"]


def test_tag_tag_paradigm_and_contradictions():
    d = new_database()
    v = d.new_entry("V001", "cəm", "eat", "VERB")
    for s_ in ("1SG.A", "3SG.A"):
        for o in ("1SG.O", "3SG.O"):
            v.tokens.append(d.new_token(v, [s_, o]))
    cfg = matrix.MatrixConfig(kind=matrix.TAG_TAG, word_class="VERB",
                              y=[S("1SG.A"), S("3SG.A")], x=[S("1SG.O"), S("3SG.O"), S("1SG.A")])
    lay = matrix.tag_tag_layout(d, v, cfg)
    (entry, tok), = lay.tokens(1, 0)
    assert {"3SG.A", "1SG.O"} <= set(tok.tags)
    assert (1, 2) in lay.greyed and (0, 2) not in lay.greyed  # 3SG.A + 1SG.A contradict
    other = matrix.MatrixConfig(kind=matrix.TAG_TAG, word_class="NOUN", y=[S("Plural")], x=[S("Genitive")])
    assert "for NOUN" in matrix.tag_tag_layout(d, v, other).message
    assert matrix.tag_tag_layout(d, v, None).message == "Please configure a matrix."


def test_matrix_class():
    d = _noun_db()
    d.entries.append(d.new_entry("X001", "zz", "thing", ""))
    assert len(matrix.in_class(d, d.entries, "NOUN")) == 2
    assert len(matrix.in_class(d, d.entries, matrix.NO_CLASS)) == 1


def test_saved_matrices_round_trip(tmp_path, db):
    cfg = matrix.MatrixConfig(name="Noun cases", kind=matrix.LEMMA_TAG, word_class="NOUN",
                              x=[matrix.Spec.citation(), S("Singular", match=matrix.LOOSE)],
                              cell=["Phonetic"])
    db.settings.matrices.append(cfg)
    path = tmp_path / "m.xml"
    storage.save(db, path)
    back = storage.load(path).settings.matrices
    assert back == [cfg]


def test_reading_order_is_column_by_column():
    lay = matrix.Layout(rows=[matrix.AxisItem("a"), matrix.AxisItem("b")],
                        cols=[matrix.AxisItem("x"), matrix.AxisItem("y")])
    assert lay.reading_order() == [(0, 0), (1, 0), (0, 1), (1, 1)]


def test_closed_lists_round_trip(tmp_path, db):
    from lemmatrix.model import ListItem
    f = db.settings.entry_field("ToneClass")
    f.items = [ListItem("Low", [ListItem("L/L"), ListItem("L/H")]), ListItem("H/L")]
    path = tmp_path / "c.xml"
    storage.save(db, path)
    g = storage.load(path).settings.entry_field("ToneClass")
    assert g.closed and g.all_values() == ["Low", "L/L", "L/H", "H/L"]


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
