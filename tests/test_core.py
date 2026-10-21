# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Tests for the data model, file names, saving and the matrix layout."""

from pathlib import Path

import numpy as np
import pytest

from lemmatrix import audio, matrix, pitch, storage
from lemmatrix.defaults import new_database
from lemmatrix.model import ListItem, Participant, Token, forbidden_in


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


def test_spaces_and_punctuation_are_written_as_praat_writes_them(db):
    """19 October: as Praat names a file's object, so its Save suggests this very name."""
    e = db.new_entry("V012", "rum", "to run", "VERB")
    db.metadata.variety_code = ""
    assert db.expected_filename(e, e.tokens[0]) == "LXX_V012_to_run.wav"


def test_forbidden_characters():
    assert forbidden_in("he/she?") == "/?"
    assert forbidden_in("goat") == ""


# ---- tags -----------------------------------------------------------------

def test_defaults_are_preselected_except_on_citation(db):
    e = db.entries[0]
    assert e.tokens[0].tags == []                         # citation stays tagless
    assert e.tokens[1].tags == ["Plural", "isolation"]
    v = db.new_entry("V001", "cəm", "eat", "VERB")
    t = db.new_token(v, ["Past", "Negative"])
    assert t.tags == ["Simple", "Past", "Indicative", "Negative", "isolation"]


def test_defaults_add_nothing_to_file_names(db):
    v = db.new_entry("V001", "cəm", "eat", "VERB")
    db.metadata.variety_code = ""
    t = db.new_token(v, ["Past", "1SG.A"])
    assert db.expected_filename(v, t) == "LXX_V001_eat_1SG_A-PST.wav"


def test_one_tag_per_group():
    d = new_database()
    ts = d.settings.tags
    assert ts.conflicts(["1SG.A", "3SG.O"]) == []
    assert ts.conflicts(["1SG.A", "3SG.A"])
    assert ts.conflicts(["before H", "after L"]) == []
    assert ts.conflicts(["before H", "before L"])
    assert ts.conflicts(["Past", "Plural"]) == []          # any tag can go on any token
    assert ts.conflicts(["Nonsense"])                      # but it must be in the structure


def test_usual_for_hints():
    d = new_database()
    ts = d.settings.tags
    assert ts.unusual(["NOUN"], ["Past", "Plural", "isolation"]) == ["Past"]
    assert ts.unusual(["VERB"], ["Past", "Plural"]) == ["Plural"]
    assert ts.unusual([], ["Past"]) == ["Past"]            # no word class: only hint-less groups are usual
    assert ts.with_defaults(["Plural"], ["NOUN"]) == ["Plural", "isolation"]
    assert ts.with_defaults(["Past"], ["VERB"]) == ["Simple", "Past", "Indicative", "Affirmative", "isolation"]
    # a nested word class counts as the class above it
    wcf = d.settings.entry_field("word-class")
    noun = next(i for i in wcf.items if i.name == "NOUN")
    noun.children.append(ListItem("Relational"))
    e = d.new_entry("C001", "bəə", "father", "Relational")
    assert d.classes(e) == ["Relational", "NOUN"]
    assert d.unusual_tags(e, ["Plural", "Past"]) == ["Past"]
    # subgroups inherit their parent's hint unless they have their own
    verb = next(g for g in ts.groups if g.name == "VERB")
    tense = next(g for g in verb.groups if g.name == "Tense")
    tense.usual = ["VERB", "NOUN"]
    assert d.unusual_tags(e, ["Past", "Negative"]) == ["Negative"]
    ts.rename_classes({"VERB": "Verbal"})
    assert verb.usual == ["Verbal"] and tense.usual == ["Verbal", "NOUN"]


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
    assert e.tokens[2].tags == ["Plural", "Genitive", "before H", "isolation"]


def test_empty_fields_not_written(db):
    text = storage.to_string(db)
    assert "<Comment" not in text
    assert 'tags="Plural, isolation"' in text


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


# ---- filters --------------------------------------------------------------

def test_text_filters():
    from lemmatrix.filters import TextFilter, ANYWHERE, WHOLE, START, END, REGEX
    assert TextFilter("dɪɪt").matches("dɪɪʈʰ") is False         # ʈ is a different letter
    assert TextFilter("dɪɪt").matches("dɪɪtʰ")                  # ʰ ignored
    assert TextFilter("dɪɪt", WHOLE).matches("dɪɪtʰ")
    assert not TextFilter("dɪɪt", WHOLE, match_diacritics=True).matches("dɪɪtʰ")
    assert TextFilter("a").matches("á")
    assert TextFilter("Goat", WHOLE).matches("goat")
    assert not TextFilter("Goat", WHOLE, match_case=True).matches("goat")
    assert TextFilter("go", START).matches("goat") and TextFilter("at", END).matches("goat")
    assert TextFilter(r"^d.*r$", REGEX).matches("dɪɪr")
    assert not TextFilter("[", REGEX).matches("x")              # bad pattern matches nothing


def test_choice_filters():
    from lemmatrix.filters import ChoiceFilter, Blanks, NonBlanks, matches, ANY, NONE, EXACTLY
    assert matches(ChoiceFilter({"NOUN"}), "NOUN") and not matches(ChoiceFilter({"NOUN"}), "VERB")
    assert matches(ChoiceFilter({"NOUN"}, NONE), "VERB")
    tags = ["Plural", "Genitive", "isolation"]
    assert matches(ChoiceFilter({"Plural"}), tags)
    assert not matches(ChoiceFilter({"Plural"}, EXACTLY), tags, {"isolation"})
    assert matches(ChoiceFilter({"Plural", "Genitive"}, EXACTLY), tags, {"isolation"})
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
    assert [t.tags[:2] for _, t in lay.tokens(0, 1)][0] == ["Singular", "isolation"]
    assert len(lay.tokens(0, 2)) == 1                       # exact PL (has isolation too)


def test_extra_chips_for_side_by_side_tokens():
    d = _noun_db()
    spec = S("Singular", match=matrix.LOOSE)
    lay = matrix.lemma_tag_layout(d, d.entries, matrix.MatrixConfig(x=[spec]))
    defaults = matrix.default_names(d)
    labels = [matrix.extra_chips(d, t, spec, d.entries[0], defaults) for _, t in lay.tokens(0, 0)]
    assert labels == [[], ["+GEN"], ["+GEN", "+xH"]]


def test_lemma_tag_starts_blank_and_restore_all_present():
    d = _noun_db()
    lay = matrix.lemma_tag_layout(d, d.entries, None)
    assert not lay.cols and "Blank matrix" in lay.message
    cfg = matrix.MatrixConfig(x=matrix.auto_specs(d, d.entries))   # Configure matrix → Restore all present
    lay = matrix.lemma_tag_layout(d, d.entries, cfg)
    assert [c.label for c in lay.cols] == ["Citation", "SG", "SG + GEN", "SG + GEN + xH",
                                           "PL", "PL + GEN"]


def test_tag_tag_paradigm_and_contradictions():
    d = new_database()
    v = d.new_entry("V001", "cəm", "eat", "VERB")
    for s_ in ("1SG.A", "3SG.A"):
        for o in ("1SG.O", "3SG.O"):
            v.tokens.append(d.new_token(v, [s_, o]))
    cfg = matrix.MatrixConfig(kind=matrix.TAG_TAG,
                              y=[S("1SG.A"), S("3SG.A")], x=[S("1SG.O"), S("3SG.O"), S("1SG.A")])
    lay = matrix.tag_tag_layout(d, v, cfg)
    (entry, tok), = lay.tokens(1, 0)
    assert {"3SG.A", "1SG.O"} <= set(tok.tags)
    assert (1, 2) in lay.greyed and (0, 2) not in lay.greyed  # 3SG.A + 1SG.A contradict
    other = matrix.MatrixConfig(kind=matrix.TAG_TAG, y=[S("Plural")], x=[S("Genitive")])
    lay = matrix.tag_tag_layout(d, v, other)                 # any matrix works for any lemma
    assert not lay.message and not lay.cells
    assert all(isinstance(c, matrix.Unusual) for c in lay.rows[0].chips)   # nominal tags on a verb
    assert matrix.tag_tag_layout(d, v, None).message == "Please configure a matrix."


def test_saved_matrices_round_trip(tmp_path, db):
    cfg = matrix.MatrixConfig(name="Noun cases", kind=matrix.LEMMA_TAG,
                              x=[matrix.Spec.citation(), S("Singular", match=matrix.LOOSE)],
                              cell=["Phonetic"])
    db.settings.matrices.append(cfg)
    path = tmp_path / "m.xml"
    storage.save(db, path)
    from lemmatrix import workspace                 # in the workspace since format 7 (idea 36)
    workspace.save(workspace.Workspace(), db)
    assert "<matrix" not in path.read_text(encoding="utf-8")
    again = storage.load(path)
    workspace.load(workspace.path_for(path), again)
    assert again.settings.matrices == [cfg]


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


def test_pitch_drawing_gaps():
    from lemmatrix.ui.widgets import pitch_width
    # 11 is one step; one unit between syllables; a comma makes it two
    assert pitch_width("11", 1) == 1
    assert pitch_width("11 11", 1) == 3
    assert pitch_width("11 , 11", 1) == 4
    assert pitch_width("1:1 4:42", 1) == 2 + 1 + 3


def test_pitch_sound_voices_follow_the_tune():
    import numpy as np
    from lemmatrix import pitchsound as ps
    for voice in ps.VOICES:
        a = ps.synthesise("11", 1, 5, voice, seed=1)
        b = ps.synthesise("55", 1, 5, voice, seed=1)
        assert np.isfinite(a).all() and 0 < np.abs(a).max() <= 1
        # higher digits sound higher: compare where the energy sits
        def centroid(x):
            sp = np.abs(np.fft.rfft(x))
            f = np.fft.rfftfreq(len(x), 1 / ps.RATE)
            return (sp * f).sum() / sp.sum()
        assert centroid(b) > centroid(a)
    # a comma is a longer silence than a syllable break
    assert len(ps.synthesise("11 , 11", voice="buzz")) > len(ps.synthesise("11 11", voice="buzz"))


def test_open_in_praat_runs_a_view_and_edit_script(tmp_path, monkeypatch):
    from lemmatrix import praat
    import sys
    # Windows doesn't allow " in file names; the script's quoting is checked wherever it can be
    wav = tmp_path / ("a 'quoted' name.wav" if sys.platform == "win32" else 'a "quoted" name.wav')
    wav.write_bytes(b"RIFF")
    exe = tmp_path / "Praat.exe"
    exe.write_bytes(b"")
    calls = []
    monkeypatch.setattr(praat.subprocess, "Popen", lambda args, **kw: calls.append(args))
    praat.open_sound(str(exe), wav)
    args = calls[0]
    assert args[0] == str(exe) and "--send" in args
    script = open(args[-1], encoding="utf-8").read()
    quoted = "a 'quoted' name.wav" if sys.platform == "win32" else 'a ""quoted"" name.wav'
    assert quoted in script and "View & Edit" in script
    import pytest
    with pytest.raises(praat.PraatError):
        praat.open_sound(str(tmp_path / "missing.exe"), wav)


def test_same_file_allows_case_only_renames(tmp_path):
    from lemmatrix import storage
    a = tmp_path / "x-F1.wav"
    a.write_bytes(b"RIFF")
    assert storage.same_file(a, a)
    assert not storage.same_file(a, tmp_path / "other.wav")


def test_open_marker_lifecycle(tmp_path, monkeypatch):
    import json
    import os
    from lemmatrix import lock
    db = tmp_path / "x.xml"
    db.write_text("<database/>")
    assert lock.held_elsewhere(db) is None
    lock.claim(db)
    assert lock.read(db).mine() and lock.held_elsewhere(db) is None
    lock.release(db)
    assert not lock.lock_path(db).exists()
    # another computer's marker is reported
    lock.lock_path(db).write_text(json.dumps({"computer": "LAPTOP", "user": "josh", "pid": 1,
                                              "opened": "2026-10-17 09:14:00", "seen": "2026-10-17 09:40:00"}))
    info = lock.held_elsewhere(db)
    assert info and info.computer == "LAPTOP" and "09:40" in info.describe()
    lock.release(db)                                   # not ours: left alone
    assert lock.lock_path(db).exists()
    # a marker left by a crash on this computer is ignored
    lock.lock_path(db).write_text(json.dumps({"computer": lock.this_computer(), "pid": 999999999}))
    assert lock.held_elsewhere(db) is None



DATA = Path(__file__).resolve().parent / "data"


def test_pasted_control_characters_never_make_a_file_unreadable(tmp_path):
    import shutil
    from lemmatrix import notebook as nb, storage
    shutil.copy2(Path(__file__).resolve().parent.parent / "samples" / "Sample.xml", tmp_path / "S.xml")
    db = storage.load(tmp_path / "S.xml")
    db.entries[0].tokens[0].set("Comment", "from Word\x0bnext\x01")
    storage.save(db, tmp_path / "S.xml")
    again = storage.load(tmp_path / "S.xml")                       # opens again
    assert again.entries[0].tokens[0].get("Comment") == "from Word next"
    # a file broken by an older version is repaired on opening, with a note
    text = (tmp_path / "S.xml").read_text(encoding="utf-8").replace("from Word next", "from\x0bWord")
    (tmp_path / "S.xml").write_text(text, encoding="utf-8")
    fixed = storage.load(tmp_path / "S.xml")
    assert fixed.entries[0].tokens[0].get("Comment") == "from Word" and fixed.load_notes
    book = nb.Notebook()
    book.add_session("2026-10-01").notes = "line one\x0bline two"
    nb.save(book, tmp_path / "S.notebook")
    assert nb.load(tmp_path / "S.notebook").session("2026-10-01").notes == "line one\nline two"


def test_backups_keep_recent_and_spread_out_older_ones(tmp_path):
    import datetime as dt
    import os
    from lemmatrix import storage
    today = dt.date(2026, 10, 18)
    files = []
    for days in range(0, 60):                  # one backup a day for two months, 3 today
        for k in range(3 if days == 0 else 1):
            f = tmp_path / f"db_{(today - dt.timedelta(days=days)).isoformat()}_12000{k}.xml"
            f.write_text("x")
            t = dt.datetime.combine(today - dt.timedelta(days=days), dt.time(12, 0, k)).timestamp()
            os.utime(f, (t, t))
            files.append(f)
    keep = storage.backups_to_keep(files, recent=10, today=today)
    ages = sorted((today - dt.date.fromtimestamp(f.stat().st_mtime)).days for f in keep)
    assert 1 in ages and 2 in ages and 7 in ages               # yesterday, the day before, a week ago
    assert any(a >= 30 for a in ages)                          # a month ago
    assert len(keep) <= 22


def test_anonymous_backup(tmp_path):
    import shutil
    import pyzipper
    from lemmatrix import anonymise, notebook as nb, storage
    from lemmatrix.model import Location, Person
    src = Path(__file__).resolve().parent.parent / "samples"
    shutil.copy2(src / "Sample.xml", tmp_path / "S.xml")
    shutil.copytree(src / "Soundfiles", tmp_path / "Soundfiles")
    db = storage.load(tmp_path / "S.xml")
    db.metadata.participants = [Person("SP1", "Sample Speaker", "a farmer", "Consent/SP1.pdf")]
    db.metadata.researchers = [Person("JS", "Joshua Smolders")]
    db.metadata.author = "Joshua Smolders"
    (tmp_path / "Consent").mkdir()
    (tmp_path / "Consent" / "SP1.pdf").write_bytes(b"%PDF consent")
    db.metadata.locations = [Location("Ethiopia", "ET", children=[
        Location("Gambella Regional State", "GBRS", children=[Location("Pade", "PADE")])])]
    db.entries[0].tokens[0].set("Comment", "Sample said this twice; ask sample speaker again")
    book = nb.Notebook()
    s = book.add_session("2026-10-01")
    s.participants, s.locations, s.notes = ["SP1"], ["PADE"], "Paid Sample for five sessions."
    opts = anonymise.Options(researchers=True, recordings=True, place_levels=2, consent_password="pw")
    rep = anonymise.export(db, book, tmp_path / "out", opts)
    out = storage.load(tmp_path / "out" / "S (anonymous).xml")
    p = out.metadata.participants[0]
    assert (p.code, p.name, p.description, p.consent) == ("SP1", "", "", "")
    assert out.metadata.researchers[0].name == "" and out.metadata.author == ""
    assert out.entries[0].tokens[0].get("Comment") == "SP1 said this twice; ask SP1 again"
    assert [x.code for x in out.metadata.locations[0].children] == ["GBRS"] and not out.metadata.locations[0].children[0].children
    back = nb.load(tmp_path / "out" / "S (anonymous).notebook").session("2026-10-01")
    assert back.notes == "Paid SP1 for five sessions." and back.locations == ["GBRS"]
    assert rep.recordings > 0 and (tmp_path / "out" / "Soundfiles" / "Tokens").is_dir()
    with pyzipper.AESZipFile(tmp_path / "out" / "S consent forms (password).zip") as zf:
        zf.setpassword(b"pw")
        assert zf.read("SP1/SP1.pdf") == b"%PDF consent"
    assert db.metadata.participants[0].name == "Sample Speaker"        # the original is untouched
    assert "Sample" in anonymise.summary(rep, opts)
