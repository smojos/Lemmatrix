# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Batch tokens from the lemma list (IDEAS.md idea 64, designed and built 24 October 2026).

Several lemmas selected (or every lemma shown), tags picked with Ctrl+click, and one empty token
for each lemma and each combination: e.g. Singular and Plural × Frame 1 and Frame 2 for ten
lemmas makes forty tokens, ready to send out in an ɛλicit request or to collect live.

- **Planned, not collected** (Josh, 24 October): the new tokens have no speaker and no date. The
  token dialogue shows the Current Session's as their defaults, written when the token is
  recorded or something is typed in it.
- **Already there:** a combination a lemma already has (another token has, or would have, that
  soundfile name, as the token dialogue's several-tokens counts it, section 5.6) is skipped; no
  Example tag is offered.
- **Each lemma's own defaults** are added as on any new token (Singular, Nominative…), so a
  noun's batch tokens and a verb's differ only where their word classes do. Singular has no
  file-name code (it is Number's default), so Singular + Frame 1 is named …_F1.
- **Predicted translations** (section 5.9), where there is one, when asked.
- **Audit** (Tools → Audits → Give every lemma its citation token…): the lemmas with no citation
  token (no token without tags) get an empty one, first in the lemma.

Plain Python with no Qt; the windows' part is ui/batch_tokens.py.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from .model import Database, Entry, Token, Utterance
from . import predict

LIMIT = 500            # more tokens than this at once: asked first


def combinations(db: Database, picked) -> list[list[str]]:
    """One tag list per combination of the picked tags: tags of the same lowest group multiply
    (Singular, Plural × Frame 1, Frame 2 → four), in tag order. No tags: no combinations."""
    ts = db.settings.tags
    groups: dict[int, list[str]] = {}
    order: list[int] = []
    for name in ts.sort(list(picked)):
        hit = ts.find(name)
        key = id(hit[1]) if hit else id(name)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(name)
    lists = [groups[k] for k in order]
    if not lists:
        return []
    return [ts.sort(list(c)) for c in itertools.product(*lists)]


def group_names(db: Database, picked) -> list[list[str]]:
    """The picked tags by group, in tag order: [[Singular, Plural], [Frame 1, Frame 2]]
    (the matrices take the first group as rows, the rest as columns)."""
    ts = db.settings.tags
    out: list[list[str]] = []
    seen: dict[int, list[str]] = {}
    for name in ts.sort(list(picked)):
        hit = ts.find(name)
        key = id(hit[1]) if hit else id(name)
        if key not in seen:
            seen[key] = []
            out.append(seen[key])
        seen[key].append(name)
    return out


@dataclass
class Plan:
    """What a batch would do: the tokens to make, by lemma, and the combinations skipped."""
    made: list[tuple[Entry, Token]] = field(default_factory=list)
    skipped: list[tuple[Entry, list[str]]] = field(default_factory=list)
    unusual: set = field(default_factory=set)          # ids of the lemmas with tags not usual for them
    predicted: int = 0                                 # tokens given a predicted translation
    untranslated: int = 0                              # tokens left with no translation

    @property
    def lemmas(self) -> list[Entry]:
        out, seen = [], set()
        for e, _ in self.made:
            if id(e) not in seen:
                seen.add(id(e))
                out.append(e)
        return out


def plan(db: Database, entries, combos, translate: bool = True,
         predictor: predict.Predictor | None = None) -> Plan:
    """The tokens a batch would make for these lemmas (each a list of tags without its lemma's
    defaults); nothing is changed."""
    p = Plan()
    fname = predict.translation_field(db) if translate else ""
    if fname and predictor is None:
        predictor = predict.Predictor()
    if fname:
        predictor.refresh(db)
    taken = {t.file.lower() for e in db.entries for t in e.tokens if t.file}
    for e in entries:
        if isinstance(e, Utterance):
            continue
        names = {db.expected_filename(e, t).lower() for t in e.tokens}
        for combo in combos:
            if not combo:
                continue
            t = db.new_token(e, combo, defaults=True)     # no speaker, no date: not collected yet
            name = db.expected_filename(e, t).lower()
            if name in names or name in taken:
                p.skipped.append((e, list(combo)))
                continue
            names.add(name)
            if db.unusual_tags(e, t.tags):
                p.unusual.add(e.id)
            if fname:
                sug = predictor.suggest(db, e, t.tags, refresh=False)
                if sug is not None:
                    t.set(fname, sug.text, predict.LANG)
                    p.predicted += 1
                else:
                    p.untranslated += 1
            p.made.append((e, t))
    return p


def pairs(p: Plan) -> list[tuple[Entry, Entry]]:
    """(lemma, its changed copy) for Document.apply_changes: one undo step for the whole batch."""
    out = []
    for e in p.lemmas:
        c = e.copy()
        for en, t in p.made:
            if en is e:
                c.add_token(t)
        out.append((e, c))
    return out


def label(p: Plan) -> str:
    n, m = len(p.made), len(p.lemmas)
    return f"Add {n} token{'s' * (n != 1)} to {m} lemma{'s' * (m != 1)}"


# ---- the audit: every lemma its citation token ------------------------------------------
def missing_citation(db: Database) -> list[Entry]:
    """The lemmas with no citation token (no token without tags), e.g. from a conversion."""
    return [e for e in db.entries if not any(t.is_citation for t in e.tokens)]


def citation_pairs(db: Database) -> list[tuple[Entry, Entry]]:
    """(lemma, its copy with an empty citation token first): no speaker, no date."""
    out = []
    for e in missing_citation(db):
        c = e.copy()
        c.add_token(Token())
        out.append((e, c))
    return out


# ---- the matrices offered afterwards ---------------------------------------------------
def matrices(db: Database, picked):
    """The Lemma/Tag and Tag/Tag matrices of a batch's tags (Josh, 24 October: rows the first
    group, columns the rest). Lemma/Tag: one Exact column per combination. Tag/Tag: the first
    group's tags down the side, the other groups' combinations across; None with one group."""
    from . import matrix as mx
    groups = group_names(db, picked)
    combos = combinations(db, picked)
    lt = mx.MatrixConfig(kind=mx.LEMMA_TAG, x=[mx.Spec(frozenset(c), mx.EXACT) for c in combos])
    if len(groups) < 2:
        return lt, None
    rest = [ts for ts in itertools.product(*groups[1:])]
    tt = mx.MatrixConfig(kind=mx.TAG_TAG, y=[mx.Spec(frozenset([n]), mx.EXACT) for n in groups[0]],
                         x=[mx.Spec(frozenset(c), mx.EXACT) for c in rest])
    return lt, tt


def same_saved(db: Database, cfg):
    """A saved matrix of the same kind with the same lines (in the same order), if there is one."""
    if cfg is None:
        return None
    return next((m for m in db.settings.matrices if m.kind == cfg.kind and list(m.x) == list(cfg.x)
                 and list(m.y) == list(cfg.y)), None)
