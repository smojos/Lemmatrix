// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
//
// A small FLAC encoder for ɛλicit (IDEAS.md idea 19): mono, 16-bit, lossless, no library.
// Written from the FLAC format specification (RFC 9639). Each block of 4096 samples is coded as
// CONSTANT, VERBATIM or FIXED (prediction orders 0 to 4) with partitioned Rice residuals
// (RICE2), whichever is smallest. No LPC, so a little bigger than the reference encoder at its
// usual setting, but about half the size of a WAV for speech. The MD5 in STREAMINFO is left
// zero ("not computed"), which the format allows.
//
// encodeFlac(samples: Int16Array, rate: number) -> Uint8Array

"use strict";

(function (global) {
  const BLOCK = 4096;

  class Bits {
    constructor(size) { this.buf = new Uint8Array(size || 65536); this.len = 0; this.acc = 0; this.n = 0; }
    grow(extra) {
      if (this.len + extra + 8 <= this.buf.length) return;
      const b = new Uint8Array(Math.max(this.buf.length * 2, this.len + extra + 1024));
      b.set(this.buf.subarray(0, this.len));
      this.buf = b;
    }
    write(value, count) {                 // count <= 24 at a time
      while (count > 0) {
        const take = Math.min(count, 8 - this.n);
        const shift = count - take;
        const part = (value >>> shift) & ((1 << take) - 1);
        this.acc = (this.acc << take) | part;
        this.n += take;
        count -= take;
        if (this.n === 8) { this.grow(1); this.buf[this.len++] = this.acc; this.acc = 0; this.n = 0; }
      }
    }
    writeBig(value, count) {              // up to 36 bits (total samples)
      if (count > 24) { this.write(Math.floor(value / 2 ** 24), count - 24); this.write(value % 2 ** 24, 24); }
      else this.write(value, count);
    }
    signed(value, count) { this.write(value < 0 ? value + 2 ** count : value, count); }
    unary(q) {                            // q zeros, then a one
      while (q >= 24) { this.write(0, 24); q -= 24; }
      this.write(1, q + 1);
    }
    align() { if (this.n) this.write(0, 8 - this.n); }
    bytes() { return this.buf.subarray(0, this.len); }
  }

  const CRC8 = new Uint8Array(256), CRC16 = new Uint16Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = (c & 0x80) ? ((c << 1) ^ 0x07) & 0xff : (c << 1) & 0xff;
    CRC8[i] = c;
    let d = i << 8;
    for (let k = 0; k < 8; k++) d = (d & 0x8000) ? ((d << 1) ^ 0x8005) & 0xffff : (d << 1) & 0xffff;
    CRC16[i] = d;
  }
  const crc8 = (b, from, to) => { let c = 0; for (let i = from; i < to; i++) c = CRC8[c ^ b[i]]; return c; };
  const crc16 = (b, from, to) => {
    let c = 0;
    for (let i = from; i < to; i++) c = ((c << 8) & 0xffff) ^ CRC16[(c >>> 8) ^ b[i]];
    return c;
  };

  function residuals(x, order) {          // the fixed predictors of orders 0 to 4
    const n = x.length, r = new Int32Array(n - order);
    for (let i = order; i < n; i++) {
      let p = 0;
      switch (order) {
        case 1: p = x[i - 1]; break;
        case 2: p = 2 * x[i - 1] - x[i - 2]; break;
        case 3: p = 3 * x[i - 1] - 3 * x[i - 2] + x[i - 3]; break;
        case 4: p = 4 * x[i - 1] - 6 * x[i - 2] + 4 * x[i - 3] - x[i - 4]; break;
      }
      r[i - order] = x[i] - p;
    }
    return r;
  }

  const zig = v => (v >= 0 ? v * 2 : -v * 2 - 1);

  function bestParam(u, from, to) {       // the Rice parameter (0..30) and its cost in bits
    let sum = 0;
    for (let i = from; i < to; i++) sum += u[i];
    const n = to - from;
    if (n === 0) return [0, 0];
    let k = Math.max(0, Math.min(30, Math.floor(Math.log2(Math.max(1, sum / n)))));
    let best = null;
    for (const kk of [k - 1, k, k + 1]) {
      if (kk < 0 || kk > 30) continue;
      let bits = n * (kk + 1);
      for (let i = from; i < to; i++) bits += Math.floor(u[i] / 2 ** kk);
      if (!best || bits < best[1]) best = [kk, bits];
    }
    return best;
  }

  function planResidual(r, blocksize, order) {   // the best partition order and its parameters
    const u = new Float64Array(r.length);
    for (let i = 0; i < r.length; i++) u[i] = zig(r[i]);
    let best = null;
    for (let p = 0; p <= 6; p++) {
      const parts = 1 << p;
      if (blocksize % parts || (blocksize >> p) <= order) break;
      const size = blocksize >> p;
      let bits = 6, params = [], pos = 0;    // 2 bits method + 4 bits partition order
      for (let k = 0; k < parts; k++) {
        const len = k === 0 ? size - order : size;
        const [param, cost] = bestParam(u, pos, pos + len);
        params.push(param);
        bits += 5 + cost;
        pos += len;
      }
      if (!best || bits < best.bits) best = { p, params, bits };
    }
    best.u = u;
    return best;
  }

  function writeSubframe(w, x) {
    const n = x.length;
    let same = true;
    for (let i = 1; i < n && same; i++) same = x[i] === x[0];
    if (same) { w.write(0, 1); w.write(0, 6); w.write(0, 1); w.signed(x[0], 16); return; }
    let best = null;
    for (let order = 0; order <= 4 && order < n; order++) {
      const plan = planResidual(residuals(x, order), n, order);
      const bits = 8 + order * 16 + plan.bits;
      if (!best || bits < best.bits) best = { order, plan, bits };
    }
    if (!best || best.bits >= 8 + 16 * n) {            // VERBATIM
      w.write(0, 1); w.write(1, 6); w.write(0, 1);
      for (let i = 0; i < n; i++) w.signed(x[i], 16);
      return;
    }
    const { order, plan } = best;
    w.write(0, 1); w.write(8 | order, 6); w.write(0, 1); // FIXED, order
    for (let i = 0; i < order; i++) w.signed(x[i], 16);
    w.write(1, 2);                                       // RICE2 (5-bit parameters)
    w.write(plan.p, 4);
    const size = n >> plan.p;
    let pos = 0;
    for (let k = 0; k < plan.params.length; k++) {
      const len = k === 0 ? size - order : size;
      const kk = plan.params[k];
      w.write(kk, 5);
      w.grow(len * 8);
      for (let i = pos; i < pos + len; i++) {
        const v = plan.u[i];
        const q = Math.floor(v / 2 ** kk);
        w.unary(q);
        if (kk) w.write(v % 2 ** kk, kk);
      }
      pos += len;
    }
  }

  function utf8Number(w, v) {             // the frame number, coded like UTF-8
    if (v < 0x80) { w.write(v, 8); return; }
    const bytes = [];
    let n = 2;
    while (v >= 2 ** (5 * n + 1)) n++;
    for (let i = 0; i < n - 1; i++) { bytes.unshift(0x80 | (v & 0x3f)); v = Math.floor(v / 64); }
    bytes.unshift(((0xff00 >> n) & 0xff) | v);
    for (const b of bytes) w.write(b, 8);
  }

  function encodeFlac(samples, rate) {
    const total = samples.length;
    const w = new Bits(Math.max(65536, total * 2));
    for (const c of "fLaC") w.write(c.charCodeAt(0), 8);
    w.write(1, 1); w.write(0, 7); w.write(34, 24);       // last metadata block: STREAMINFO, 34 bytes
    const block = Math.min(BLOCK, Math.max(16, total));
    w.write(block, 16); w.write(block, 16);              // min and max block size
    w.write(0, 24); w.write(0, 24);                      // min and max frame size: unknown
    w.write(rate, 20); w.write(0, 3); w.write(15, 5);    // rate, 1 channel, 16 bits
    w.writeBig(total, 36);
    for (let i = 0; i < 16; i++) w.write(0, 8);          // MD5: not computed
    for (let f = 0, pos = 0; pos < total; f++, pos += BLOCK) {
      const x = samples.subarray(pos, Math.min(total, pos + BLOCK));
      const start = w.len;
      w.write(0xfff8, 16);                               // sync, fixed block size
      w.write(7, 4);                                     // block size: 16 bits at the end of the header
      w.write(0, 4);                                     // sample rate: from STREAMINFO
      w.write(0, 4);                                     // one channel
      w.write(4, 3); w.write(0, 1);                      // 16 bits per sample
      utf8Number(w, f);
      w.write(x.length - 1, 16);
      w.write(crc8(w.buf, start, w.len), 8);
      writeSubframe(w, x);
      w.align();
      w.write(crc16(w.buf, start, w.len), 16);
    }
    return w.bytes().slice();
  }

  global.encodeFlac = encodeFlac;
  if (typeof module !== "undefined") module.exports = { encodeFlac };
})(typeof window !== "undefined" ? window : globalThis);
