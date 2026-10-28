# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Writes lemmatrix/elicit_prompts.py's tables from a review (IDEAS.md idea 92): never edit the
translations by hand, so the reviewed text and the program can't drift apart.

    python tools/write_prompts.py FINAL.json [STATUS]

FINAL.json: {"fr": {key: text or {form: text}}, "ar": {...}, "am": {...}} (the review's final forms,
Josh's corrections applied); STATUS (optional): {"fr": "Machine audited only", ...}. English and
everything outside the two marked blocks are left as they are."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "lemmatrix" / "elicit_prompts.py"
BEGIN, END = "# ---- translations: written by tools/write_prompts.py ----", "# ---- end of translations ----"


def render(final: dict, status: dict) -> str:
    out = [BEGIN, "TRANSLATIONS: dict[str, dict[str, str | dict[str, str]]] = {"]
    for lang, table in final.items():
        out.append(f"    {lang!r}: {{")
        for key, val in table.items():
            out.append(f"        {key!r}: {json.dumps(val, ensure_ascii=False)},")
        out.append("    },")
    out.append("}")
    out.append(f"STATUS: dict[str, str] = {json.dumps(status, ensure_ascii=False)}")
    out.append(END)
    return "\n".join(out)


def main(argv):
    final = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    status = json.loads(Path(argv[2]).read_text(encoding="utf-8")) if len(argv) > 2 else {}
    text = HERE.read_text(encoding="utf-8")
    a, b = text.index(BEGIN), text.index(END) + len(END)
    HERE.write_text(text[:a] + render(final, status) + text[b:], encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv)
