# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Editing a text's lines in Lemmatrix (19 October): units, the buffer, writing back."""

import os

from lemmatrix import interlinear as il, lines as lmod, textgrid as tgmod
from lemmatrix.defaults import new_database
from lemmatrix.model import SPEAKER_FIELD, Text, TierRule


def test_units_follow_the_latex_glossing_rules():
    assert il.split_units("a {big dog} {} ran") == ["a", "{big dog}", "{}", "ran"]
    assert il.split_units("  hare   run.PST ") == ["hare", "run.PST"]
    assert [il.bare(u) for u in il.split_units("a {big dog} {}")] == ["a", "big dog", ""]
    assert il.as_unit("") == "{}" and il.as_unit("big dog") == "{big dog}" and il.as_unit("dog") == "dog"


def _setup(tmp_path, tiers=None):
    db = new_database()
    db.path = str(tmp_path / "Lex.xml")
    folder = tmp_path / "Soundfiles" / "Texts"
    folder.mkdir(parents=True)
    grid = folder / "t.TextGrid"
    tgmod.write_example(grid, tiers or {
        "tx": [(0.5, 1.5, "ʔəŋ kɒ"), (2.0, 3.0, "ɛ ŋəə")],
        "ge": [(0.5, 1.0, "hare"), (1.0, 1.5, "run.PST"), (2.0, 3.0, "where.3SG")],
        "ft": [(0.5, 1.5, "the hare ran"), (2.0, 3.0, "where is he?")]}, 4.0)
    t = Text(ref="T001", textgrid="t.TextGrid")
    db.texts.append(t)
    return db, t, lmod.Buffer(grid), grid


def _set(buf, db, t, n, key, value):
    ln = buf.lines(db, t)[n]
    edits = lmod.plan_edit(buf, db, t, ln, key, value)
    buf.apply(edits)
    return edits


def test_a_word_tier_keeps_its_segments_when_the_units_match(tmp_path):
    db, t, buf, grid = _setup(tmp_path)
    edits = _set(buf, db, t, 0, "Morphemes", "hare run.PFV")
    assert lmod.would_merge(edits) == []
    ge = [tuple(e) for e in buf.tg.getTier("ge").entries if e[2]]
    assert ge[:2] == [(0.5, 1.0, "hare"), (1.0, 1.5, "run.PFV")]
    assert buf.lines(db, t)[0].values["Morphemes"] == "hare run.PFV"


def test_an_empty_unit_and_a_braced_unit(tmp_path):
    db, t, buf, grid = _setup(tmp_path)
    _set(buf, db, t, 0, "Morphemes", "{} {run fast}")
    ge = [tuple(e) for e in buf.tg.getTier("ge").entries]
    assert (0.5, 1.0, "") in ge and (1.0, 1.5, "run fast") in ge
    assert buf.lines(db, t)[0].values["Morphemes"] == "{} {run fast}"       # read back the same


def test_other_unit_counts_merge_within_the_line_only(tmp_path):
    db, t, buf, grid = _setup(tmp_path)
    edits = _set(buf, db, t, 0, "Morphemes", "hare run PST")
    assert lmod.would_merge(edits) == [("ge", 2)]
    ge = [tuple(e) for e in buf.tg.getTier("ge").entries]
    assert (0.5, 1.5, "hare run PST") in ge and (0.0, 0.5, "") in ge and (1.5, 2.0, "") in ge


def test_a_single_segment_field_and_undo(tmp_path):
    db, t, buf, grid = _setup(tmp_path)
    edits = _set(buf, db, t, 1, "Translation:en", "where did he go?")
    assert buf.lines(db, t)[1].values["Translation:en"] == "where did he go?"
    buf.apply(edits, undo=True)
    assert buf.lines(db, t)[1].values["Translation:en"] == "where is he?"


def test_a_field_without_a_tier_gets_one(tmp_path):
    db, t, buf, grid = _setup(tmp_path)
    edits = _set(buf, db, t, 0, "Phonemic", "ʔəŋ kɒ")
    assert edits[0].created and edits[0].tier == "Phonemic"
    assert db.mapping_for(t).rule("Phonemic").field == "Phonemic"
    assert buf.lines(db, t)[0].values["Phonemic"] == "ʔəŋ kɒ" and "Phonemic" not in buf.lines(db, t)[1].values
    buf.apply(edits, undo=True)
    assert "Phonemic" not in buf.tg.tierNames


def test_the_main_tier_cant_be_emptied(tmp_path):
    db, t, buf, grid = _setup(tmp_path)
    ln = buf.lines(db, t)[0]
    try:
        lmod.plan_edit(buf, db, t, ln, "Phonetic", "")
        assert False, "should refuse"
    except lmod.LineEditError as exc:
        assert "placeholder" in str(exc)


def test_empty_segments_past_the_line_are_split_not_swallowed(tmp_path):
    db, t, buf, grid = _setup(tmp_path, {"tx": [(0.5, 1.5, "ʔəŋ kɒ")], "ft": [(2.0, 3.0, "x")]})
    _set(buf, db, t, 0, "Translation:en", "the hare ran")
    ft = [tuple(e) for e in buf.tg.getTier("ft").entries]
    assert (0.5, 1.5, "the hare ran") in ft and (0.0, 0.5, "") in ft and (1.5, 2.0, "") in ft


def test_writing_backs_up_and_praat_reads_it(tmp_path):
    db, t, buf, grid = _setup(tmp_path)
    _set(buf, db, t, 0, "Morphemes", "hare run.PFV")
    assert buf.changed and not buf.disk_changed()
    buf.write(db)
    assert not buf.changed and not buf.disk_changed()
    assert len(list((tmp_path / "Backups").iterdir())) == 1
    assert tgmod.read_lines(grid, db.mapping_for(t))[0].values["Morphemes"] == "hare run.PFV"
    os.utime(grid, (1, 1))
    assert buf.disk_changed()
    try:
        import parselmouth
    except ImportError:
        return
    out = parselmouth.praat.run(f'Read from file: "{grid}"\nn = Get number of intervals: 2\nappendInfoLine: n\n',
                                capture_output=True)[1].strip()
    assert out.isdigit()


def test_a_speaker_tier_gives_each_line_its_speaker(tmp_path):
    db, t, buf, grid = _setup(tmp_path, {"tx": [(0.5, 1.5, "a"), (2.0, 3.0, "b")],
                                         "who": [(0.5, 1.5, "SP1"), (2.0, 3.0, "SP2")]})
    db.settings.tier_mapping.rules.append(TierRule("who", SPEAKER_FIELD))
    lines = buf.lines(db, t)
    assert [ln.speaker for ln in lines] == ["SP1", "SP2"] and all("who" not in ln.copied for ln in lines)


def test_clipped_utterances_follow_their_line(tmp_path):
    from lemmatrix.model import ClipSource
    from lemmatrix import pull
    db, t, buf, grid = _setup(tmp_path)
    before = buf.lines(db, t)
    u = db.new_utterance("W001", "hare ran", "", "")
    u.token.set("Morphemes", before[0].values["Morphemes"])
    u.token.set("Phonetic", before[0].values["Phonetic"])
    u.token.set("Translation", before[0].values["Translation:en"], "en", True)
    u.source = ClipSource(t.id, round(0.5, 4), 1.5, dict(before[0].copied), tgmod.modified(grid))
    other = db.new_utterance("W002", "", "", "")
    other.source = ClipSource(t.id, 2.0, 3.0, dict(before[1].copied), tgmod.modified(grid))
    db.utterances += [u, other]
    edits = lmod.plan_edit(buf, db, t, before[0], "Morphemes", "hare run.PFV")
    buf.apply(edits)
    pairs = lmod.follow_clips(db, t, before, buf.lines(db, t), before[0], "Morphemes", edits)
    assert [p[0] for p in pairs] == [u]
    after = pairs[0][1]
    assert after.token.get("Morphemes") == "hare run.PFV" and after.source.copied["ge"] == "hare run.PFV"
    u.__dict__.update(after.__dict__)
    c = pull.check(db, u, {t.id: buf})                       # unsaved: compared with the edit, not the file
    assert c.status == pull.OK and not c.edited


def test_a_stretch_with_no_main_tier_text_is_a_flagged_line_until_it_gets_some(tmp_path):
    """21 October (Josh: much easier on import): where only other tiers have text, a line too."""
    db, t, buf, grid = _setup(tmp_path, {
        "tx": [(0.5, 1.5, "ʔəŋ kɒ")],
        "ge": [(0.5, 1.5, "hare run.PST"), (2.0, 2.6, "where.3SG")],
        "ft": [(0.5, 1.5, "the hare ran"), (2.2, 3.0, "where is he?")]})
    lines = buf.lines(db, t)
    assert [ln.missing_main for ln in lines] == [False, True]
    orphan = lines[1]
    assert (orphan.start, orphan.end) == (2.0, 3.0)              # the two tiers' stretches together
    assert orphan.values["Translation:en"] == "where is he?" and "Phonetic" not in orphan.values
    _set(buf, db, t, 1, "Phonetic", "ɛ ŋəə")                     # typing the main field makes it real
    lines = buf.lines(db, t)
    assert [ln.missing_main for ln in lines] == [False, False] and lines[1].values["Phonetic"] == "ɛ ŋəə"
