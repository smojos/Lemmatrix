# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Gaps in a recording: sound lost while it was made (IDEAS.md idea 88).

A phone's browser records in chunks of 128 samples (the audio worklet's render quantum). When the
phone is too busy, a chunk can be lost and the sound on either side is butted together: a pop in a
vowel, a click in the quiet (Josh, 27 October: an ɛλicit recording with pops at 4.29 and 8.37 s).
Such a break is found as a spike in the linear-prediction error (each sample predicted from the
16 before it), many times the error around it, falling on a chunk boundary.

- ``find(x, sr, offset=0)``: a take as the page made it, chunks starting at sample 0.
- ``find(x, sr, offset=None)``: a recording that may have been trimmed since (✂ auto-snip, Praat):
  the boundary is unknown, so the spikes must share one position within the chunk (two or more:
  clean speech has the odd spike this strong too, a release or a click, in 10 of 274 clean files,
  but never two on one grid).
- ``find(x, sr, offset="auto")``: the boundary as made first (a recording untouched since), else
  unknown. A single gap in a trimmed recording can't be told from a click, so it isn't reported.

Only gaps where there is sound (louder than −40 dBFS) are reported: a lost chunk in the quiet is
inaudible. Nor next to a clipped sample: clipping makes corners as sharp, and is reported as clipping. Calibrated 27 October on that recording (its four audible gaps, at 2.37, 4.29, 8.37 and 11.13 s, all score above 50) and on
153 clean recordings, 589 s, none of which scores 30 in sound.

The same test runs in the web page (``docs/elicit/elicit.js``, ``gapsIn``), on each take.
"""

from __future__ import annotations

import numpy as np

QUANTUM = 128
THRESHOLD = 30.0          # the spike against the error around it
LOUD_DB = -40.0           # only where there is sound
ORDER = 16
CLIP = 0.999              # full scale (lemmatrix/ui/levelmeter.py): a clipped take is told so instead


def residual(x: np.ndarray, sr: int) -> np.ndarray:
    """The prediction error of every sample, the predictor fitted per 20 ms (Levinson-Durbin)."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    out = np.zeros(n)
    block = max(256, int(0.02 * sr))
    for s0 in range(0, n, block):
        lo, hi = max(0, s0 - block), min(n, s0 + 2 * block)
        seg = x[lo:hi] * np.hanning(hi - lo)
        r = np.array([np.dot(seg[:len(seg) - k], seg[k:]) for k in range(ORDER + 1)])
        if r[0] <= 1e-12:
            continue
        a = np.zeros(ORDER + 1)
        a[0] = 1.0
        e = r[0] * (1 + 1e-9)
        for i in range(1, ORDER + 1):
            k = -(r[i] + np.dot(a[1:i], r[i - 1:0:-1])) / e
            a[1:i] = a[1:i] + k * a[i - 1:0:-1]
            a[i] = k
            e *= (1 - k * k)
            if e <= 0:
                break
        idx = np.arange(max(s0, ORDER), min(n, s0 + block))
        if len(idx):
            frame = np.stack([x[idx - j] for j in range(1, ORDER + 1)], 1)
            out[idx] = x[idx] + frame @ a[1:]
    return out


def _scores(x: np.ndarray, sr: int):
    e = np.abs(residual(x, sr))
    w = max(8, int(0.005 * sr))
    kernel = np.ones(2 * w + 1)
    kernel[w - 2:w + 3] = 0                       # the error around, not the spike itself
    around = np.convolve(e, kernel, "same") / kernel.sum()
    peak = np.maximum(e, np.concatenate([e[1:], [0.0]]))       # the spike or the sample after
    score = peak / (around + 1e-6)
    level = np.convolve(np.asarray(x, dtype=np.float64) ** 2, np.ones(2 * w) / (2 * w), "same")
    loud = 10 * np.log10(level + 1e-12) > LOUD_DB
    return score, loud


def find(x, sr: int, offset: int | str | None = 0) -> list[float]:
    """The audible gaps' times in seconds (see the module's note)."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        x = x[:, 0]
    if len(x) < 4 * QUANTUM:
        return []
    score, loud = _scores(x, sr)
    hits = np.where((score >= THRESHOLD) & loud)[0]
    hits = hits[(hits >= QUANTUM) & (hits < len(x) - QUANTUM)]
    w = max(8, int(0.005 * sr))                   # a clipped waveform's corners aren't lost sound
    hits = np.array([h for h in hits if np.abs(x[max(0, h - w):h + w]).max() < CLIP], dtype=int)
    if offset == "auto":
        keep = hits[hits % QUANTUM == 0]
        if not len(keep):
            return find(x, sr, None) if len(hits) >= 2 else []
    elif offset is not None:
        keep = hits[hits % QUANTUM == offset % QUANTUM]
    else:
        if len(hits) < 2:
            return []
        residues, counts = np.unique(hits % QUANTUM, return_counts=True)
        best = residues[np.argmax(counts)]
        if counts.max() < 2:
            return []
        keep = hits[hits % QUANTUM == best]
    times, last = [], -1
    for h in keep:                                # one per gap (the spike and the sample after)
        if last < 0 or h - last > 2:
            times.append(round(float(h) / sr, 3))
        last = h
    return times


def find_in_file(path, offset: int | str | None = "auto") -> list[float]:
    import soundfile as sf
    x, sr = sf.read(str(path), dtype="float64", always_2d=True)
    return find(x[:, 0], sr, offset)
