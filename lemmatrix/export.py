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
    hit = db.settings.tags.find(db.word_class(e) or None, tag)
    t = hit[0] if hit else db.settings.tags.find_anywhere(tag)
    return t.file_code() if t else tag


def database_table(db: Database, entries: list[Entry] | None = None) -> tuple[list[str], list[list[str]]]:
    """Every lemma field and token field: one row per token, lemmas without tokens on a row of their own."""
    entries = db.entries if entries is None else entries
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
