# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The segment scratchpad's soundfiles (IDEAS.md idea 46): Lemmatrix's own IPA soundfiles, the
database's Soundfiles/Segments, names, the order of voices, renames and the Ethical archive."""

import csv
import hashlib

import numpy as np

from lemmatrix import audio, layout, segments as sg
from lemmatrix.model import Database, Person


def _db(tmp_path, language="LXX", variety="VXX"):
    db = Database()
    db.path = str(tmp_path / "LXX-VXX_Test.xml")
    db.metadata.language_code, db.metadata.variety_code = language, variety
    db.metadata.participants = [Person("SP1", "Speaker one", audio_sharing=True),
                                Person("SP2", "Speaker two")]
    db.metadata.researchers = [Person("RS1", "Researcher one")]
    return db


def _wav(path):
    audio.write_wav(path, np.zeros(441), 44100)
    return path


def test_every_native_soundfile_is_there_unchanged():
    rows = list(csv.DictReader(open(sg.NATIVE_FOLDER / "credits.tsv", encoding="utf-8"), delimiter="\t"))
    assert len(rows) == 126
    for r in rows:
        data = (sg.NATIVE_FOLDER / r["soundfile"]).read_bytes()
        assert hashlib.sha1(data).hexdigest() == r["sha1"], r["soundfile"]
    assert (sg.NATIVE_FOLDER / "LICENSE-IPA.md").exists() and (sg.NATIVE_FOLDER / "CREDITS.md").exists()
    assert len(sg.native_index()) == 126


def test_native_lookup_and_credit():
    b = sg.native("β")
    assert b.native and b.path.name == "Voiced_bilabial_fricative.ogg"
    assert b.credit == "Peter Isotalo · CC BY-SA 3.0 · Wikimedia Commons"
    assert sg.native(" ɛ ").credit.startswith("Terfili")               # trimmed; the actual recorder
    assert sg.native("ts") is sg.native("t͡s") is not None            # tie bar or not: the same (Josh)
    assert sg.native("t͜s") is sg.native("t͡s")                        # the tie bar below too
    assert sg.native("ɡ") is not None and sg.native("g") is sg.native("ɡ")   # the ordinary g too (Josh, 25 October)
    assert sg.native("ɸʼ").credit.endswith("CC0 · Wikimedia Commons")


def test_native_soundfiles_play():
    data, rate = audio.read_any(sg.native("a").path)
    assert rate == 44100 and data.ndim == 1 and len(data) > 1000


def test_names_and_parsing(tmp_path):
    db = _db(tmp_path)
    assert sg.filename(db, "ʌ", "SP1") == "LXX-VXX-SP1_ʌ.wav"
    assert sg.filename(db, "ʌ") == "LXX-VXX_ʌ.wav"
    assert sg.filename(db, " a_b ") == "LXX-VXX_a_b.wav"
    assert sg.parse(db, "LXX-VXX-SP1_ʌ.wav") == ("ʌ", "SP1")
    assert sg.parse(db, "LXX-VXX-RS1_ʌ.wav") == ("ʌ", "RS1")
    assert sg.parse(db, "LXX-VXX_a_b.wav") == ("a_b", "")
    assert sg.parse(db, "OLD-SP2_pu.wav") == ("pu", "SP2")            # an older language code
    assert sg.parse(db, "ʌ.wav") == ("ʌ", "")                         # dropped in by hand
    assert sg.parse(db, "notes.txt") is None
    no_variety = _db(tmp_path, variety="")
    assert sg.filename(no_variety, "ʌ", "SP1") == "LXX-SP1_ʌ.wav"
    assert sg.parse(no_variety, "LXX-SP1_ʌ.wav") == ("ʌ", "SP1")
    bare = _db(tmp_path, language="", variety="")
    assert sg.filename(bare, "ʌ", "SP1") == "SP1_ʌ.wav" and sg.filename(bare, "ʌ") == "ʌ.wav"
    assert sg.parse(bare, "SP1_ʌ.wav") == ("ʌ", "SP1") and sg.parse(bare, "a_b.wav") == ("a_b", "")


def test_tie_bars_call_the_same_recording(tmp_path):
    db = _db(tmp_path)
    seg = layout.segments_folder(db.path)
    seg.mkdir(parents=True)
    _wav(seg / "LXX-VXX-SP1_t͡ʃa.wav")
    assert [v.speaker for v in sg.voices(db, "tʃa")] == ["SP1"]
    assert sg.filename(db, "tʃa", "SP1") == "LXX-VXX-SP1_tʃa.wav"       # names keep what was typed


def test_playback_padding_leaves_the_sound_as_it_is():
    data = np.ones(100, dtype=np.float32)
    out = audio.padded(data, 1000)
    assert len(out) == 100 + int(1000 * audio.LEAD_IN) + int(1000 * audio.TAIL)
    assert not out[:int(1000 * audio.LEAD_IN)].any() and (out[int(1000 * audio.LEAD_IN):][:100] == 1).all()


def test_forbidden_characters():
    assert sg.problem("ǀ") == "" and sg.problem("a|b") == "|" and sg.problem("a:") == ":"


def test_the_order_of_voices(tmp_path):
    db = _db(tmp_path)
    seg = layout.segments_folder(db.path)
    seg.mkdir(parents=True)
    for name in ("LXX-VXX-RS1_ʌ.wav", "LXX-VXX-SP2_ʌ.wav", "LXX-VXX_ʌ.wav", "LXX-VXX-SP1_ʌ.wav",
                 "LXX-VXX-SP1_pu.wav"):
        _wav(seg / name)
    order = [(v.speaker, v.native) for v in sg.voices(db, "ʌ", "SP2")]
    assert order == [("SP2", False), ("", False), ("SP1", False), ("RS1", False), ("", True)]
    assert [v.speaker for v in sg.voices(db, "ʌ")][:3] == ["", "SP1", "SP2"]
    assert sg.best(db, "pu").speaker == "SP1"
    assert sg.voices(db, "bu") == [] and sg.best(db, "") is None
    (seg / "LXX-VXX-SP1_ʌ.wav").unlink()
    (seg / "LXX-VXX-SP2_ʌ.wav").unlink()
    (seg / "LXX-VXX-RS1_ʌ.wav").unlink()
    (seg / "LXX-VXX_ʌ.wav").unlink()
    assert sg.best(db, "ʌ").native                                    # deleted: Lemmatrix's own again


def test_speakers_renamed_follow(tmp_path):
    db = _db(tmp_path)
    seg = layout.segments_folder(db.path)
    seg.mkdir(parents=True)
    _wav(seg / "LXX-VXX-SP1_ʌ.wav")
    _wav(seg / "LXX-VXX-SP2_ʌ.wav")
    db.metadata.participants[0].code = "SPA"
    done = sg.rename_speakers(db, {"SP1": "SPA"})
    assert done == [("LXX-VXX-SP1_ʌ.wav", "LXX-VXX-SPA_ʌ.wav")]
    assert (seg / "LXX-VXX-SPA_ʌ.wav").exists() and (seg / "LXX-VXX-SP2_ʌ.wav").exists()


def test_ethical_archive_takes_only_shared_participants(tmp_path):
    db = _db(tmp_path)
    seg = layout.segments_folder(db.path)
    seg.mkdir(parents=True)
    for name in ("LXX-VXX-SP1_ʌ.wav", "LXX-VXX-SP2_ʌ.wav", "LXX-VXX-RS1_ʌ.wav", "LXX-VXX_ʌ.wav"):
        _wav(seg / name)
    out = tmp_path / "archive" / "Soundfiles" / "Segments"
    assert sg.copy_shared(db, out) == (1, 3)
    assert [p.name for p in out.iterdir()] == ["LXX-VXX-SP1_ʌ.wav"]


def test_an_ordinary_g_calls_the_same_as_the_ipa_g(tmp_path):
    from lemmatrix import segments
    assert segments.key("g") == segments.key("ɡ") == "ɡ"
    assert segments.key("ga") == segments.key("ɡa")
    assert segments.native("g").sequence == "ɡ"


def test_alternative_callers_call_the_ipa_symbols_soundfile():
    """Josh's list (25 October, lemmatrix/ipa/alternatives.tsv): the whole sequence only."""
    assert sg.called("sh") == "ʃ" and sg.native("ʃ") is not None
    assert sg.called("sha") == ""                              # only on its own
    for alt, ipa in (("b'", "ɓ"), ("!", "ǃ"), ("?", "ʔ"), ("ny", "ɲ"), ("gh", "ɣ"), ("tr'", "ʈʼ"),
                     ("ch", "t͡ʃ"), ("(.)", "ʘ"), ("G'", "ʛ"), ("J", "d͡ʒ"), ("X", "q")):
        assert sg.called(alt) == ipa, alt
        assert sg.native(ipa) is not None, ipa                 # every target is a built-in sound
    assert sg.called("rr") == ""                               # waiting: given for both ɻ and ɽ
    for alt in sg.callers():                                   # no alternative is itself a built-in
        assert sg.native(alt) is None or sg.key(sg.native(alt).sequence) == sg.key(sg.called(alt)), alt


def test_a_recording_of_the_sequence_as_typed_comes_before_the_alternative(tmp_path):
    db = _db(tmp_path)
    folder = layout.segments_folder(db.path)
    folder.mkdir(parents=True)
    _wav(folder / "LXX-VXX_th.wav")                                     # an aspirated t, say
    _wav(folder / "LXX-VXX_θ.wav")
    found = sg.voices(db, "th")
    assert [v.sequence for v in found] == ["th", "θ", "θ"] and found[-1].native
    assert [v.sequence for v in sg.voices(db, "θ")] == ["θ", "θ"]      # θ never finds the th recording
