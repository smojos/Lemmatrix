# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The database's setup, to send with a bug report or feature request (IDEAS.md idea 50, Josh,
24 October): its fields and their lists, the tag structure, the reference categories, the tier
mapping and the settings, so the developer can see how it is set up, with no data at all: no
lemmas, tokens, utterances or texts, no people and no places, the language and variety as LXX
and VXX. Made from the Anonymous archive's copy (section 3.15), so names in the setup's own text
(a tag's description, a category's name) are replaced as there, then everything that is data is
taken out. The original database is never touched."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import anonymise as an
from . import storage
from .model import Database


def setup_copy(db: Database) -> Database:
    """A copy of the database with its setup only."""
    opts = an.Options.for_kind(an.ANONYMOUS)
    opts.hide_language_code = opts.hide_variety_code = True
    out, _ = an.anonymise(db, None, opts, an.Report())
    out.entries, out.utterances, out.texts = [], [], []
    md = out.metadata
    md.researchers, md.participants, md.locations = [], [], []
    md.author, md.description = "", ""
    md.name = "Setup"
    out.path = None
    return out


def file_name(db: Database, today: dt.date | None = None) -> str:
    return f"Lemmatrix setup {(today or dt.date.today()).isoformat()}.xml"


def write(db: Database, folder: str | Path) -> Path:
    """Write the setup into folder (made if need be), never over a file already there."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / file_name(db)
    n = 2
    while path.exists():
        path = folder / f"{path.stem.split(' (')[0]} ({n}).xml"
        n += 1
    storage.save(setup_copy(db), path, backup=False)
    return path
