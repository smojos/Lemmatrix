# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Build a large invented test database: 300 lemmas with their tagged forms.

    python samples/make_test_database.py            ->  samples/Test-300.xml

The forms are random but consistent (each lemma has a stem, and its forms are
built from it with invented affixes), so paradigms look plausible. There are no
soundfiles. The same seed always gives the same database.

What "every logical combination" means here, per word class:
  NOUN       Citation; Number (SG, PL) x Case (none + the seven cases);
             SG in each frame f1-f4; SG before H / before L.
  VERB (tr)  Citation; every A subject x every object;
             3SG.A + 3SG.O through Tense x Aspect, each also Negative;
             3SG.A + 3SG.O Imperative, Passive, Antipassive and Causative.
  VERB (in)  Citation; every S subject;
             3SG.S through Tense x Aspect, each also Negative; Imperative.
  others     Citation; each frame f1-f4; utterance-initial and -final.
Group defaults (Simple, Indicative, Affirmative, isolation) are added
automatically, as the program does for new tokens.
The full cross-product of every group would be thousands of forms per verb,
which is neither logical for a language nor useful to test with.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from lemmatrix import pitch, storage, workspace  # noqa: E402
from lemmatrix.defaults import new_database  # noqa: E402
from lemmatrix.model import Participant  # noqa: E402

SEED = 300
rng = random.Random(SEED)

# ---------------------------------------------------------------- glosses
NOUNS = {
    "A": "head eye ear nose mouth tooth tongue neck arm hand finger leg foot knee belly back "
         "heart liver blood bone skin hair",
    "B": "man woman child elder chief stranger friend guest twin orphan",
    "C": "mother father brother sister grandmother uncle aunt husband wife in-law",
    "D": "goat cow sheep dog lion hyena elephant giraffe monkey rabbit rat donkey",
    "E": "chicken duck eagle ostrich crow dove owl",
    "F": "catfish tilapia eel",
    "G": "snake crocodile lizard frog tortoise",
    "H": "ant bee housefly mosquito termite louse scorpion spider locust",
    "I": "spirit god sickness fever wound medicine festival",
    "J": "tree grass leaf root seed sorghum maize bean milk beer water salt honey meat oil",
    "K": "house door rope knife spear bow arrow pot basket bed drum hoe boat bag cloth wall money gift",
    "L": "sun moon star sky cloud rain wind fire smoke ash stone sand river mountain earth field well",
    "M": "word name song story lie",
    "N": "day night morning evening year place side",
    "O": "thing work market road village price path fence",
}
TRANSITIVE = ("eat drink see hear know hit cut kill bite carry take give hold wash cook burn "
              "build dig throw pull push tie open close sell buy call help teach find lose "
              "leave break count grind pour plant chase greet answer hide send fold "
              "draw_milk herd flay weave sew beat lick suck squeeze scratch lift plait sweep sharpen borrow pay").split()
INTRANSITIVE = ("sleep run walk sit stand die laugh cry swim fly dance sing come go return "
                "fall jump wake sweat shout play cough rest grow rot shine float "
                "hunger drizzle sneeze wait limp shiver kneel yawn hurry").split()
ADJECTIVES = "big small long short good bad new old hot cold white black red heavy wet dry sweet bitter full sharp".split()
ADVERBS = "here there now today yesterday tomorrow quickly slowly again together".split()
PRONOUNS = [("R1SG", "I"), ("R2SG", "you (sg)"), ("R3SG", "he or she"), ("R1PLIN", "we (incl)"),
            ("R1PLEX", "we (excl)"), ("R2PL", "you (pl)"), ("R3PL", "they"), ("R1SGPOSS", "my"),
            ("R2SGPOSS", "your"), ("R3SGPOSS", "his or her")]
QUANTIFIERS = [("Q001", "one"), ("Q002", "two"), ("Q003", "three"), ("Q004", "four"),
               ("Q005", "five"), ("Q010", "ten")]               # Q + the number itself
OTHER_QUANTIFIERS = "many few all some".split()                 # non-numerical quantifiers are in O

# ----------------------------------------------------- invented phonology
# The sample language's inventory (see make_sample.py); forms are random, not real words.
CONS = ("p pʼ pʰ b ɓ t tʼ tʰ t̪ t̪ʰ t̪ʼ d̪ d ɗ c cʰ cʼ ɟ k kʼ kʰ g ʔ β s z ʃ t͡s d͡z n m ŋ ɲ l r w j ɥ").split()
FINAL = list("nmŋɲ")
VOWELS = list("aiɪuʊeɛoɔʌə")


def syllable(final: bool) -> str:
    c = rng.choice(CONS)
    v = rng.choice(VOWELS)
    if rng.random() < 0.35:
        v *= 2
    tail = rng.choice(FINAL) if (final and rng.random() < 0.7) else ""
    return c + v + tail


def stem() -> tuple[str, int]:
    n = rng.choices([1, 2, 3], [5, 4, 1])[0]
    return "".join(syllable(i == n - 1) for i in range(n)), n


def tone(n: int) -> list[str]:
    """Random pitch in the colon notation: 11, 1:1, 14, 1:4, 4:42, 42:1 …"""
    out = []
    for _ in range(n):
        r = rng.random()
        a, b = rng.sample("12345", 2)
        if r < 0.45:
            out.append(a * 2)                       # short level
        elif r < 0.6:
            out.append(f"{a}:{a}")                  # long level
        elif r < 0.78:
            out.append(a + b)                       # quick contour
        elif r < 0.88:
            out.append(f"{a}:{b}")                  # long contour
        elif r < 0.95:
            out.append(f"{a}:{a}{b}")               # long level, then a quick change
        else:
            c = rng.choice([x for x in "12345" if x != b])
            out.append(a + b + c)                   # rise-fall or fall-rise
    return out


def phonemic(phonetic: str) -> str:
    """A rough 'phonemic' version: drop aspiration and length marks."""
    return phonetic.replace("ʰ", "").replace("ː", "")


# Affixes (invented): each adds one syllable with its own tone.
CASES = {"Nominative": ("", ""), "Accusative": ("tɔ", "1"), "Ergative": ("rɛ", "5"),
         "Absolutive": ("", ""), "Genitive": ("sʊʊ", "3"), "Pertensive": ("jɛ", "1"), "Locative": ("pɛ", "2")}
CASE_GLOSS = {"Nominative": "{n}", "Accusative": "{n} (object)", "Ergative": "{n} (agent)",
              "Absolutive": "{n} (absolutive)", "Genitive": "of the {n}", "Pertensive": "the {n} of", "Locative": "at the {n}"}
SUBJ = {"1SG": ("mɪ", "1", "I"), "2SG": ("jɔ", "1", "you"), "3SG": ("wɛ", "5", "he"),
        "1PL": ("tʌ", "5", "we"), "2PL": ("βʊ", "3", "you all"), "3PL": ("kɪ", "5", "they")}
OBJ = {"1SG": ("ŋɪ", "1", "me"), "2SG": ("ŋɔ", "3", "you"), "3SG": ("ŋɛ", "5", "him"),
       "1PL": ("ŋʌ", "1", "us"), "2PL": ("ŋʊ", "3", "you all"), "3PL": ("ŋə", "5", "them")}
TENSE = {"Past": ("rɛ", "1", "past"), "Present": ("", "", "present"), "Future": ("dɔ", "3", "future")}
ASPECT = {"Perfective": ("", "", "pfv"), "Imperfective": ("sɪ", "3", "ipfv")}
STEMS = {"Passive": ("ʊʊ", "2"), "Antipassive": ("ɪ", "1"), "Causative": ("cɪ", "4")}


def third_person(gloss: str) -> str:
    """eat -> eats, carry -> carries, draw milk -> draws milk."""
    verb, _, rest = gloss.partition(" ")
    if verb.endswith(("s", "sh", "ch", "x", "o")):
        verb += "es"
    elif verb.endswith("y") and verb[-2:-1] not in "aeiou":
        verb = verb[:-1] + "ies"
    else:
        verb += "s"
    return f"{verb} {rest}".strip()


def plural(s: str) -> str:
    return s + ("nà" if s[-1] in VOWELS else "à")


def join(*parts):
    words = [p for p in parts if p[0]]
    return " ".join(w for w, _ in words), pitch.normalise(" ".join(t for _, t in words))


def main(out: Path):
    db = new_database()
    from lemmatrix.defaults import easter_egg_locations   # Ucluelet and Pade: kept here (Josh)
    db.metadata.locations = easter_egg_locations()
    md = db.metadata
    md.language_code, md.language_name = "TST", "Testish"
    md.variety_code, md.variety_name = "CEN", "Central"
    md.description = ("Invented test data: 300 random lemmas with their tagged forms. "
                      "Generated by samples/make_test_database.py.")
    md.participants = [Participant("SP1", "Speaker 1"), Participant("SP2", "Speaker 2"),
                       Participant("XYZ", "Third speaker")]
    db.settings.gloss_languages = ["en"]
    db.settings.pitch_low, db.settings.pitch_high = 1, 5
    dates = [f"2026-10-{d:02d}" for d in range(1, 17)]
    used_forms = set()

    def fresh_stem():
        while True:
            s, n = stem()
            if s not in used_forms:
                used_forms.add(s)
                return s, n

    def add(entry, tags, phon, pit, tr, speaker=None, date=None):
        t = db.new_token(entry, list(tags), speaker or rng.choice(["SP1", "SP1", "SP2"]),
                         date or rng.choice(dates))
        r = rng.random()
        if r < 0.04:                    # a few unfinished tokens, as in real data
            phon = ""
        t.set("Phonetic", phon)
        if r > 0.08:
            t.set("Phonemic", phonemic(phon))
        if r < 0.94:
            t.set("Pitch", pit)
        t.set("Translation", tr, "en")
        entry.tokens.append(t)
        return t

    def entry(ref, lemma, gloss, wc, tone_class=""):
        e = db.new_entry(ref, lemma, gloss, wc)
        e.tokens.clear()
        if tone_class:
            e.set("ToneClass", tone_class)
        db.entries.append(e)
        return e

    # ---- nouns -----------------------------------------------------------
    for letter, words in NOUNS.items():
        for gloss in words.split():
            s, n = fresh_stem()
            tn = tone(n)
            e = entry(db.suggest_reference(letter), s, gloss, "NOUN", rng.choice(["LH", "HL", "L", "H"]))
            if rng.random() < 0.15:
                e.set("InflectionClass", rng.choice(["I", "II", "III"]))
            add(e, [], s, " ".join(tn), gloss)
            pl = plural(s)
            tn_pl = tone(max(1, n))
            for number, form, tns, nglo in (("Singular", s, tn, gloss), ("Plural", pl, tn_pl, gloss + "s")):
                add(e, [number], form, " ".join(tns), nglo)
                for case, (suf, st) in CASES.items():
                    phon, pit = join((form, " ".join(tns)), (suf, st))
                    add(e, [number, case], phon, pit, CASE_GLOSS[case].format(n=nglo))
            for f, frame in zip(("f1", "f2", "f3", "f4"),
                                ("I saw the {}", "the {} is here", "{} and a stone", "give me the {}")):
                phon, pit = join(("a ŋɔ", "1 3"), (s, " ".join(tn))) if f == "f1" else \
                    join((s, " ".join(tn)), (rng.choice(["tʊ", "ɟɛ", "rɛ"]), rng.choice(["11", "33", "55"])))
                add(e, ["Singular", f], phon, pit, frame.format(gloss))
            add(e, ["Singular", "before H"], s, " ".join(tn[:-1] + [tn[-1][0] + "4"]), gloss + " (before H)")
            add(e, ["Singular", "before L"], s, " ".join(tn), gloss + " (before L)")

    # ---- verbs -----------------------------------------------------------
    def verb(gloss, transitive):
        s, n = fresh_stem()
        tn = " ".join(tone(n))
        e = entry(db.suggest_reference("V"), s, gloss, "VERB", rng.choice(["H", "L", "HL"]))
        add(e, [], s, tn, gloss)
        role = "A" if transitive else "S"
        for p, (sp, st, sg) in SUBJ.items():
            if transitive:
                for o, (op, ot, og) in OBJ.items():
                    phon, pit = join((sp, st), (s, tn), (op, ot))
                    og = {"1SG": "myself", "2SG": "yourself", "1PL": "ourselves",
                          "2PL": "yourselves"}.get(o, og) if o == p else og
                    vg = third_person(gloss) if p == "3SG" else gloss
                    add(e, [f"{p}.A", f"{o}.O"], phon, pit, f"{sg} {vg} {og}")
            else:
                phon, pit = join((sp, st), (s, tn))
                add(e, [f"{p}.S"], phon, pit, f"{sg} {third_person(gloss) if p == '3SG' else gloss}")
        subj = ["3SG." + role] + (["3SG.O"] if transitive else [])
        obj = (OBJ["3SG"],) if transitive else ()
        for tense, (tp, tt, tg) in TENSE.items():
            for aspect, (ap, at, ag) in ASPECT.items():
                for neg in (False, True):
                    parts = [SUBJ["3SG"][:2], (tp, tt), (s, tn), (ap, at)] + [o[:2] for o in obj]
                    if neg:
                        parts.append(("kʌ", "1"))
                    phon, pit = join(*parts)
                    tr = f"he {third_person(gloss)}{' it' if transitive else ''} ({tg}, {ag}{', neg' if neg else ''})"
                    add(e, subj + [tense, aspect] + (["Negative"] if neg else []), phon, pit, tr)
        imp_tags = (["2SG.A", "3SG.O"] if transitive else ["2SG.S"]) + ["Imperative"]
        phon, pit = join((s, tn), *[o[:2] for o in obj])
        add(e, imp_tags, phon, pit, f"{gloss}{' it' if transitive else ''}!")
        if transitive:
            for st_name, (sp2, st2) in STEMS.items():
                phon, pit = join(SUBJ["3SG"][:2], (s + sp2, tn + " " + st2), OBJ["3SG"][:2])
                add(e, ["3SG.A", "3SG.O", st_name], phon, pit, f"he {third_person(gloss)} it ({st_name.lower()})")

    for g in TRANSITIVE:
        verb(g.replace("_", " "), True)      # "draw milk" tests a gloss with a space
    for g in INTRANSITIVE:
        verb(g, False)

    # ---- the other word classes ------------------------------------------
    def simple(ref, gloss, wc):
        s, n = fresh_stem()
        tn = " ".join(tone(n))
        e = entry(ref, s, gloss, wc)
        add(e, [], s, tn, gloss)
        for f in ("f1", "f2", "f3", "f4"):
            phon, pit = join((s, tn), (rng.choice(["tʊ", "ɟɛ", "rɛ", "mə"]), rng.choice(["11", "33", "55"])))
            add(e, [f], phon, pit, f"{gloss} (frame {f[1]})")
        add(e, ["utterance-initial"], s, tn, gloss + " (initial)")
        add(e, ["utterance-final"], s, tn, gloss + " (final)")

    for g in ADJECTIVES:
        simple(db.suggest_reference("P"), g, "ADJECTIVE")
    for g in ADVERBS:
        simple(db.suggest_reference("N"), g, "ADVERB")
    for ref, g in PRONOUNS:
        simple(ref, g, "PRONOUN")
    for ref, g in QUANTIFIERS:
        simple(ref, g, "QUANT")
    for g in OTHER_QUANTIFIERS:
        simple(db.suggest_reference("O"), g, "QUANT")

    n_entries = len(db.entries)
    assert n_entries == 300, n_entries
    db.path = str(out)
    for f in db.settings.entry_fields:          # closed fields list the values in use
        if f.closed and f.role != "word-class":
            for v in sorted({e.get(f.name) for e in db.entries if e.get(f.name)}):
                f.add_value(v)
    storage.save(db, out, backup=False)
    workspace.save(workspace.Workspace(), db)
    n_tokens = sum(len(e.tokens) for e in db.entries)
    print(f"Wrote {out} with {n_entries} lemmas and {n_tokens} tokens.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "Test-300.xml")
