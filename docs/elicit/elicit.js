// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright © 2026 Joshua A. G. Smolders
//
// ɛλicit, stage 1 (IDEAS.md idea 19): the speaker opens the request file the researcher sent
// (a zip made by Lemmatrix), answers three questions, records the cards one by one, and at the
// end sends the recordings back as a zip. Nothing leaves the device except that zip, which the
// speaker sends themselves. Until then the request and the recordings are kept in the browser
// (IndexedDB), so closing the page and opening the file again carries on where it stopped.
//
// No libraries: the zips are read and written here (stored, not compressed: recordings hardly
// compress), and recordings are 16-bit PCM WAV with echo cancellation, noise suppression and
// automatic gain switched off.

"use strict";

const RESPONSE_FORMAT = "lemmatrix-elicit-response";
const REQUEST_FORMAT = "lemmatrix-elicit-request";
const app = document.getElementById("app");

// ------------------------------------------------------------------------------------------
// Small helpers
// ------------------------------------------------------------------------------------------

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function fill(text, vars) {
  return String(text || "").replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
}

// Each new screen fades in after the last one fades out: calm, not a flash (Josh, 20 October).
// Taps are ignored while it fades. Without motion (the device's "reduce motion"), it just changes.
const FADE_OUT = 220, QUIET = matchMedia("(prefers-reduced-motion: reduce)");
let fading = null;

function show(...nodes) {
  const swap = () => {
    fading = null;
    app.replaceChildren(...nodes);
    window.scrollTo(0, 0);
    app.classList.remove("out");
  };
  clearTimeout(fading);
  if (QUIET.matches || !app.firstChild) return swap();
  app.classList.add("out");
  fading = setTimeout(swap, FADE_OUT);
}

const RTL = new Set(["ar", "he", "fa", "ur"]);

// ------------------------------------------------------------------------------------------
// Zip files (stored entries; deflated ones are read too, where the browser can)
// ------------------------------------------------------------------------------------------

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

async function readZip(buffer) {
  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  let eocd = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
    if (view.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("not a zip file");
  const count = view.getUint16(eocd + 10, true);
  let p = view.getUint32(eocd + 16, true);
  const files = {};
  const utf8 = new TextDecoder();
  for (let k = 0; k < count; k++) {
    if (view.getUint32(p, true) !== 0x02014b50) throw new Error("damaged zip file");
    const method = view.getUint16(p + 10, true);
    const size = view.getUint32(p + 20, true);
    const nameLen = view.getUint16(p + 28, true);
    const extraLen = view.getUint16(p + 30, true);
    const commentLen = view.getUint16(p + 32, true);
    const local = view.getUint32(p + 42, true);
    const name = utf8.decode(bytes.subarray(p + 46, p + 46 + nameLen));
    const start = local + 30 + view.getUint16(local + 26, true) + view.getUint16(local + 28, true);
    let data = bytes.slice(start, start + size);
    if (method === 8) {
      if (typeof DecompressionStream === "undefined") throw new Error("compressed zip");
      const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
      data = new Uint8Array(await new Response(stream).arrayBuffer());
    } else if (method !== 0) {
      throw new Error("unsupported zip");
    }
    files[name] = data;
    p += 46 + nameLen + extraLen + commentLen;
  }
  return files;
}

function writeZip(entries) {          // [{name, data: Uint8Array}] -> Blob
  const enc = new TextEncoder();
  const parts = [], central = [];
  let offset = 0;
  const now = new Date();
  const dosTime = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
  const dosDate = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
  for (const e of entries) {
    const name = enc.encode(e.name);
    const crc = crc32(e.data);
    const head = new DataView(new ArrayBuffer(30));
    head.setUint32(0, 0x04034b50, true); head.setUint16(4, 20, true); head.setUint16(6, 0x0800, true);
    head.setUint16(8, 0, true); head.setUint16(10, dosTime, true); head.setUint16(12, dosDate, true);
    head.setUint32(14, crc, true); head.setUint32(18, e.data.length, true); head.setUint32(22, e.data.length, true);
    head.setUint16(26, name.length, true); head.setUint16(28, 0, true);
    parts.push(head.buffer, name, e.data);
    const c = new DataView(new ArrayBuffer(46));
    c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true);
    c.setUint16(8, 0x0800, true); c.setUint16(10, 0, true); c.setUint16(12, dosTime, true);
    c.setUint16(14, dosDate, true); c.setUint32(16, crc, true); c.setUint32(20, e.data.length, true);
    c.setUint32(24, e.data.length, true); c.setUint16(28, name.length, true);
    c.setUint32(42, offset, true);
    central.push(c.buffer, name);
    offset += 30 + name.length + e.data.length;
  }
  const size = central.reduce((s, b) => s + b.byteLength, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); end.setUint16(8, entries.length, true);
  end.setUint16(10, entries.length, true); end.setUint32(12, size, true); end.setUint32(16, offset, true);
  return new Blob([...parts, ...central, end.buffer], { type: "application/zip" });
}

// ------------------------------------------------------------------------------------------
// WAV files
// ------------------------------------------------------------------------------------------

function toPcm(chunks) {
  const n = chunks.reduce((s, c) => s + c.length, 0);
  const pcm = new Int16Array(n);
  let i = 0;
  for (const c of chunks) for (let k = 0; k < c.length; k++) {
    const v = Math.max(-1, Math.min(1, c[k]));
    pcm[i++] = v < 0 ? v * 32768 : v * 32767;
  }
  return pcm;
}

function wav(pcm, rate, info) {
  const n = pcm.length;
  const enc = new TextEncoder();
  const fields = [];
  for (const [key, value] of Object.entries(info)) {
    if (!value) continue;
    let data = enc.encode(value + "\0");
    if (data.length % 2) data = new Uint8Array([...data, 0]);
    fields.push([key, data]);
  }
  const infoSize = fields.length ? 4 + fields.reduce((s, [, d]) => s + 8 + d.length, 0) : 0;
  const total = 12 + 24 + 8 + pcm.byteLength + (infoSize ? 8 + infoSize : 0);
  const buf = new ArrayBuffer(total);
  const v = new DataView(buf);
  const str = (o, s) => { for (let k = 0; k < s.length; k++) v.setUint8(o + k, s.charCodeAt(k)); };
  str(0, "RIFF"); v.setUint32(4, total - 8, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, pcm.byteLength, true);
  new Int16Array(buf, 44, n).set(pcm);
  let o = 44 + pcm.byteLength;
  if (infoSize) {
    str(o, "LIST"); v.setUint32(o + 4, infoSize, true); str(o + 8, "INFO"); o += 12;
    for (const [key, data] of fields) {
      str(o, key); v.setUint32(o + 4, data.length, true);
      new Uint8Array(buf, o + 8, data.length).set(data); o += 8 + data.length;
    }
  }
  return new Blob([buf], { type: "audio/wav" });
}

// ------------------------------------------------------------------------------------------
// Keeping the request and the recordings on the device (IndexedDB)
// ------------------------------------------------------------------------------------------

const store = {
  db: null,
  async open() {
    if (this.db) return this.db;
    this.db = await new Promise((resolve, reject) => {
      const r = indexedDB.open("elicit", 1);
      r.onupgradeneeded = () => r.result.createObjectStore("requests", { keyPath: "id" });
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(r.error);
    });
    return this.db;
  },
  async run(mode, fn) {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("requests", mode);
      const req = fn(tx.objectStore("requests"));
      tx.oncomplete = () => resolve(req && req.result);
      tx.onerror = () => reject(tx.error);
    });
  },
  get(id) { return this.run("readonly", s => s.get(id)); },
  all() { return this.run("readonly", s => s.getAll()); },
  put(rec) { return this.run("readwrite", s => s.put(rec)); },
  remove(id) { return this.run("readwrite", s => s.delete(id)); },
};

async function persist() {
  try {
    if (navigator.storage && navigator.storage.persist) await navigator.storage.persist();
  } catch (e) { /* the browser decides */ }
}

// ------------------------------------------------------------------------------------------
// The request in hand
// ------------------------------------------------------------------------------------------

let S = null;   // {req, files, zip (Blob), answers: {n: {status, wav, recorded, seconds}}}

function l2() { return S && S.req.languages.length > 1 ? S.req.languages[1] : null; }
function en() { return S.req.languages[0]; }

function vars(lang) {
  return {
    name: S.req.speaker.name, researcher: S.req.researcher.name,
    language: (S.req.language_names || {})[lang] || S.req.database.language_name || "",
  };
}

function text(key, extra) {        // [english, second language or null]
  const out = [];
  for (const lang of [en(), l2()]) {
    if (!lang) { out.push(null); continue; }
    const p = S.req.prompts[lang] || (lang === en() ? S.req.prompts.en : null);
    out.push(p && p[key] ? fill(p[key], Object.assign(vars(lang), extra || {})) : null);
  }
  if (out[1] === out[0]) out[1] = null;
  return out;
}

function say(key, extra, cls) {
  const [a, b] = text(key, extra);
  const lang2 = l2();
  return h("div", { class: "say " + (cls || "") },
    h("div", { class: "en", lang: en() }, a),
    b ? h("div", { class: "l2", lang: lang2, dir: RTL.has(lang2.split("-")[0]) ? "rtl" : "auto" }, b) : null);
}

function btn(key, onclick, cls, extra) {
  const [a, b] = text(key, extra);
  const lang2 = l2();
  return h("button", { class: cls || "", onclick },
    h("span", { lang: en() }, a),
    b ? h("span", { class: "l2", lang: lang2, dir: "auto" }, b) : null);
}

async function save() {
  await store.put({ id: S.req.id, zip: S.zip, answers: S.answers, drive: S.driveId || "",
                    saved: new Date().toISOString() });
}

function byDrive() { return S && S.req.transport === "drive"; }

async function destroy() {
  stopMic();
  if (S) await store.remove(S.req.id);
}

function applyAccent(colour) {
  if (!/^#[0-9a-f]{6}$/i.test(colour || "")) return;
  document.documentElement.style.setProperty("--accent", colour);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = colour;
}

async function load(zipBlob, answers) {
  const files = await readZip(await zipBlob.arrayBuffer());
  if (!files["request.json"]) throw new Error("no request.json");
  const req = JSON.parse(new TextDecoder().decode(files["request.json"]));
  if (req.format !== REQUEST_FORMAT) throw new Error("not an ɛλicit request");
  S = { req, files, zip: zipBlob, answers: answers || {} };
  applyAccent(req.accent);
  document.documentElement.lang = en();
}

function expired() {
  const today = new Date().toISOString().slice(0, 10);
  return S.req.expires && today > S.req.expires;
}

// ------------------------------------------------------------------------------------------
// Screens
// ------------------------------------------------------------------------------------------

// ------------------------------------------------------------------------------------------
// Through Google Drive (stage 2): the link is .../elicit/#d=<request.json's id>&k=<API key>.
// The request and its pictures and recordings to repeat are read with the key (shared by link);
// each recording goes to its own upload link as soon as it is good. Nothing to open or send.
// ------------------------------------------------------------------------------------------

const DRIVE = "https://www.googleapis.com/drive/v3/files/";

function linkParams() {
  const p = new URLSearchParams(location.hash.slice(1));
  return { id: p.get("d") || "", key: p.get("k") || "" };
}

async function driveFile(id, key) {
  const r = await fetch(DRIVE + encodeURIComponent(id) + "?alt=media&key=" + encodeURIComponent(key));
  if (!r.ok) throw new Error("Google Drive answered " + r.status);
  return new Uint8Array(await r.arrayBuffer());
}

async function openLink(id, key) {
  let saved = [];
  try { saved = await store.all(); } catch (e) { saved = []; }
  const prior = saved.find(rec => rec.drive === id);
  if (prior) {                                       // opened before on this device: carry on
    await load(prior.zip, prior.answers);
    S.driveId = id;
    return begin();
  }
  show(h("div", { class: "panel" }, h("div", { class: "say" }, h("div", { class: "en" }, "Opening the request…"))));
  try {
    const reqBytes = await driveFile(id, key);
    const req = JSON.parse(new TextDecoder().decode(reqBytes));
    const entries = [{ name: "request.json", data: reqBytes }];
    for (const c of req.cards || []) {
      if (c.image && c.image_id) entries.push({ name: c.image, data: await driveFile(c.image_id, key) });
      if (c.original && c.original_id) entries.push({ name: c.original, data: await driveFile(c.original_id, key) });
    }
    await load(writeZip(entries));
  } catch (e) {
    show(h("div", { class: "panel" },
      h("div", { class: "say danger" }, h("div", { class: "en" }, "This link can't be opened just now."),
        h("div", { class: "l2" }, "Check the internet connection and try again. If it still doesn't open, the " +
          "request may have expired or been withdrawn: please contact the person who sent it.")),
      h("div", { class: "note" }, String(e && e.message || e)),
      h("div", { class: "buttons" }, h("button", { class: "main", onclick: () => openLink(id, key) }, "Try again"))));
    return;
  }
  S.driveId = id;
  persist();
  await save();
  begin();
}

let uploading = null;
let lastError = "";                  // shown small on the waiting screen, for whoever tests it

async function uploadPending() {
  // Every recording that is good but not uploaded yet, in order; false if one couldn't go now.
  if (!byDrive()) return true;
  if (uploading) return uploading;
  uploading = (async () => {
    let ok = true;
    for (const c of S.req.cards) {
      const a = S.answers[c.n];
      if (!a || a.status !== "recorded" || a.uploaded || !c.upload) continue;
      try {
        const r = await fetch(c.upload, { method: "PUT", headers: { "Content-Type": a.wav.type || "audio/wav" },
                                          body: a.wav });
        if (!r.ok) throw new Error("upload " + r.status);
        a.uploaded = true;
        await save();
      } catch (e) {
        lastError = String(e && e.message || e) + (navigator.onLine ? " (online)" : " (offline)");
        console.error("ɛλicit upload", c.n, e);
        ok = false;
        break;
      }
    }
    uploading = null;
    return ok;
  })();
  return uploading;
}

window.addEventListener("online", () => { if (byDrive()) uploadPending(); });

async function putJSON(url, data) {
  const r = await fetch(url, { method: "PUT", headers: { "Content-Type": "application/json" },
                               body: JSON.stringify(data, null, 1) });
  if (!r.ok) throw new Error("upload " + r.status);
}

async function tellResearcher(reason) {
  // Turned down on the phone: the researcher sees why (best effort; nothing is kept here).
  if (!byDrive() || !S.req.drive || !S.req.drive.status) return;
  try { await putJSON(S.req.drive.status, { request: S.req.id, reason, when: new Date().toISOString() }); }
  catch (e) { /* offline: the request simply expires */ }
}

async function sendDrive() {
  const total = S.req.cards.filter(c => (S.answers[c.n] || {}).status === "recorded").length;
  const line = h("div", { class: "note" });
  const panel = h("div", { class: "panel" }, say("goodbye"), line);
  show(panel);
  for (;;) {
    const done = S.req.cards.filter(c => (S.answers[c.n] || {}).uploaded).length;
    line.replaceChildren(...text("sending", { n: done, total }).filter(Boolean).map(t => h("div", {}, t)));
    if (await uploadPending()) {
      try {
        await putJSON(S.req.drive.response, responseData());
        break;
      } catch (e) { lastError = "response: " + String(e && e.message || e); }
    }
    line.replaceChildren(...text("waiting_net").filter(Boolean).map(t => h("div", {}, t)),
      lastError ? h("div", { class: "note" }, lastError) : "");
    await new Promise(res => setTimeout(res, 8000));
  }
  await destroy();
  show(h("div", { class: "panel" }, say("sent_done"), say("closing", null, "small")));
}

async function start() {
  const link = linkParams();
  if (link.id && link.key) return openLink(link.id, link.key);
  let saved = [];
  try { saved = await store.all(); } catch (e) { saved = []; }
  const input = h("input", { type: "file", accept: ".zip,application/zip", onchange: () => openFile(input) });
  const resume = [];
  for (const rec of saved) {
    try {
      const files = await readZip(await rec.zip.arrayBuffer());
      const req = JSON.parse(new TextDecoder().decode(files["request.json"]));
      const done = Object.keys(rec.answers || {}).length;
      resume.push(h("button", { class: "main", onclick: () => reopen(rec) },
        `Carry on: ${req.researcher.name}'s request for ${req.speaker.name} (${done} of ${req.cards.length})`));
    } catch (e) { /* unreadable: ignore */ }
  }
  show(h("div", { class: "panel" },
    h("div", { class: "say" }, h("div", { class: "en" }, "Open the request file"),
      h("div", { class: "l2" }, "Choose the file you were sent with the link (a .zip file).")),
    h("div", { class: "buttons" }, ...resume,
      h("label", { class: "button" + (resume.length ? "" : " main") },
        h("span", {}, "Open the request file"), input))));
}

async function openFile(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  let prior = null;
  try {
    await load(file);
    prior = await store.get(S.req.id);
  } catch (e) {
    show(h("div", { class: "panel" },
      h("div", { class: "say danger" }, h("div", { class: "en" }, "This file can't be opened here."),
        h("div", { class: "l2" }, "Please choose the .zip file you were sent with the link (" + e.message + ").")),
      h("div", { class: "buttons" }, h("button", { onclick: start }, "Back"))));
    return;
  }
  if (prior) S.answers = prior.answers || {};
  persist();
  await save();
  begin();
}

async function reopen(rec) {
  await load(rec.zip, rec.answers);
  begin();
}

function begin() {
  if (expired()) {
    destroy();
    show(h("div", { class: "panel" }, say("expired", null, "danger")));
    return;
  }
  areYou();
}

function areYou() {
  show(h("div", { class: "panel" }, say("are_you"),
    h("div", { class: "buttons row" }, btn("yes", agreement, "main"), btn("no", giveDevice))));
}

function giveDevice() {
  show(h("div", { class: "panel" }, say("give_device"),
    h("div", { class: "buttons" }, btn("ok", areYou, "main"), btn("not_around", notAround, "quiet"))));
}

async function notAround() {
  await tellResearcher("not around");
  await destroy();
  show(h("div", { class: "panel" }, say("not_around_end"), say("goodbye", null, "small")));
}

function agreement() {
  show(h("div", { class: "panel" }, say("agreement"),
    h("div", { class: "buttons row" }, btn("yes", speak, "main"), btn("no", contact))));
}

function contact() {
  show(h("div", { class: "panel" }, say("contact"),
    h("div", { class: "buttons" }, btn("ok", async () => {
      await tellResearcher("no participation agreement");
      await destroy();
      show(h("div", { class: "panel" }, say("goodbye")));
    }, "main"))));
}

function speak() {
  show(h("div", { class: "panel" }, say("speak"),
    h("div", { class: "buttons row" }, btn("yes", opener, "main"), btn("no", async () => {
      await tellResearcher("doesn't speak the language");
      await destroy();
      show(h("div", { class: "panel" }, say("goodbye"), say("wrong_language_end", null, "small")));
    }))));
}

function opener() {
  const err = h("div", { class: "error" });
  show(h("div", { class: "panel" }, say("opener"), say("mic_allow", null, "small"),
    h("div", { class: "buttons" }, btn("ready", async () => {
      try {
        await startMic();
      } catch (e) {
        err.replaceChildren(...[text("mic_error")[0], text("mic_error")[1]].filter(Boolean)
          .map(t => h("div", {}, t)), h("div", { class: "note" }, String(e && e.message || e)));
        return;
      }
      nextCard();
    }, "main")), err));
}

function nextCard() {
  const card = S.req.cards.find(c => !S.answers[c.n]);
  if (!card) return finished();
  showCard(card);
}

function mediaURL(name, type) {
  const data = S.files[name];
  if (!data) return null;
  return URL.createObjectURL(new Blob([data], { type }));
}

function imageType(name) {
  const ext = name.split(".").pop().toLowerCase();
  return ext === "png" ? "image/png" : ext === "gif" ? "image/gif" : "image/jpeg";
}

const EAR = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ' +
  'stroke-linejoin="round"><path d="M7 9a5 5 0 0 1 10 0c0 3-2.5 3.8-3.3 5.6-.6 1.4-.9 3.4-3 3.4A2.7 2.7 0 0 1 8 15.4"/>' +
  '<path d="M10 9.2a2 2 0 0 1 4 0c0 1-1 1.4-1.4 2"/></svg>';
const MIC = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="9" y="3" width="6" height="11" rx="3"/>' +
  '<path d="M6 11a6 6 0 0 0 12 0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' +
  '<path d="M12 17v4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
const STOP = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';

function svg(markup) {
  const t = document.createElement("template");
  t.innerHTML = markup;        // our own constant markup, never the request's text
  return t.content.firstChild;
}

function showCard(card) {
  const total = S.req.cards.length;
  const done = Object.keys(S.answers).length;
  const lang2 = l2();
  const prompt = h("div", { class: "prompt" });
  if (card.kind === "rerecord") {
    prompt.append(say("rerecord"));
    const url = card.original ? mediaURL(card.original, "audio/wav") : null;
    if (url) {
      const audio = new Audio(url);
      prompt.append(h("button", { class: "ear", "aria-label": text("listen")[0], onclick: () => {
        audio.currentTime = 0; audio.play();
      } }, svg(EAR)));
    }
  } else {
    prompt.append(say("new_card"));
    if (card.image) {
      const url = mediaURL(card.image, imageType(card.image));
      if (url) prompt.append(h("img", { src: url, alt: "" }));
    }
    const words = card.texts || {};
    if (words[en()]) prompt.append(h("div", { class: "word", lang: en() }, words[en()]));
    if (lang2 && words[lang2]) {
      prompt.append(h("div", { class: "word l2", lang: lang2, dir: "auto" }, words[lang2]));
    }
    if (card.repeat) prompt.append(say("say_repeat", null, "small"));
  }
  const area = h("div", {});
  show(h("div", {},
    h("div", { class: "progress" }, text("progress", { n: done + 1, total }).filter(Boolean).join(" · ")),
    h("div", { class: "bar" }, h("div", { style: `width:${Math.round(100 * done / total)}%` })),
    h("div", { class: "panel" }, prompt, area)));
  recordArea(card, area);
}

function recordArea(card, area) {
  const label = h("div", { class: "reclabel" }, text("record").filter(Boolean).join(" · "));
  const meterFill = h("div", {});
  const meter = h("div", { class: "meter" }, meterFill);
  const rec = h("button", { class: "rec", "aria-label": text("record")[0] }, svg(MIC));
  let recording = false;
  rec.addEventListener("click", async () => {
    if (!recording) {
      recording = true;
      rec.classList.add("on");
      rec.replaceChildren(svg(STOP));
      label.textContent = text("recording").filter(Boolean).join(" · ");
      mic.begin(level => { meterFill.style.width = Math.min(100, Math.round(level * 300)) + "%"; });
    } else {
      recording = false;
      const result = mic.end(S.req.speaker.code);
      afterRecording(card, area, result);
    }
  });
  area.replaceChildren(rec, label, meter,
    h("div", { class: "buttons" }, btn("cant_say", () => answer(card, { status: "skipped" }), "quiet")));
}

function afterRecording(card, area, result) {
  const url = URL.createObjectURL(result.blob);
  const audio = new Audio(url);
  audio.play().catch(() => {});
  area.replaceChildren(
    h("div", { class: "buttons" },
      btn("listen", () => { audio.currentTime = 0; audio.play(); }, "quiet"),
      btn("its_good", () => {
        audio.pause();
        answer(card, { status: "recorded", wav: keep(result), recorded: result.recorded, date: result.date,
                       seconds: result.seconds, rate: result.rate });
      }, "main"),
      btn("try_again", () => { audio.pause(); recordArea(card, area); }),
      btn("cant_say", () => { audio.pause(); answer(card, { status: "skipped" }); }, "quiet")));
}

function keep(result) {
  // What is kept and sent: the WAV as recorded (it plays back), or the same sound as FLAC when the
  // request asks for it (lossless, about 60% of the size: flac.js).
  if (S.req.audio === "flac" && typeof encodeFlac === "function") {
    return new Blob([encodeFlac(result.pcm, result.rate)], { type: "audio/flac" });
  }
  return result.blob;
}

async function answer(card, result) {
  S.answers[card.n] = result;
  await save();
  uploadPending();                   // through Drive: on its way now (kept here until it has gone)
  nextCard();
}

function finished() {
  stopMic();
  show(h("div", { class: "panel" }, say("finished"),
    h("div", { class: "buttons" }, btn("goodbye", () => (byDrive() ? sendDrive() : sendScreen()), "main"))));
}

function responseData() {
  const cards = [];
  for (const c of S.req.cards) {
    const a = S.answers[c.n];
    if (!a) continue;
    const item = { n: c.n, status: a.status };
    if (a.status === "recorded" && a.wav) {
      item.file = c.file;
      item.recorded = a.recorded;
      item.date = a.date;               // the day on the device (the recording's date in Lemmatrix)
      item.seconds = a.seconds;
      item.rate = a.rate;
    }
    cards.push(item);
  }
  return { format: RESPONSE_FORMAT, version: 1, request: S.req.id, speaker: S.req.speaker.code,
           finished: new Date().toISOString(), cards };
}

function responseZip() {
  const enc = new TextEncoder();
  const entries = [{ name: "response.json", data: enc.encode(JSON.stringify(responseData(), null, 1)) }];
  return Promise.all(S.req.cards.filter(c => S.answers[c.n] && S.answers[c.n].wav).map(async c => ({
    name: "recordings/" + c.file, data: new Uint8Array(await S.answers[c.n].wav.arrayBuffer()),
  }))).then(recs => writeZip(entries.concat(recs)));
}

function fileName() {
  return `Elicit_recordings_${S.req.speaker.code.replace(/[^\w-]/g, "_")}_${S.req.created.slice(0, 10)}.zip`;
}

async function sendScreen() {
  const blob = await responseZip();
  const name = fileName();
  const file = new File([blob], name, { type: "application/zip" });
  const buttons = [];
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    buttons.push(btn("send", async () => {
      try { await navigator.share({ files: [file], title: name }); } catch (e) { /* cancelled */ }
    }, "main"));
  }
  buttons.push(btn("save", () => {
    const a = h("a", { href: URL.createObjectURL(blob), download: name });
    document.body.append(a);
    a.click();
    a.remove();
  }, buttons.length ? "" : "main"));
  buttons.push(btn("sent", async () => {
    await destroy();
    show(h("div", { class: "panel" }, say("closing")));
  }, "quiet"));
  show(h("div", { class: "panel" }, say("send_title"),
    h("div", { class: "note" }, name, " · ", (blob.size / 1048576).toFixed(1), " MB"),
    h("div", { class: "buttons" }, ...buttons)));
}

// ------------------------------------------------------------------------------------------
// The microphone
// ------------------------------------------------------------------------------------------

const mic = {
  stream: null, ctx: null, node: null, chunks: null, onLevel: null, started: 0,
  begin(onLevel) {
    this.chunks = [];
    this.onLevel = onLevel;
    this.started = Date.now();
    if (this.ctx.state === "suspended") this.ctx.resume();
  },
  push(samples) {
    if (!this.chunks) return;
    this.chunks.push(samples);
    if (this.onLevel) {
      let sum = 0;
      for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
      this.onLevel(Math.sqrt(sum / samples.length));
    }
  },
  end(speaker) {
    const chunks = this.chunks || [];
    this.chunks = null;
    const rate = this.ctx.sampleRate;
    const now = new Date();
    const day = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const pcm = toPcm(chunks);
    return { blob: wav(pcm, rate, { IART: speaker, ICRD: day }), pcm, rate, seconds: +(pcm.length / rate).toFixed(2),
             recorded: now.toISOString(), date: day };
  },
};

const WORKLET = `class Tap extends AudioWorkletProcessor {
  process(inputs) { const c = inputs[0] && inputs[0][0]; if (c) this.port.postMessage(c.slice(0)); return true; }
}
registerProcessor("tap", Tap);`;

async function startMic() {
  if (mic.stream) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("This browser can't record (the page must be opened over https).");
  }
  mic.stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
  });
  const Ctx = window.AudioContext || window.webkitAudioContext;
  mic.ctx = new Ctx();
  const source = mic.ctx.createMediaStreamSource(mic.stream);
  if (mic.ctx.audioWorklet) {
    const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    await mic.ctx.audioWorklet.addModule(url);
    mic.node = new AudioWorkletNode(mic.ctx, "tap");
    mic.node.port.onmessage = e => mic.push(e.data);
    source.connect(mic.node);
    const silent = mic.ctx.createGain();          // keeps the node running; nothing is heard
    silent.gain.value = 0;
    mic.node.connect(silent).connect(mic.ctx.destination);
  } else {                                       // older browsers
    mic.node = mic.ctx.createScriptProcessor(4096, 1, 1);
    mic.node.onaudioprocess = e => mic.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    source.connect(mic.node);
    mic.node.connect(mic.ctx.destination);
  }
}

function stopMic() {
  if (mic.stream) mic.stream.getTracks().forEach(t => t.stop());
  if (mic.ctx) mic.ctx.close().catch(() => {});
  mic.stream = mic.ctx = mic.node = null;
}

// ------------------------------------------------------------------------------------------

fetch("logo.svg").then(r => r.text()).then(t => {
  if (t.trim().startsWith("<svg")) document.getElementById("logo").innerHTML = t;   // our own file
}).catch(() => {});
start();
