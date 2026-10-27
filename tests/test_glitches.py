# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Gaps in a recording (IDEAS.md idea 88, 27 October): a chunk of 128 samples lost while a phone
recorded, the sound either side butted together. Calibrated on a real ɛλicit recording (not in the
repository: it is a speaker's voice) and on the sample's own recordings, which must stay clean."""

from pathlib import Path

import numpy as np
import soundfile as sf

from lemmatrix import glitches

ROOT = Path(__file__).resolve().parent.parent
SR = 48000


def _voice(seconds=3.0, f0=120.0, seed=1):
    """Something like a vowel: a buzz with formant-ish harmonics and a little breath noise."""
    t = np.arange(int(SR * seconds)) / SR
    x = sum(a * np.sin(2 * np.pi * f0 * k * t + k) for k, a in ((1, .3), (2, .2), (3, .15), (5, .08), (8, .05)))
    x = x * (0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * t))
    return x + np.random.default_rng(seed).normal(0, 0.002, len(t))


def _drop(x, chunk):
    """Chunk number `chunk` (of 128 samples) lost: what comes after moves up."""
    return np.concatenate([x[:chunk * 128], x[(chunk + 1) * 128:]])


def test_a_lost_chunk_is_found_where_it_was():
    x = _drop(_voice(), 400)
    assert glitches.find(x, SR, offset=0) == [round(400 * 128 / SR, 3)]


def test_clean_sound_has_no_gaps():
    assert glitches.find(_voice(seed=2), SR, offset=0) == []
    assert glitches.find(_voice(seed=3), SR, offset=None) == []


def test_a_trimmed_recording_still_shows_its_gaps():
    x = _drop(_drop(_voice(), 300), 700)
    trimmed = x[1000:]                                    # ✂ auto-snip or Praat took the start off
    assert glitches.find(trimmed, SR, offset=0) == []     # not on the boundaries any more
    found = glitches.find(trimmed, SR, offset=None)
    assert found == [round((300 * 128 - 1000) / SR, 3), round((700 * 128 - 1000) / SR, 3)]


def test_auto_tries_the_boundary_as_recorded_first():
    x = _drop(_voice(), 400)
    assert glitches.find(x, SR, offset="auto") == [round(400 * 128 / SR, 3)]
    assert glitches.find(x[1000:], SR, offset="auto") == []             # one gap, trimmed: a click?
    two = _drop(x, 600)[1000:]
    assert len(glitches.find(two, SR, offset="auto")) == 2


def test_a_click_near_the_start_doesnt_crash():
    """The review of 27 October: a spike in the first 5 ms took a slice before the start (empty)."""
    x = _voice()
    x[130] += 0.8                                         # a click at 2.7 ms
    glitches.find(x, SR, offset=0)
    glitches.find(x, SR, offset="auto")


def test_a_gap_in_the_quiet_is_not_reported():
    x = _voice() * 0.001                                  # below -40 dBFS: inaudible either way
    assert glitches.find(_drop(x, 400), SR, offset=0) == []


def test_the_sample_recordings_are_clean():
    """Josh's own recordings of the sample (44.1 kHz, not made in a browser): no false alarms."""
    files = sorted((ROOT / "samples" / "Soundfiles" / "Tokens").glob("*.wav"))[:60]
    assert files
    for f in files:
        assert glitches.find_in_file(f, offset=0) == [], f.name
        assert glitches.find_in_file(f, offset=None) == [], f.name


def test_find_in_file_reads_a_wav(tmp_path):
    p = tmp_path / "take.wav"
    sf.write(p, _drop(_voice(), 250), SR, subtype="PCM_16")
    assert glitches.find_in_file(p, offset=0) == [round(250 * 128 / SR, 3)]
