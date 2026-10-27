// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
//
// ɛλicit: what is done with a take after Stop (IDEAS.md idea 88), in a background worker when the
// browser allows it, so the phone stays free for the speaker's next take; otherwise on the page.
//
// - gapsIn(pcm, rate): sound lost while recording. The browser records in chunks of 128 samples;
//   when the phone is too busy one can be lost and the sound either side is butted together (a pop
//   in a vowel). Found as a spike in the prediction error (each sample predicted from the 16 before
//   it) at least 30 times the error around it, on a chunk boundary, where there is sound (louder than
//   -40 dBFS), and not next to a clipped sample (clipping makes corners as sharp: it is told as
//   clipping). The same test as Lemmatrix's lemmatrix/glitches.py, which explains the calibration.
// - levelOf(pcm): "clipped" (3 or more samples at full scale), "quiet" (the peak under -30 dBFS) or
//   "", as Lemmatrix's own recording note says it (lemmatrix/ui/levelmeter.py). Nothing is changed:
//   the speaker is only told.
// - processTake(pcm, rate, flac): both, and the take encoded as FLAC when the request asks for it.

"use strict";

(function (global) {
  const QUANTUM = 128, THRESHOLD = 30, LOUD_DB = -40, ORDER = 16, CLIP = 0.999, QUIET_DB = -30;

  function residual(x, rate) {            // Float64Array -> the prediction error of every sample
    const n = x.length, out = new Float64Array(n);
    const block = Math.max(256, Math.floor(0.02 * rate));
    const r = new Float64Array(ORDER + 1), a = new Float64Array(ORDER + 1), prev = new Float64Array(ORDER + 1);
    for (let s0 = 0; s0 < n; s0 += block) {
      const lo = Math.max(0, s0 - block), hi = Math.min(n, s0 + 2 * block), m = hi - lo;
      if (m < 2) continue;
      const seg = new Float64Array(m);
      for (let i = 0; i < m; i++) seg[i] = x[lo + i] * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / (m - 1)));
      for (let k = 0; k <= ORDER; k++) {
        let s = 0;
        for (let i = 0; i + k < m; i++) s += seg[i] * seg[i + k];
        r[k] = s;
      }
      if (r[0] <= 1e-12) continue;
      a.fill(0); a[0] = 1;
      let e = r[0] * (1 + 1e-9);
      for (let i = 1; i <= ORDER; i++) {             // Levinson-Durbin
        let acc = r[i];
        for (let j = 1; j < i; j++) acc += a[j] * r[i - j];
        const k = -acc / e;
        prev.set(a);
        for (let j = 1; j < i; j++) a[j] = prev[j] + k * prev[i - j];
        a[i] = k;
        e *= 1 - k * k;
        if (e <= 0) break;
      }
      const end = Math.min(n, s0 + block);
      for (let i = Math.max(s0, ORDER); i < end; i++) {
        let p = x[i];
        for (let j = 1; j <= ORDER; j++) p += a[j] * x[i - j];
        out[i] = p;
      }
    }
    return out;
  }

  function gapsIn(pcm, rate) {            // Int16Array -> the audible gaps' times in seconds
    const n = pcm.length;
    if (n < 4 * QUANTUM) return [];
    const x = new Float64Array(n);
    for (let i = 0; i < n; i++) x[i] = pcm[i] / 32768;
    const e = residual(x, rate);
    for (let i = 0; i < n; i++) e[i] = Math.abs(e[i]);
    const w = Math.max(8, Math.floor(0.005 * rate));
    const sumE = new Float64Array(n + 1), sumP = new Float64Array(n + 1);
    for (let i = 0; i < n; i++) { sumE[i + 1] = sumE[i] + e[i]; sumP[i + 1] = sumP[i] + x[i] * x[i]; }
    const range = (s, from, to) => s[Math.min(n, Math.max(0, to))] - s[Math.min(n, Math.max(0, from))];
    const kernel = 2 * w + 1 - 5;
    const out = [];
    let last = -10;
    for (let i = QUANTUM; i < n - QUANTUM; i += QUANTUM) {        // each chunk boundary
      const around = (range(sumE, i - w, i + w + 1) - range(sumE, i - 2, i + 3)) / kernel;
      const peak = Math.max(e[i], e[i + 1]);                      // the spike, or the sample after
      if (peak / (around + 1e-6) < THRESHOLD) continue;
      const power = range(sumP, i - w, i + w) / (2 * w);
      if (10 * Math.log10(power + 1e-12) <= LOUD_DB) continue;
      let full = false;                           // a clipped waveform's corners aren't lost sound
      for (let j = Math.max(0, i - w); j < Math.min(n, i + w); j++) if (Math.abs(x[j]) >= CLIP) { full = true; break; }
      if (full) continue;
      if (i - last > 2) out.push(Math.round(i / rate * 1000) / 1000);
      last = i;
    }
    return out;
  }

  function levelOf(pcm) {                 // {verdict: "clipped" | "quiet" | "", db: the peak in dBFS}
    let peak = 0, full = 0;
    const lim = CLIP * 32768;
    for (let i = 0; i < pcm.length; i++) {
      const v = Math.abs(pcm[i]);
      if (v > peak) peak = v;
      if (v >= lim) full++;                       // as levelmeter.py: |x| >= 0.999
    }
    const db = peak ? 20 * Math.log10(peak / 32768) : -120;
    const verdict = full >= 3 ? "clipped" : db < QUIET_DB ? "quiet" : "";
    return { verdict, db: Math.round(db * 10) / 10 };
  }

  function processTake(pcm, rate, flac) {
    const out = { gaps: gapsIn(pcm, rate), level: levelOf(pcm), flac: null };
    if (flac && typeof global.encodeFlac === "function") out.flac = global.encodeFlac(pcm, rate);
    return out;
  }

  global.gapsIn = gapsIn;
  global.levelOf = levelOf;
  global.processTake = processTake;

  if (typeof importScripts === "function" && typeof document === "undefined") {   // the worker
    importScripts("flac.js");
    global.onmessage = ev => {
      const { id, pcm, rate, flac } = ev.data;
      try {
        const r = processTake(pcm, rate, flac);
        global.postMessage({ id, gaps: r.gaps, level: r.level, flac: r.flac }, r.flac ? [r.flac.buffer] : []);
      } catch (err) {
        global.postMessage({ id, error: String(err && err.message || err) });
      }
    };
  }
})(typeof window !== "undefined" ? window : globalThis);
