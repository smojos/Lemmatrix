"""Play pitch notation as sound: an abstract rendering of the tune.

Three voices:
    buzz     a robotic buzz (a sawtooth) following the trace exactly
    hum      a human-like "mmm mmm mmm": a voice-like source through a nasal
             filter, with a little vibrato and drift
    whistle  a human-like whistle: a pure tone two and a half octaves up,
             with a little breath noise and vibrato

Timing follows the drawing: every short step lasts the same time, each colon
adds a step, syllables are separated by a short silence and a comma by a
longer one. Pitch levels are a fixed number of semitones apart, centred on the
middle of the display range.
"""

from __future__ import annotations

import numpy as np

from . import pitch as pitchmod

BUZZ, HUM, WHISTLE = "buzz", "hum", "whistle"
VOICES = {BUZZ: "Buzz", HUM: "Hum", WHISTLE: "Whistle"}

RATE = 44100
STEP = 0.17           # seconds per short step
GAP = 0.09            # silence between syllables
PAUSE = 0.32          # silence for a comma
BASE = {BUZZ: 140.0, HUM: 135.0, WHISTLE: 1150.0}     # Hz at the middle of the range


def _semitones_per_level(low: int, high: int) -> float:
    """Two semitones a level, but a wide range is squeezed into about an octave and a half."""
    return min(2.0, 18.0 / max(1, high - low))


def contour(text: str, low: int = 1, high: int = 5, rate: int = RATE):
    """[(semitone track or None for silence)]: one array per syllable, None for gaps."""
    per = _semitones_per_level(low, high)
    mid = (low + high) / 2
    out = []
    items = pitchmod.parse(text)
    first = True
    pending = 0.0
    for item in items:
        if item == pitchmod.PAUSE:
            pending = PAUSE if not first else 0.0
            continue
        if not first:
            out.append(int(rate * max(pending, GAP)))
        pending = 0.0
        first = False
        points = [(d - mid) * per for d in item.points]
        segs = []
        for a, b, step in zip(points, points[1:], item.steps):
            n = max(1, int(rate * STEP * step))
            segs.append(np.linspace(a, b, n, endpoint=False))
        track = np.concatenate(segs) if segs else np.full(int(rate * STEP), points[0])
        # round the corners a little (20 ms), as a voice would
        k = max(1, int(rate * 0.02))
        if len(track) > 2 * k:
            padded = np.concatenate([np.full(k, track[0]), track, np.full(k, track[-1])])
            track = np.convolve(padded, np.ones(k) / k, mode="same")[k:-k]
        out.append(track)
    return out


def _envelope(n: int, attack: float, release: float, rate: int) -> np.ndarray:
    env = np.ones(n)
    a, r = min(n // 2, int(rate * attack)), min(n // 2, int(rate * release))
    if a:
        env[:a] = np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    if r:
        env[-r:] = np.cos(np.linspace(0, np.pi / 2, r)) ** 2
    return env


def _resonance(f: np.ndarray, centre: float, bandwidth: float) -> np.ndarray:
    return 1.0 / np.sqrt(1.0 + ((f - centre) / (bandwidth / 2)) ** 2)


def _additive(freq: np.ndarray, amplitude, rate: int, limit: int = 60) -> np.ndarray:
    """Sum of harmonics of a changing f0; amplitude(k, harmonic frequencies) gives each one's level."""
    phase = 2 * np.pi * np.cumsum(freq) / rate
    out = np.zeros_like(freq)
    for k in range(1, limit + 1):
        fk = freq * k
        if fk.min() > rate * 0.45:
            break
        amp = amplitude(k, fk) * (fk < rate * 0.45)
        out += amp * np.sin(k * phase)
    return out


def _syllable(semis: np.ndarray, voice: str, rate: int, rng: np.random.Generator) -> np.ndarray:
    n = len(semis)
    t = np.arange(n) / rate
    if voice == BUZZ:
        freq = BASE[BUZZ] * 2 ** (semis / 12)
        sig = _additive(freq, lambda k, fk: 1.0 / k, rate)
        return sig * _envelope(n, 0.008, 0.012, rate)
    if voice == WHISTLE:
        vib = 0.28 * np.sin(2 * np.pi * 6.0 * t + rng.uniform(0, 6.3))
        freq = BASE[WHISTLE] * 2 ** ((semis + vib) / 12)
        phase = 2 * np.pi * np.cumsum(freq) / rate
        tone = np.sin(phase) + 0.04 * np.sin(2 * phase)
        # breath: slow noise riding on the tone gives a soft band around it
        noise = rng.standard_normal(n)
        k = max(1, int(rate * 0.0015))
        noise = np.convolve(noise, np.ones(k) / k, mode="same")
        breath = 0.35 * noise * np.sin(phase + 0.7) + 0.015 * rng.standard_normal(n)
        swell = 0.85 + 0.15 * np.sin(np.pi * np.linspace(0, 1, n))
        return (tone + breath) * swell * _envelope(n, 0.035, 0.06, rate)
    # hum: a soft voice source through a nasal filter ("mmm")
    drift = np.cumsum(rng.standard_normal(n)) / np.sqrt(rate) * 0.6
    drift -= np.linspace(drift[0], drift[-1], n)
    vib = 0.22 * np.sin(2 * np.pi * 5.3 * t + rng.uniform(0, 6.3))
    freq = BASE[HUM] * 2 ** ((semis + vib + drift) / 12)

    def level(k, fk):
        nasal = (_resonance(fk, 260, 140) + 0.12 * _resonance(fk, 1100, 300)
                 + 0.05 * _resonance(fk, 2300, 400))
        return (nasal + (0.9 if k == 1 else 0.0)) / k ** 0.7     # hums have a strong fundamental
    sig = _additive(freq, level, rate, limit=40)
    shimmer = 1 + 0.04 * np.sin(2 * np.pi * 3.1 * t + rng.uniform(0, 6.3))
    return sig * shimmer * _envelope(n, 0.05, 0.09, rate)


def synthesise(text: str, low: int = 1, high: int = 5, voice: str = HUM,
               rate: int = RATE, seed: int | None = None) -> np.ndarray:
    """Mono float samples (-1..1) of the pitch notation in the chosen voice."""
    if voice not in VOICES:
        voice = HUM
    rng = np.random.default_rng(seed)
    parts = [np.zeros(int(rate * 0.04))]          # a moment of silence first
    for piece in contour(text, low, high, rate):
        if isinstance(piece, int):
            parts.append(np.zeros(piece))
        else:
            parts.append(_syllable(piece, voice, rate, rng))
    parts.append(np.zeros(int(rate * 0.06)))
    out = np.concatenate(parts)
    peak = np.abs(out).max()
    if peak > 0:
        out = out / peak * 0.6
    return out.astype(np.float32)
