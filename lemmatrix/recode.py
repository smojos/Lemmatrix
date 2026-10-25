# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""People's codes renamed in Edit → Lists, followed outside the database's own records (the
audit, P7, 25 October): the speaker part of TextGrid tier names (`tx@SP1`), clipped utterances'
copies of those tiers, and the stored ɛλicit requests. The tokens, texts, notebook and segment
soundfiles are followed by their own code (ui/main_window.py, edit_lists). The archives rename
the same things in their copies (anonymise.py).

No Qt in this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .model import Database, sync_file, tier_base


@dataclass
class Result:
    textgrids: int = 0                                     # TextGrids whose tier names were renamed
    failed: list[str] = field(default_factory=list)        # TextGrids that couldn't be read or written
    utterances: int = 0                                    # clipped utterances' copies renamed
    requests: int = 0                                      # stored ɛλicit requests renamed


def renamed_tier(name: str, codes: dict[str, str]) -> str:
    """tx@SP1 -> tx@SP7 when SP1 became SP7; anything else as it is."""
    _, speaker = tier_base(name)
    if not speaker or speaker not in codes:
        return name
    return f"{name.partition('@')[0]}@{codes[speaker]}"


def follow(db: Database, codes: dict[str, str]) -> Result:
    """Follow renamed people's codes (old -> new) everywhere outside the records themselves."""
    out = Result()
    codes = {o: n for o, n in codes.items() if o and n and o != n}
    if not codes:
        return out
    for e in db.items():                          # clipped utterances' copies of their line's tiers
        src = getattr(e, "source", None)
        if src is None or not src.copied:
            continue
        new = {renamed_tier(k, codes): v for k, v in src.copied.items()}
        if list(new) != list(src.copied):
            src.copied = new
            out.utterances += 1
    if db.path:
        for text in db.texts:
            if text.textgrid:
                try:
                    if _rename_tiers(db, text, codes):
                        out.textgrids += 1
                except Exception:                 # noqa: BLE001 (praatio raises several kinds; the file
                    out.failed.append(text.textgrid)   # is left as it was)
        out.requests = _rename_requests(db, codes)
    return out


def _rename_tiers(db: Database, text, codes: dict[str, str]) -> bool:
    """Rename the tiers in the text's TextGrid file (after a dated copy in Backups). Only tier
    names change; every segment is left as it is."""
    from . import storage
    from . import textgrid as tgmod
    from .pull import backup_textgrid
    path = Path(storage.text_folder(db)) / text.textgrid
    if not path.exists():
        return False
    tg = tgmod.read_grid(path)
    if not any(renamed_tier(n, codes) != n for n in tg.tierNames):
        return False
    from praatio import textgrid
    new = textgrid.Textgrid(tg.minTimestamp, tg.maxTimestamp)
    for tier in tg.tiers:
        new.addTier(tier.new(name=renamed_tier(tier.name, codes)))
    backup_textgrid(db, path)
    tmp = path.with_name(path.name + ".lemmatrix-writing")
    try:
        new.save(str(tmp), format="long_textgrid", includeBlankSpaces=True)
        sync_file(tmp)                            # on the disk before it replaces the old one
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return True


def _rename_requests(db: Database, codes: dict[str, str]) -> int:
    """The speaker's and researcher's codes in the Elicit folder's requests (the review takes a
    new token's speaker from there)."""
    from . import elicit
    n = 0
    for st in elicit.stored_requests(db.path):
        changed = False
        for person in (st.request.speaker, st.request.researcher):
            if person.get("code") in codes:
                person["code"] = codes[person["code"]]
                changed = True
        if changed:
            (st.folder / "request.json").write_text(st.request.to_json(), encoding="utf-8")
            n += 1
    return n
