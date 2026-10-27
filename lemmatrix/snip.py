# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""✂ auto-snip (IDEAS.md idea 10, Josh, 27 October): *trim silence at the ends of recordings; for
tokens, normalize silence intervals between repetitions*. No Qt here: `snip(samples, rate, gaps)`
gives back the take, cut, and a report of what was cut. **Test version**: the margins are to be set
from Josh's own recordings (`tools/snip_dryrun.py`) before it is switched on in the program.

**Protecting quiet data at the edges** (Josh: "How can we protect quiet data at the end of a word or
utterance?"):
1. Silence is judged against the take's own **background** (its quietest tenth), never its peak.
2. **Hiss counts as sound:** the 2–10 kHz band is measured on its own too, so a final [s], [f] or
   [h] is sound even when its overall loudness is low. Hum below 100 Hz is left out of the overall
   loudness, so mains or traffic rumble isn't taken for speech.
3. A stretch of sound is **speech** only when it reaches well above the background somewhere
   (a click or a cough in a gap doesn't count); its quiet edges, close to it, belong to it.
4. **Longer tail than lead-in:** 100 ms kept before the first sound, 250 ms after the last.
5. **A noisy take isn't trimmed** (speech too close to the background to find its edges).
6. Gaps only ever **shorten** (over 0.6 s → 0.3 s: 0.2 s after the sound, 0.1 s before the next);
   nothing is ever lengthened, and a short gap (a closure, a breath) is never touched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

FRAME = 0.010            # s, the unit everything is measured in
QUIET = 10.0             # dB above the background: sound, overall…
QUIET_HISS = 8.0         # …or in the hiss band (steadier in silence, so a lower step)
SMOOTH = 0.050           # s: the levels are averaged over this, so noise's flicker isn't sound
SPEECH = 20.0            # dB above the background somewhere: a stretch is speech, not a noise
SPEECH_MIN = 0.030       # s of frames that loud, so a click isn't speech
JOIN = 0.150             # s: quiet sound this close to speech belongs to it
NOISY = 25.0             # dB: peak less than this above the background → not trimmed
LEAD, TAIL = 0.100, 0.250
GAP_OVER = 0.600         # s: a gap longer than this is shortened…
GAP_AFTER, GAP_BEFORE = 0.200, 0.100   # …to this much after one stretch and before the next
FADE = 0.005             # s crossfade at each join, so there's no click
HUM = 100.0              # Hz: left out of the overall loudness
HISS = (2000.0, 10000.0)  # Hz


@dataclass
class Report:
    changed: bool = False
    noisy: bool = False
    background_db: float = 0.0
    peak_db: float = 0.0
    speech: list = field(default_factory=list)        # (start, end) s of each stretch of speech
    cut: list = field(default_factory=list)           # (start, end) s of each piece taken out
    length: float = 0.0
    new_length: float = 0.0

    def describe(self) -> str:
        if self.noisy:
            return (f"not trimmed: too noisy (speech only {self.peak_db - self.background_db:.0f} dB "
                    f"above the background)")
        if not self.changed:
            return "nothing to trim"
        return (f"{self.length:.2f} s → {self.new_length:.2f} s; cut "
                + ", ".join(f"{a:.2f}–{b:.2f}" for a, b in self.cut))


def _mono(samples) -> np.ndarray:
    a = np.asarray(samples)
    if a.dtype.kind in "iu":
        a = a.astype(np.float32) / float(np.iinfo(a.dtype).max)
    a = a.astype(np.float32)
    return a if a.ndim == 1 else a.mean(axis=1)


def _levels(x: np.ndarray, rate: int):
    hop = max(1, int(rate * FRAME))
    n = len(x) // hop
    fr = x[:n * hop].reshape(n, hop)
    spec = np.abs(np.fft.rfft(fr * np.hanning(hop), axis=1)) ** 2
    fq = np.fft.rfftfreq(hop, 1.0 / rate)
    k = max(1, int(round(SMOOTH / FRAME)))
    kernel = np.ones(k) / k

    def level(power):
        return 10 * np.log10(np.convolve(power, kernel, mode="same") + 1e-20)

    overall = level(spec[:, fq >= HUM].sum(axis=1))
    band = (fq >= HISS[0]) & (fq <= min(HISS[1], rate / 2))
    hiss = level(spec[:, band].sum(axis=1)) if band.any() else np.full(n, -200.0)
    return hop, overall, hiss


def _runs(mask: np.ndarray):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            out.append([i, j])
            i = j
        else:
            i += 1
    return out


def find_speech(samples, rate: int):
    """The stretches of speech (start, end frames), the frame length, and the levels for the report."""
    x = _mono(samples)
    hop, overall, hiss = _levels(x, rate)
    if len(overall) == 0:
        return [], hop, 0.0, 0.0
    bg, hbg = np.percentile(overall, 10), np.percentile(hiss, 10)
    sound = (overall > bg + QUIET) | (hiss > hbg + QUIET_HISS)
    loud = overall > bg + SPEECH
    join = int(round(JOIN / FRAME))
    stretches = []
    for a, b in _runs(sound):
        if stretches and a - stretches[-1][1] <= join:
            stretches[-1][1] = b
        else:
            stretches.append([a, b])
    need = int(round(SPEECH_MIN / FRAME))
    speech = [(a, b) for a, b in stretches if loud[a:b].sum() >= need]
    return speech, hop, float(bg), float(overall.max())


def snip(samples, rate: int, gaps: bool = True):
    """The take with its silent ends trimmed and (with `gaps`) long gaps shortened: (samples, Report).
    The samples come back in the same type and channels; unchanged when there's nothing to do."""
    a = np.asarray(samples)
    rep = Report(length=len(a) / rate if rate else 0.0)
    rep.new_length = rep.length
    if len(a) < rate * 0.2:
        return samples, rep
    speech, hop, bg, peak = find_speech(a, rate)
    rep.background_db, rep.peak_db = bg, peak
    rep.speech = [(s * hop / rate, e * hop / rate) for s, e in speech]
    if peak - bg < NOISY:
        rep.noisy = True
        return samples, rep
    if not speech:
        return samples, rep
    n = len(a)
    keep = []                                            # sample ranges to keep, in order
    start = max(0, speech[0][0] * hop - int(LEAD * rate))
    cur = start
    for (s1, e1), (s2, e2) in zip(speech, speech[1:]):
        gap = (s2 - e1) * hop / rate
        if gaps and gap > GAP_OVER:
            keep.append((cur, e1 * hop + int(GAP_AFTER * rate)))
            cur = s2 * hop - int(GAP_BEFORE * rate)
    end = min(n, speech[-1][1] * hop + int(TAIL * rate))
    keep.append((cur, end))
    cut, prev = [], 0
    for s, e in keep:
        if s > prev:
            cut.append((prev / rate, s / rate))
        prev = e
    if prev < n:
        cut.append((prev / rate, n / rate))
    cut = [(x, y) for x, y in cut if y - x > 0.001]
    if not cut:
        return samples, rep
    out = _join([a[s:e] for s, e in keep], int(FADE * rate))
    rep.changed, rep.cut = True, cut
    rep.new_length = len(out) / rate
    return out, rep


def _join(pieces, fade: int):
    """The pieces end to end, each join crossfaded over `fade` samples."""
    dtype = pieces[0].dtype
    acc = pieces[0].astype(np.float64)
    for p in pieces[1:]:
        p = p.astype(np.float64)
        f = min(fade, len(acc), len(p))
        if f > 0:
            ramp = np.linspace(0.0, 1.0, f)
            if acc.ndim > 1:
                ramp = ramp[:, None]
            mixed = acc[-f:] * (1 - ramp) + p[:f] * ramp
            acc = np.concatenate([acc[:-f], mixed, p[f:]])
        else:
            acc = np.concatenate([acc, p])
    if dtype.kind in "iu":
        info = np.iinfo(dtype)
        acc = np.clip(np.round(acc), info.min, info.max)
    return acc.astype(dtype)
