# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Exporting data to other formats (CSV for now; SFM and LIFT later).

CSV files are UTF-8 with a byte-order mark, so Excel on Windows reads IPA
correctly, and use the "excel" dialect (commas, quotes where needed). A cell
may hold several lines; Excel shows them inside the one cell.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .model import Database, Entry, Token, nfc


def _lemma_columns(db: Database) -> list[tuple[str, callable]]:
    s = db.settings
    cols = [("Reference", lambda e: e.ref)]
    for f in s.entry_fields:
        if f.multilingual:
            for lang in s.gloss_languages:
                cols.append((f"{f.title} ({lang})", lambda e, n=f.name, l=lang: e.get(n, l)))
        else:
            cols.append((f.title, lambda e, n=f.name: e.get(n)))
    cols.append(("Gloss in file names", lambda e: e.file_gloss))
    return cols


def _token_columns(db: Database) -> list[tuple[str, callable]]:
    s = db.settings
    cols = [("Tags", lambda e, t: ", ".join(t.tags) if t else ""),
            ("Tag codes", lambda e, t: " ".join(
                c for c in (_code(db, e, x) for x in t.tags) if c) if t else "")]
    for f in s.token_fields:
        if f.multilingual:
            for lang in s.gloss_languages:
                cols.append((f"{f.title} ({lang})", lambda e, t, n=f.name, l=lang: t.get(n, l) if t else ""))
        else:
            cols.append((f.title, lambda e, t, n=f.name: t.get(n) if t else ""))
    cols += [("Speaker", lambda e, t: t.speaker if t else ""),
             ("Date", lambda e, t: t.collected if t else ""),
             ("Sound file", lambda e, t: t.file if t else "")]
    return cols


def _code(db: Database, e: Entry, tag: str) -> str:
    t = db.settings.tags.tag(tag)
    return t.file_code() if t else tag


def database_table(db: Database, entries: list[Entry] | None = None) -> tuple[list[str], list[list[str]]]:
    """Every lemma field and token field: one row per token, lemmas without tokens on a row of their own.
    The entire database (entries None) has utterances too, after the lemmas: their lemma columns are
    blank but for the reference and (in Gloss in file names) the file label. Kind says which is which."""
    whole = entries is None
    entries = db.entries if whole else entries
    lcols, tcols = _lemma_columns(db), _token_columns(db)
    lnames, tnames = [n for n, _ in lcols], [n for n, _ in tcols]
    shared = set(lnames) & set(tnames)            # e.g. a Comment on both lemmas and tokens
    header = ([f"{n} (lemma)" if n in shared else n for n in lnames]
              + [f"{n} (token)" if n in shared else n for n in tnames])
    rows = []
    for e in entries:
        lemma = [get(e) for _, get in lcols]
        tokens: list[Token | None] = list(e.tokens) or [None]
        for t in tokens:
            rows.append(lemma + [get(e, t) for _, get in tcols])
    if whole and db.utterances:
        header = header[:1] + ["Kind"] + header[1:]
        rows = [r[:1] + ["Lemma"] + r[1:] for r in rows]
        for u in db.utterances:
            lemma = [""] * len(lcols)
            lemma[0], lemma[-1] = u.ref, u.label
            for t in u.tokens:
                row = lemma + [get(u, t) for _, get in tcols]
                rows.append(row[:1] + ["Utterance"] + row[1:])
    return header, rows


def tag_structure_table(db: Database) -> tuple[list[str], list[list[str]]]:
    """File → Export → Tag structure: one row per group and tag, in tag order."""
    ts = db.settings.tags
    usual, only = ts.usual_map(), ts.only_map()
    header = ["Group", "Tag", "Code", "Default", "Usual for", "Description"]
    rows = []

    def walk(g, path):
        here = path + [g.name]
        hint = "utterances only" if only.get(id(g)) else (", ".join(usual.get(id(g), ())) or "every lemma")
        rows.append([" › ".join(here), "", "", "", hint, g.description])
        for t in g.tags:
            rows.append([" › ".join(here), t.name, t.file_code(), "yes" if t.default else "", "",
                         t.description])
        for sub in g.groups:
            walk(sub, here)
    for g in ts.groups:
        walk(g, [])
    return header, rows


def write_csv(path: str | Path, header: list[str], rows: list[list[str]]) -> int:
    """Write a table; returns the number of data rows."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".part")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, dialect="excel")
        w.writerow([nfc(str(h)) for h in header])
        for r in rows:
            w.writerow([nfc("" if v is None else str(v)) for v in r])
    tmp.replace(path)
    return len(rows)
