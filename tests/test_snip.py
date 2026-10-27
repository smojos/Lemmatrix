# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""✂ auto-snip, the test version (IDEAS.md idea 10, Josh, 27 October): synthetic takes of tone
bursts, hiss and background noise."""

import numpy as np

from lemmatrix import snip

R = 44100
rng = np.random.default_rng(7)


def noise(sec, db=-60):
    return rng.normal(0, 10 ** (db / 20), int(R * sec)).astype(np.float32)


def vowel(sec, db=-12):
    t = np.arange(int(R * sec)) / R
    return (sum(np.sin(2 * np.pi * f * t) / k for k, f in enumerate((150, 300, 450, 900), 1))
            * 10 ** (db / 20) / 2).astype(np.float32)


def fricative(sec, db=-35):
    """[s]-like: high-passed noise."""
    x = rng.normal(0, 1, int(R * sec))
    spec = np.fft.rfft(x)
    spec[np.fft.rfftfreq(len(x), 1 / R) < 4000] = 0
    y = np.fft.irfft(spec, len(x))
    return (y / np.sqrt((y ** 2).mean()) * 10 ** (db / 20)).astype(np.float32)


def take(*parts):
    """(kind, seconds) parts over one steady background."""
    sig = np.concatenate([p for p in parts])
    return sig + noise(len(sig) / R)


def test_ends_trimmed_with_a_longer_tail():
    x = take(np.zeros(R), vowel(0.5), np.zeros(R))
    y, rep = snip.snip(x, R)
    assert rep.changed and abs(rep.new_length - (0.1 + 0.5 + 0.25)) < 0.06
    assert rep.cut[0][1] == pytest_approx(0.9) and rep.cut[-1][0] == pytest_approx(1.75)


def pytest_approx(v, tol=0.05):
    class A:
        def __eq__(self, other):
            return abs(other - v) <= tol
    return A()


def test_a_long_gap_shortened_a_short_one_kept():
    x = take(np.zeros(int(R * 0.3)), vowel(0.4), np.zeros(int(R * 1.5)), vowel(0.4),
             np.zeros(int(R * 0.2)), vowel(0.4), np.zeros(int(R * 0.3)))
    y, rep = snip.snip(x, R)
    gaps = [(b - a) for (_, a), (b, _) in zip(rep.speech, rep.speech[1:])]
    assert len(rep.speech) == 2 or len(rep.speech) == 3
    inner = [c for c in rep.cut if 0.5 < c[0] < 2.5]
    assert len(inner) == 1 and abs((inner[0][1] - inner[0][0]) - 1.2) < 0.06   # 1.5 s → 0.3 s
    assert all(not (2.9 < c[0] < 3.3) for c in rep.cut)                       # the 0.2 s gap untouched
    assert gaps


def test_no_gaps_for_utterances():
    x = take(np.zeros(int(R * 0.3)), vowel(0.4), np.zeros(int(R * 1.5)), vowel(0.4), np.zeros(int(R * 0.3)))
    y, rep = snip.snip(x, R, gaps=False)
    assert all(not (0.8 < a < 2.0) for a, b in rep.cut)                       # only the ends


def test_a_quiet_final_fricative_kept():
    x = take(np.zeros(R), vowel(0.4), fricative(0.3, db=-38), np.zeros(R))
    y, rep = snip.snip(x, R)
    # the [s] ends at 1.7 s; the cut starts no earlier than its end plus the tail
    assert rep.cut[-1][0] >= 1.7 + 0.2


def test_a_closure_inside_a_word_kept():
    x = take(np.zeros(R), vowel(0.3), np.zeros(int(R * 0.12)), vowel(0.3), np.zeros(R))
    y, rep = snip.snip(x, R)
    assert len(rep.cut) == 2                                                  # the ends only


def test_a_click_in_a_gap_is_not_speech():
    click = np.zeros(int(R * 0.5), np.float32)
    click[R // 4] = 0.8
    x = take(np.zeros(int(R * 0.3)), vowel(0.4), np.zeros(R), click, np.zeros(R), vowel(0.4), np.zeros(int(R * 0.3)))
    y, rep = snip.snip(x, R)
    assert len(rep.speech) == 2


def test_a_noisy_take_left_alone():
    x = vowel(0.5, db=-45)
    x = np.concatenate([np.zeros(R, np.float32), x, np.zeros(R, np.float32)])
    x = x + noise(len(x) / R, db=-50)
    y, rep = snip.snip(x, R)
    assert rep.noisy and not rep.changed and y is x


def test_all_silence_unchanged():
    x = noise(2.0)
    y, rep = snip.snip(x, R)
    assert not rep.changed and y is x


def test_type_and_channels_kept():
    x = take(np.zeros(R), vowel(0.5), np.zeros(R))
    pcm = (x * 32767).astype(np.int16)
    y, rep = snip.snip(pcm, R)
    assert y.dtype == np.int16 and rep.changed
    st = np.stack([x, x], axis=1)
    y2, rep2 = snip.snip(st, R)
    assert y2.ndim == 2 and y2.shape[1] == 2 and len(y2) == len(y) or abs(len(y2) - len(y)) < 2
