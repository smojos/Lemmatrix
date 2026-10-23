# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
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


# ---- Push (agreed 18 October) ----------------------------------------------------------------

def _word_level(tmp_path):
    """A text whose Morphemes tier has a segment per word."""
    db, t, u, grid = _setup(tmp_path)
    _write(grid, TX, FT, ge=[(0.5, 1.0, "hare"), (1.0, 1.5, "run.PST"), (2.0, 3.0, "where.3SG")])
    lines = tgmod.read_lines(grid, db.mapping_for(t))
    u.token.set("Morphemes", lines[0].values["Morphemes"])
    u.source = ClipSource(t.id, 0.5, 1.5, dict(lines[0].copied), tgmod.modified(grid))
    return db, t, u, grid


def test_edits_in_lemmatrix_are_noticed_but_not_flagged(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    assert pull.check(db, u).edited == []
    u.token.set("Phonetic", "ʔə̀ŋ kɒ̄")
    c = pull.check(db, u)
    assert c.status == pull.OK and not c.flagged and c.pushable and c.edited == ["tx"]
    u.token.set("Phonetic", "ʔəŋ  kɒ")                           # only spacing at the edges/doubled: the same
    assert pull.check(db, u).edited == []


def test_push_writes_the_tier_and_keeps_a_backup(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    u.token.set("Phonetic", "ʔə̀ŋ kɒ̄")
    c = pull.check(db, u)
    plan = pull.push_plan(db, c)
    assert [(ch.tier, ch.old, ch.new, ch.segments) for ch in plan] == [("tx", "ʔəŋ kɒ", "ʔə̀ŋ kɒ̄", 1)]
    after = pull.push(db, t, [(c, plan)])
    u.__dict__.update(after[u.id].__dict__)
    assert tgmod.read_lines(grid, db.mapping_for(t))[0].values["Phonetic"] == "ʔə̀ŋ kɒ̄"
    assert tgmod.read_lines(grid, db.mapping_for(t))[1].values["Phonetic"] == "ɛ ŋəə"   # other lines kept
    c = pull.check(db, u)
    assert c.status == pull.OK and not c.edited and u.source.copied["tx"] == "ʔə̀ŋ kɒ̄"
    backups = list((tmp_path / "Backups").iterdir())
    assert len(backups) == 1 and backups[0].name.startswith("t_") and "ʔəŋ kɒ" in backups[0].read_text(encoding="utf-8")


def test_push_merges_a_word_level_tier(tmp_path):
    db, t, u, grid = _word_level(tmp_path)
    u.token.set("Morphemes", "hare run.PST.3SG")
    c = pull.check(db, u)
    plan = pull.push_plan(db, c)
    assert [(ch.tier, ch.segments, ch.merges) for ch in plan] == [("ge", 2, True)]
    pull.push(db, t, [(c, plan)])
    from praatio import textgrid
    tg = textgrid.openTextgrid(str(grid), includeEmptyIntervals=False)
    assert [tuple(e) for e in tg.getTier("ge").entries] == [(0.5, 1.5, "hare run.PST.3SG"), (2.0, 3.0, "where.3SG")]


def test_push_only_the_chosen_tiers(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    u.token.set("Phonetic", "ʔə̀ŋ kɒ̄")
    u.token.set("Translation", "the hare ran away", "en", True)
    c = pull.check(db, u)
    assert sorted(c.edited) == ["ft", "tx"]
    plan = [ch for ch in pull.push_plan(db, c) if ch.tier == "tx"]
    u.__dict__.update(pull.push(db, t, [(c, plan)])[u.id].__dict__)
    c = pull.check(db, u)
    assert c.edited == ["ft"] and c.status == pull.OK                # the translation still waits


def test_push_keeps_a_praat_change_on_another_tier_visible(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    _write(grid, TX, [(0.5, 1.5, "the hare ran off"), FT[1]])        # changed in Praat, not pulled
    u.token.set("Phonetic", "ʔə̀ŋ kɒ̄")                                  # edited here
    c = pull.check(db, u)
    assert c.status == pull.CHANGED and c.edited == ["tx"]
    plan = pull.push_plan(db, c)
    assert [(ch.tier, ch.edited) for ch in plan] == [("tx", True), ("ft", False)]   # ft: Praat's change
    u.__dict__.update(pull.push(db, t, [(c, [ch for ch in plan if ch.edited])])[u.id].__dict__)
    c = pull.check(db, u)
    assert c.status == pull.CHANGED and [ch.tier for ch in c.changes] == ["ft"] and not c.edited


def test_praat_reads_a_pushed_textgrid(tmp_path):
    parselmouth = __import__("pytest").importorskip("parselmouth")
    db, t, u, grid = _word_level(tmp_path)
    u.token.set("Morphemes", "hare run.PST.3SG")
    c = pull.check(db, u)
    pull.push(db, t, [(c, pull.push_plan(db, c))])
    script = (f'Read from file: "{grid}"\nn = Get number of intervals: 3\nlabel$ = Get label of interval: 3, 2\n'
              'appendInfoLine: n\nappendInfoLine: label$\n')
    out = parselmouth.praat.run(script, capture_output=True)[1].splitlines()
    assert out == ["5", "hare run.PST.3SG"]       # blank, merged, blank, where.3SG, blank


def test_push_never_reaches_past_the_line_with_rounded_times(tmp_path):
    """Josh, 19 October: stored times are rounded (2.9261 for 2.926141…), and a push merged the
    empty segments either side of the line into it."""
    db, t, u, grid = _setup(tmp_path)
    a, b = 0.512345678, 1.487654321
    tgmod.write_example(grid, {"tx": [(a, b, "ʔəŋ kɒ"), (2.0, 3.0, "ɛ ŋəə")],
                               "ft": [(a, b, "the hare ran"), (2.0, 3.0, "where is he?")],
                               "ge": [(a, 1.0, "hare"), (1.0, b, "run.PST"), (2.0, 3.0, "where.3SG")]}, 4.0)
    lines = tgmod.read_lines(grid, db.mapping_for(t))
    u.token.set("Morphemes", "hare run.PST")
    u.source = ClipSource(t.id, round(a, 4), round(b, 4), dict(lines[0].copied), tgmod.modified(grid))
    u.token.set("Morphemes", "hare.run")
    c = pull.check(db, u)
    assert c.status == pull.OK and c.line is None                  # not read: only rounded times known
    plan = pull.push_plan(db, c)
    assert [(ch.tier, ch.segments) for ch in plan] == [("ge", 2)]
    pull.push(db, t, [(c, plan)])
    from praatio import textgrid
    tg = textgrid.openTextgrid(str(grid), includeEmptyIntervals=True)
    ge = [tuple(e) for e in tg.getTier("ge").entries]
    assert ge[:3] == [(0.0, a, ""), (a, b, "hare.run"), (b, 2.0, "")]   # the empty neighbours untouched


def test_an_empty_segment_reaching_past_the_line_is_split_not_swallowed(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    tgmod.write_example(grid, {"tx": TX, "ft": FT, "ge": [(2.0, 3.0, "where.3SG")]}, 4.0)   # ge empty at 0.5–1.5
    lines = tgmod.read_lines(grid, db.mapping_for(t))
    u.source = ClipSource(t.id, 0.5, 1.5, dict(lines[0].copied), tgmod.modified(grid))
    u.token.set("Morphemes", "hare run.PST")
    c = pull.check(db, u)
    plan = pull.push_plan(db, c)
    assert [(ch.tier, ch.old, ch.segments) for ch in plan] == [("ge", "", 1)]
    pull.push(db, t, [(c, plan)])
    from praatio import textgrid
    tg = textgrid.openTextgrid(str(grid), includeEmptyIntervals=True)
    assert [tuple(e) for e in tg.getTier("ge").entries][:3] == [(0.0, 0.5, ""), (0.5, 1.5, "hare run.PST"), (1.5, 2.0, "")]


def test_after_restoring_a_backup_push_can_write_the_utterance_again(tmp_path):
    db, t, u, grid = _setup(tmp_path)
    original = grid.read_bytes()
    u.token.set("Phonetic", "ʔə̀ŋ kɒ̄")
    c = pull.check(db, u)
    u.__dict__.update(pull.push(db, t, [(c, pull.push_plan(db, c))])[u.id].__dict__)
    grid.write_bytes(original)                                     # the backup put back by hand
    os.utime(grid, (time.time() + 900, time.time() + 900))
    c = pull.check(db, u)
    assert c.status == pull.CHANGED and not c.edited and c.pushable    # either direction can be chosen
    assert [(ch.tier, ch.old, ch.new) for ch in pull.push_plan(db, c)] == [("tx", "ʔəŋ kɒ", "ʔə̀ŋ kɒ̄")]
