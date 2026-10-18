"""Pull (idea 7, stage 4): checking clipped utterances against their TextGrid lines."""

import os
import time
from pathlib import Path

from lemmatrix import pull, textgrid as tgmod
from lemmatrix.defaults import new_database
from lemmatrix.model import ClipSource, Text


def _write(path, tx, ft, ge=None, end=4.0):
    tiers = {"tx": tx, "ft": ft}
    if ge is not None:
        tiers["ge"] = ge
    tgmod.write_example(path, tiers, end)
    st = os.stat(path)                                   # a different time each write, to the second
    _write.n = getattr(_write, "n", 0) + 10
    os.utime(path, (st.st_atime, time.time() + _write.n))


TX = [(0.5, 1.5, "ʔəŋ kɒ"), (2.0, 3.0, "ɛ ŋəə")]
FT = [(0.5, 1.5, "the hare ran"), (2.0, 3.0, "where is he?")]


def _setup(tmp_path):
    db = new_database()
    db.path = str(tmp_path / "Lex.xml")
    folder = tmp_path / "Soundfiles" / "Texts"
    folder.mkdir(parents=True)
    _write(folder / "t.TextGrid", TX, FT)
    t = Text(ref="T001", textgrid="t.TextGrid")
    db.texts.append(t)
    lines = tgmod.read_lines(folder / "t.TextGrid", db.mapping_for(t))
    u = db.new_utterance("W001", "hare ran", "", "")
    ln = lines[0]
    u.token.set("Phonetic", ln.values["Phonetic"])
    u.token.set("Translation", ln.values["Translation:en"], "en", True)
    u.source = ClipSource(t.id, ln.start, ln.end, dict(ln.copied), tgmod.modified(folder / "t.TextGrid"))
    db.utterances.append(u)
    return db, t, u, folder / "t.TextGrid"


def test_unchanged_textgrid_is_ok_without_reading(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    c = pull.check(db, u)
    assert c.status == pull.OK and not c.flagged and c.line is None


def test_saved_again_but_the_line_is_the_same(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    _write(grid, TX, [FT[0], (2.0, 3.0, "where is she?")])     # another line changed
    c = pull.check(db, u)
    assert c.status == pull.OK and not c.flagged


def test_changed_text_is_flagged_and_pulled(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    u.token.set("Comment", "my own note")                       # edits in Lemmatrix stay
    _write(grid, [(0.5, 1.5, "ʔəŋ kɒɒ"), TX[1]], FT)
    c = pull.check(db, u)
    assert c.status == pull.CHANGED and c.flagged and c.pullable and not c.moved
    assert [(ch.key, ch.old, ch.new) for ch in c.changes] == [("Phonetic", "ʔəŋ kɒ", "ʔəŋ kɒɒ")]
    after = pull.pulled(db, c)
    assert after.token.get("Phonetic") == "ʔəŋ kɒɒ" and after.token.get("Comment") == "my own note"
    assert after.source.copied["tx"] == "ʔəŋ kɒɒ" and after.source.modified == tgmod.modified(grid)
    assert u.token.get("Phonetic") == "ʔəŋ kɒ"                  # a copy: the utterance itself is untouched
    u.__dict__.update(after.__dict__)
    assert pull.check(db, u).status == pull.OK


def test_an_edit_in_lemmatrix_is_not_a_change(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    u.token.set("Phonetic", "ʔə̀ŋ kɒ̄")                          # corrected in Lemmatrix
    _write(grid, TX, FT)                                        # saved in Praat, nothing changed
    assert pull.check(db, u).status == pull.OK


def test_moved_boundaries(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    _write(grid, [(0.45, 1.6, "ʔəŋ kɒ"), TX[1]], [(0.45, 1.6, "the hare ran"), FT[1]])
    c = pull.check(db, u)
    assert c.status == pull.MOVED and c.moved and c.pullable and not c.changes
    after = pull.pulled(db, c)
    assert (after.source.start, after.source.end) == (0.45, 1.6)


def test_changed_and_moved_with_a_translation(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    _write(grid, [(0.4, 1.5, "ʔəŋ kɒ"), TX[1]], [(0.4, 1.5, "the hare ran off"), FT[1]])
    c = pull.check(db, u)
    assert c.status == pull.CHANGED and c.moved
    assert [ch.key for ch in c.changes] == ["Translation:en"]
    assert pull.pulled(db, c).token.get("Translation", "en") == "the hare ran off"
    assert "moved" in pull.describe(c)


def test_a_new_tier_fills_its_field(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    _write(grid, TX, FT, ge=[(0.5, 1.0, "hare"), (1.0, 1.5, "run.PST")])
    c = pull.check(db, u)
    assert [(ch.key, ch.old, ch.new) for ch in c.changes] == [("Morphemes", "", "hare run.PST")]
    assert pull.pulled(db, c).token.get("Morphemes") == "hare run.PST"


def test_line_not_found_and_missing_files(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    _write(grid, [TX[1]], [FT[1]])
    c = pull.check(db, u)
    assert c.status == pull.NOT_FOUND and c.flagged and not c.pullable
    grid.unlink()
    assert pull.check(db, u).status == pull.NO_TEXTGRID
    db.texts.remove(t)
    c = pull.check(db, u)
    assert c.status == pull.NO_TEXT and not c.flagged             # a deleted text isn't a problem
    assert pull.unlinked(c).source is None and u.source is not None


def test_find_line_keeps_to_the_speakers_tiers():
    a = tgmod.Line(0.5, 1.5, "SP1", copied={"tx@SP1": "a"})
    b = tgmod.Line(0.5, 1.5, "ABC", copied={"tx@ABC": "b"})
    src = ClipSource("x", 0.5, 1.5, {"tx@ABC": "b"})
    assert pull.find_line([a, b], src) is b
    src = ClipSource("x", 0.6, 1.4, {"tx@SP1": "a"})
    assert pull.find_line([b, a], src) is a


def test_check_all(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    other = db.new_utterance("W002", "", "", "")
    db.utterances.append(other)
    checks = pull.check_all(db)
    assert list(checks) == [u.id]


def test_a_tier_gone_altogether_is_not_a_change(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    tgmod.write_example(grid, {"tx": TX}, 4.0)                  # ft removed (or renamed)
    st = os.stat(grid)
    os.utime(grid, (st.st_atime, time.time() + 500))
    assert pull.check(db, u).status == pull.OK
    _write(grid, TX, [(2.0, 3.0, "where is he?")])               # ft there, but this line's emptied
    c = pull.check(db, u)
    assert [(ch.key, ch.new) for ch in c.changes] == [("Translation:en", "")]
