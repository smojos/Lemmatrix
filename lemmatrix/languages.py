# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The world's languages for a lemma's From (Josh, 22 October): every ISO 639-3 code (about 7,900;
the codes Ethnologue uses), from the `pycountry` package, searchable by name or code, the most
widely spoken first. A language the standard lacks (a proto-language, a dialect) is kept as typed.

No Qt here."""

from __future__ import annotations

from functools import lru_cache

from .model import nfc

# About the 100 most widely spoken languages (first and second language speakers), as ISO 639-3
# codes, offered first. Macrolanguage codes (ara, zho, msa…) are used where people usually mean them.
TOP = ("eng zho hin spa fra ara ben por rus urd ind deu jpn pcm mar tel tur tam yue vie tgl kor fas hau "
       "swa jav ita pan kan guj tha amh bho pnb yor ibo ory mal mya azb sun pol ukr ron nld kur sin "
       "khm npi zul uzb som ell ces hun swe aka run kin xho bel hrv srp bos slk dan fin nob heb cat "
       "glg kaz tuk tgk kir mon bul sqi hye kat lit lav est slv mkd lao ceb ilo hil mad min ful wol "
       "lin kon lug orm tir nya sna sot tsn afr mlg").split()


@lru_cache(maxsize=1)
def _all() -> dict[str, str]:
    """{code: name} for every living and historical language in ISO 639-3."""
    try:
        import pycountry
    except ImportError:                          # the list is a convenience: without it, typed names
        return {}
    return {lang.alpha_3: getattr(lang, "name", lang.alpha_3) for lang in pycountry.languages}


def name(code: str) -> str:
    """A code's name ("arb" → "Standard Arabic"); anything else (a typed language) as it is."""
    return _all().get(code, code)


def is_code(text: str) -> bool:
    return text in _all()


def label(code: str) -> str:
    """How a language shows on a chip: "Standard Arabic · arb", or a typed name alone."""
    return f"{name(code)} · {code}" if is_code(code) else code


def search(text: str, limit: int = 40) -> list[str]:
    """Codes whose name or code matches (codes and names starting with it first, then containing it;
    the widely spoken languages before the rest)."""
    t = nfc(text).strip().lower()
    langs = _all()
    rank = {c: i for i, c in enumerate(TOP)}
    if not t:
        return [c for c in TOP if c in langs][:limit]
    hits = []
    for code, nm in langs.items():
        n = nm.lower()
        if code == t:
            score = 0
        elif n.startswith(t) or code.startswith(t):
            score = 1
        elif t in n:
            score = 2
        else:
            continue
        hits.append((score, rank.get(code, 999), n, code))
    hits.sort()
    return [h[3] for h in hits[:limit]]
