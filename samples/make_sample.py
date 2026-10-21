# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""Build the sample database: an invented language, with short synthetic recordings.

    python samples/make_sample.py        ->  samples/Sample.xml and samples/Soundfiles/

The language (LXX, variety VXX) is made up for trying out Lemmatrix: it is not a real language,
and any resemblance to one is coincidental. The database uses the program's defaults (fields,
tags, lists, people and places); only the frames' carrier sentences are filled in.

Phonology
  Consonants  p pʼ pʰ b ɓ t tʼ tʰ t̪ t̪ʰ t̪ʼ d̪ d ɗ c cʰ cʼ ɟ k kʼ kʰ g ʔ β s z ʃ t͡s d͡z n m ŋ ɲ l r w j ɥ
  Vowels      a i ɪ u ʊ e ɛ o ɔ ʌ ə, and long aa ii ɪɪ uu ʊʊ ee ɛɛ oo ɔɔ ʌʌ
  Tones       v́ H, v̄ M, v̀ L, v̂ HL, v̌ LH, ꜜ downstep (Phonemic only); Pitch: H 5, M 3, L 1,
              a downstepped H 4. A long vowel's tone is marked on its first half (áa);
              a contour on a long vowel is split between the halves (áà).
  Syllables   CVN CVVN CV CVV CVCV CVVCV CVNCV CVVNCV CVCVCV CVNCVCV; a nasal before a
              consonant shares its place.
  Phonetic    no tones, length as ː; velars are labialised before round vowels (kʷ) and
              palatalised before high front ones (kʲ); a word-final vowel after a nasal is
              nasalised (ṽ), a vowel after an aspirate breathy (v̤), after a glottal consonant
              creaky (v̰); never two of these on one syllable.

Morphology
  Pronouns  1SG mɪ̀ɪ, 2SG jɔ̀ɔ, 3SG wɛ́ɛ, 1PL tʌ́ʌn, 2PL βʊ̄ʊ, 3PL kɪ́ɪn; their first syllable is
            the prefix for subjects (verbs) and possessors (nouns): mɪ̀-dʌ́ʌm 'my goat'.
  Nouns     PL -à after a consonant (class I), -nà after a vowel (class II).
  Verbs     PRS unmarked, PST -ɛ̀ (class I) / -rɛ̀ (class II), FUT dɔ̄- after the subject;
            IMP -á / -rá, 2PL with βʊ̄-; NEG imperative: kʌ̀ before the verb.
            A full noun object (NP.O) follows the verb.
  Frames    Frame 1: ___ ɗɪ̄ɪ 'it is a ___'; Frame 2: mɪ̀ɲɔ̄ɔ ___ 'I see the ___'.
"""

from __future__ import annotations

import shutil
import sys
import unicodedata
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from lemmatrix import audio, matrix as mx, pitch, storage, workspace  # noqa: E402
from lemmatrix.defaults import new_database  # noqa: E402

RATE = 11025
SPEAKER, DATE = "SP1", "2026-10-20"

# ---------------------------------------------------------------------------------------------
# The lexicon (phonemic, with tones)
# ---------------------------------------------------------------------------------------------

NOUNS = [   # reference letter, gloss, form, the object it is (for verbs' NP objects)
    ("A", "head", "tʊ́ʊm"), ("A", "eye", "ɲɪ̀n"), ("A", "mouth", "ɓʌ̄ŋ"), ("A", "tooth", "cɔ́kà"),
    ("A", "hand", "dàmbɛ́"), ("A", "foot", "pʰúrʊ̀"),
    ("B", "person", "ʔɪ́ɪn"), ("B", "man", "gàanà"), ("B", "woman", "dɛ̄nzɪ́"), ("B", "child", "tʰʊ̀ŋ"),
    ("C", "mother", "mʌ̀ʌ"), ("C", "father", "βɔ́ɔ"),
    ("D", "goat", "dʌ́ʌm"), ("D", "lion", "ŋɔ́ɔɲ"), ("D", "sheep", "pɛ́ɛ"), ("D", "cow", "ŋʊ̀ʊŋ"),
    ("D", "dog", "ɟɪ̀ŋ"), ("D", "elephant", "ʃɔ̀mbɔ́rɔ̀"),
    ("E", "duck", "kʊ́kʊ̀"), ("E", "eagle", "ɗɪ́ꜜɗɪ́"), ("E", "ostrich", "ɓʊ̀ʊndʊ́"),
    ("F", "fish", "ɲɛ́ɛm"), ("F", "catfish", "kʰʌ̀nt̪ʌ́"),
    ("G", "snake", "t͡sɔ́ɔ"), ("G", "crocodile", "ŋàŋkáꜜrá"), ("G", "frog", "ɓɛ̀ɓɛ̄"),
    ("H", "fly", "ʃɪ̀ɪn"), ("H", "bee", "dɔ́ŋ"), ("H", "termite", "zʌ̀mbʌ̀"),
    ("I", "god", "jʊ́ʊ"),
    ("J", "tree", "jɛ́ɛn"), ("J", "leaf", "pàlàtá"), ("J", "food", "kʊ́ndɛ̀"), ("J", "water", "ɲʊ́ʊ̀"),
    ("J", "meat", "rɪ̀ɪŋ"), ("J", "sorghum", "d͡zàmá"), ("J", "milk", "cʰʌ̀ʌ"), ("J", "honey", "ʃáꜜsá"),
    ("K", "house", "kʊ̀ʊn"), ("K", "pot", "dɪ́ɪɗɪ̀"), ("K", "spear", "bɛ̄ɛŋ"), ("K", "rope", "lʊ́ŋgʊ̀"),
    ("K", "knife", "t͡sɪ̀mpɪ́"), ("K", "basket", "ʃɛ̀nzɛ̀"),
    ("L", "sun", "cɔ̀ɔŋ"), ("L", "moon", "pʼɛ̄ɛ"), ("L", "rain", "ɓʊ́ʊ"), ("L", "fire", "d̪ɔ́ɔɲ"),
    ("L", "stone", "kɔ̀ɔlɔ́"), ("L", "river", "wɔ̄ɔn"),
]

VERBS = [   # gloss, root, past tense of the gloss, its object (a noun's gloss)
    ("eat", "tʌ̄ŋ", "ate", "food"), ("drink", "mʊ̀ʊn", "drank", "water"), ("see", "ɲɔ̄ɔ", "saw", "lion"),
    ("hit", "pʼɪ́", "hit", "dog"), ("take", "jàn", "took", "knife"), ("carry", "ɓɛ́ɛŋ", "carried", "pot"),
    ("cook", "t͡sʊ̀mbà", "cooked", "meat"), ("build", "ɟɛ̀ɛ", "built", "house"),
    ("cut", "kʼɔ́tà", "cut", "rope"), ("kill", "rɛ̀ɛm", "killed", "snake"),
    ("hold", "gʊ́ʊ", "held", "spear"), ("call", "lɔ̄ɔlɛ̀", "called", "child"),
    ("hear", "pʰɪ̀ɪ", "heard", "rain"), ("know", "d͡zɪ́ɪn", "knew", "person"),
    ("catch", "ŋɪ́mbɪ̀", "caught", "fish"), ("throw", "βàdá", "threw", "stone"),
    ("plant", "sɪ̀ndʊ́", "planted", "sorghum"), ("find", "ɥɛ̂n", "found", "goat"),
    ("wash", "t̪ɔ̀ɔŋkɔ́", "washed", "hand"), ("sell", "cʼàlàmá", "sold", "milk"),
]

PRONOUNS = [   # tag stem, form, English (subject, object, possessive)
    ("1SG", "mɪ̀ɪ", "I", "my"), ("2SG", "jɔ̀ɔ", "you (sg)", "your (sg)"), ("3SG", "wɛ́ɛ", "he", "his"),
    ("1PL", "tʌ́ʌn", "we", "our"), ("2PL", "βʊ̄ʊ", "you (pl)", "your (pl)"), ("3PL", "kɪ́ɪn", "they", "their"),
]

NUMBERS = [("one", "ʔɔ́n", "one"), ("two", "ɓɪ̀ɪ", "two"), ("three", "sàdɛ́", "three"),
           ("four", "ŋʊ̂ŋ", "four"), ("five", "t̪ʰʌ́ʌn", "five"), ("six", "t̪ʰʌ́ʌn ʔɔ́n", "five one"),
           ("seven", "t̪ʰʌ́ʌn ɓɪ̀ɪ", "five two"), ("eight", "t̪ʰʌ́ʌn sàdɛ́", "five three"),
           ("nine", "t̪ʰʌ́ʌn ŋʊ̂ŋ", "five four"), ("ten", "ɟɔ̌", "ten")]
MASS = {"water", "meat", "milk", "honey", "food", "sorghum", "fire", "rain"}

ADJECTIVES = [("big", "dʊ́ŋ"), ("small", "cɪ̀cɪ̀"), ("good", "ɲɛ̄ɛ"), ("bad", "kʼʌ̀ʌn"), ("red", "mɔ̄ɔɲ"),
              ("white", "pɛ̀pɛ́"), ("black", "d̪ʊ̀ʊ"), ("long", "lʌ̀ʌŋgʌ́"), ("short", "kʊ́tʊ́"),
              ("hot", "ʃʊ́ʊ")]

ADVERBS = [("today", "ɲàmá"), ("here", "dɛ̀ɛ́")]

COPULA, SEE_1SG = "ɗɪ̄ɪ", "mɪ̀ɲɔ̄ɔ"
FRAMES = {"Frame 1": "___ ɗɪ̄ɪ ‘it is a ___’", "Frame 2": "mɪ̀ɲɔ̄ɔ ___ ‘I see the ___’"}

# Lemmas recorded in full (every token); the others have a recording of the citation form only.
RECORDED_IN_FULL = {"goat", "house", "eat", "drink"}

# ---------------------------------------------------------------------------------------------
# Phonology: segments, Phonetic forms, Pitch
# ---------------------------------------------------------------------------------------------

VOWELS = set("aiɪuʊeɛoɔʌə")
ROUND, HIGH_FRONT = set("uʊoɔ"), set("iɪ")
CONSONANTS = sorted("p pʼ pʰ b ɓ t tʼ tʰ t̪ t̪ʰ t̪ʼ d̪ d ɗ c cʰ cʼ ɟ k kʼ kʰ g ʔ β s z ʃ t͡s d͡z n m ŋ ɲ l r w j ɥ"
                    .split(), key=len, reverse=True)
NASALS = set("mnŋɲ")
VELARS = {"k", "kʼ", "kʰ", "g"}
GLOTTAL = {"ʔ", "ɓ", "ɗ", "pʼ", "tʼ", "t̪ʼ", "cʼ", "kʼ"}
HOMORGANIC = {"m": set("pbɓβ") | {"pʼ", "pʰ"}, "n": {"t", "tʼ", "tʰ", "d", "ɗ", "s", "z", "l", "r", "t̪", "t̪ʰ",
                                                    "t̪ʼ", "d̪", "t͡s", "d͡z"},
              "ɲ": {"c", "cʰ", "cʼ", "ɟ", "ʃ"}, "ŋ": {"k", "kʼ", "kʰ", "g"}}
TONES = {"́": "H", "̀": "L", "̄": "M", "̂": "HL", "̌": "LH"}
LEVEL = {"H": 5, "M": 3, "L": 1}
DOWNSTEP = "ꜜ"
BREATHY, CREAKY, NASAL = "̤", "̰", "̃"


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def segments(word: str) -> list[tuple[str, str]]:
    """A phonemic word as (segment, tones) pairs; tones only on vowels (H, L, M, HL, LH, or '!H'
    for a downstepped H)."""
    s = unicodedata.normalize("NFD", word)
    out, i, down = [], 0, False
    while i < len(s):
        if s[i] == DOWNSTEP:
            down, i = True, i + 1
            continue
        if s[i] in VOWELS:
            v, i = s[i], i + 1
            tone = ""
            while i < len(s) and unicodedata.combining(s[i]):
                tone = TONES.get(s[i], tone)
                i += 1
            out.append((v, ("!" if down and "H" in tone else "") + tone))
            continue
        c = next((c for c in CONSONANTS if s.startswith(unicodedata.normalize("NFD", c), i)), None)
        if c is None:
            raise ValueError(f"not in the inventory: {s[i]!r} in {word}")
        out.append((c, ""))
        i += len(unicodedata.normalize("NFD", c))
    return out


def check(word: str):
    """Raise if a word breaks the phonotactics (inventory, syllable shapes, homorganic NC)."""
    segs = [s for s, _ in segments(word)]
    shape = "".join("V" if s in VOWELS else "C" for s in segs)
    allowed = {"CVC", "CVVC", "CV", "CVV", "CVCV", "CVVCV", "CVCCV", "CVVCCV", "CVCVCV", "CVCCVCV"}
    assert shape in allowed, (word, shape)
    for a, b in zip(segs, segs[1:]):
        if a in NASALS and b not in VOWELS:
            assert b in HOMORGANIC[a], (word, a, b)
    if shape.endswith("C"):
        assert segs[-1] in NASALS, word


def phonetic_word(word: str) -> str:
    segs = segments(word)
    out = []
    i = 0
    while i < len(segs):
        seg, _ = segs[i]
        if seg not in VOWELS:
            nxt = segs[i + 1][0] if i + 1 < len(segs) else ""
            if seg in VELARS and nxt in ROUND | HIGH_FRONT:
                mark = "ʷ" if nxt in ROUND else "ʲ"
                seg = seg[0] + mark + seg[1:]
            out.append(seg)
            i += 1
            continue
        long = i + 1 < len(segs) and segs[i + 1][0] == seg
        onset = segs[i - 1][0] if i > 0 and segs[i - 1][0] not in VOWELS else ""
        last = i + (2 if long else 1) >= len(segs)
        mark = ""
        if "ʰ" in onset:
            mark = BREATHY
        elif onset in GLOTTAL:
            mark = CREAKY
        elif last and onset in NASALS:
            mark = NASAL
        out.append(seg + mark + ("ː" if long else ""))
        i += 2 if long else 1
    return "".join(out)


def phonetic(form: str) -> str:
    return nfc(" ".join(phonetic_word(w) for w in form.split()))


def tone_points(t: str) -> list[int]:
    """Pitch points of one vowel's tone: H 5, M 3, L 1; a downstepped H ('!H') 4."""
    down = t.startswith("!")
    t = t.lstrip("!")
    pts = [LEVEL[x] for x in ([t] if t in LEVEL else [t[0], t[1]])]
    if down and t.startswith("H"):
        pts[0] -= 1
    return pts


def pitch_of(form: str) -> str:
    """The Pitch field from the tones: one syllable per vowel nucleus."""
    sylls = []
    for word in form.split():
        segs = segments(word)
        i = 0
        while i < len(segs):
            seg, tone = segs[i]
            if seg not in VOWELS:
                i += 1
                continue
            tones = [tone]
            if i + 1 < len(segs) and segs[i + 1][0] == seg:
                tones.append(segs[i + 1][1])
                i += 1
            i += 1

            if len(tones) == 2:                      # a long vowel: a long step between its halves
                a, b = tone_points(tones[0]), tone_points(tones[1] or tones[0].lstrip("!")[-1:])
                sylls.append(f"{a[0]}:{b[-1]}")
            else:
                sylls.append("".join(map(str, tone_points(tone))))
    return pitch.normalise(" ".join(sylls))


def tone_melody(form: str) -> str:
    """H, L, LH or HL from the tones (None if there's an M or another melody)."""
    seq = []
    for word in form.split():
        for seg, t in segments(word):
            for x in (t.lstrip("!") if t not in ("HL", "LH") else list(t)):
                if x and (not seq or seq[-1] != x):
                    seq.append(x)
    melody = "".join(seq)
    return melody if melody in ("H", "L", "LH", "HL") else None


# ---------------------------------------------------------------------------------------------
# Morphology
# ---------------------------------------------------------------------------------------------

def ends_in_vowel(form: str) -> bool:
    return segments(form.split()[-1])[-1][0] in VOWELS


def prefix(person: str) -> str:
    """The pronoun's first syllable (CV, with its tone)."""
    form = dict((p, f) for p, f, *_ in PRONOUNS)[person]
    segs = unicodedata.normalize("NFD", form)
    cut = next(i for i, ch in enumerate(segs) if ch in VOWELS)
    end = cut + 1
    while end < len(segs) and unicodedata.combining(segs[end]):
        end += 1
    return nfc(segs[:end])


def suffix(root: str, after_c: str, after_v: str) -> str:
    return root + (after_v if ends_in_vowel(root) else after_c)


def inflection_class(root: str) -> str:
    return "II" if ends_in_vowel(root) else "I"


# ---------------------------------------------------------------------------------------------
# Building the database
# ---------------------------------------------------------------------------------------------

def hum(pitch_text: str) -> np.ndarray:
    """A short hum following the pitch, so playback has something to play."""
    out = []
    step = 0.09
    for item in pitch.parse(pitch_text) or pitch.parse("33"):
        if item == pitch.PAUSE:
            out.append(np.zeros(int(RATE * 0.1)))
            continue
        times = np.concatenate([[0], np.cumsum(item.steps)]) * step
        n = max(1, int(RATE * times[-1]))
        levels = np.interp(np.linspace(0, times[-1], n), times, item.points)
        freq = 110 * 2 ** ((levels - 1) / 8)
        phase = 2 * np.pi * np.cumsum(freq) / RATE
        env = np.minimum(1, np.minimum(np.arange(n), n - np.arange(n)) / (RATE * 0.015))
        out.append(0.3 * env * (np.sin(phase) + 0.3 * np.sin(2 * phase)))
        out.append(np.zeros(int(RATE * 0.025)))
    return np.concatenate(out)


class Builder:
    def __init__(self):
        self.db = db = new_database()
        md = db.metadata
        md.language_code, md.language_name = "LXX", "Sample language"
        md.variety_code, md.variety_name = "VXX", "Sample variety"
        md.name = "Sample"
        md.description = ("Invented sample data for trying out Lemmatrix: not a real language, and any "
                          "resemblance to one is coincidental. Built by samples/make_sample.py.")
        for name, carrier in FRAMES.items():
            db.settings.tags.tag(name).description = carrier
        self.folder = HERE / "Soundfiles" / "Tokens"
        db.path = str(HERE / "Sample.xml")
        self.nouns = {g: f for _, g, f in NOUNS}

    def token(self, e, tags, form, morphemes, translation, record):
        t = self.db.new_token(e, tags, speaker=SPEAKER, date=DATE) if tags else e.tokens[0]
        t.set("Phonetic", phonetic(form))
        t.set("Phonemic", nfc(form))
        t.set("Pitch", pitch_of(form))
        t.set("Morphemes", morphemes)
        t.set("Translation", translation, "en")
        if tags:
            e.tokens.append(t)
        if record:
            t.file = self.db.expected_filename(e, t)
            audio.write_wav(self.folder / t.file, hum(t.get("Pitch")), RATE, 16, artist=t.speaker, date=t.collected)
        return t

    def entry(self, ref, form, gloss, wc, classes=True):
        for w in form.split():
            check(w)
        e = self.db.new_entry(ref, nfc(form), gloss, wc, speaker=SPEAKER, date=DATE)
        if classes:
            if (m := tone_melody(form)):
                e.set("ToneClass", m)
        self.db.entries.append(e)
        return e

    def noun(self, letter, gloss, form):
        e = self.entry(self.db.suggest_reference(letter), form, gloss, "NOUN")
        e.set("InflectionClass", inflection_class(form))
        rec = gloss in RECORDED_IN_FULL
        pl = suffix(form, "à", "nà")
        pl_m = f"{gloss}-PL"
        plural = gloss if gloss in ("sheep", "fish") else ("people" if gloss == "person" else
                                                          {"man": "men", "woman": "women", "child": "children",
                                                           "tooth": "teeth", "foot": "feet", "knife": "knives",
                                                           "leaf": "leaves", "catfish": "catfish"}.get(gloss, gloss + "s"))
        self.token(e, [], form, gloss, gloss, True)
        self.token(e, ["Plural"], pl, pl_m, plural, rec)
        art = "" if gloss in MASS else ("an " if gloss[0] in "aeiou" else "a ")
        self.token(e, ["Frame 1"], f"{form} {COPULA}", f"{gloss} COP", f"it is {art}{gloss}", rec)
        self.token(e, ["Frame 2"], f"{SEE_1SG} {form}", f"1SG.A-see {gloss}", f"I see the {gloss}", rec)
        for number, stem, m_stem, eng in (("Singular", form, gloss, gloss), ("Plural", pl, pl_m, plural)):
            for person, _, _, poss in PRONOUNS:
                self.token(e, [number, f"{person}.POSS"], prefix(person) + stem, f"{person}.POSS-{m_stem}",
                           f"{poss} {eng}", rec)

    def verb(self, gloss, root, past, obj):
        e = self.entry(self.db.suggest_reference("V"), root, gloss, "VERB")
        e.set("InflectionClass", inflection_class(root))
        rec = gloss in RECORDED_IN_FULL
        self.token(e, [], root, gloss, f"to {gloss}", True)
        imp = suffix(root, "á", "rá")
        for neg in (False, True):
            for person, pre, eng in (("2SG", "", "(sg)"), ("2PL", prefix("2PL"), "(pl)")):
                form = ("kʌ̀ " if neg else "") + pre + imp
                morph = ("NEG " if neg else "") + (f"{person}.A-" if pre else "") + f"{gloss}-IMP"
                tr = (f"don't {gloss}! {eng}" if neg else f"{gloss}! {eng}")
                self.token(e, ["Imperative", f"{person}.A"] + (["Negative"] if neg else []), form, morph, tr, rec)
        o = self.nouns[obj]
        for person, _, subj, _ in [p for p in PRONOUNS if p[0] in ("3SG", "3PL")]:
            pre = prefix(person)
            s3 = "s" if person == "3SG" else ""
            third = gloss
            if person == "3SG":
                third = (gloss[:-1] + "ies" if gloss.endswith("y") else
                         gloss + ("es" if gloss.endswith(("sh", "ch", "ss")) else s3))
            for tense, form, morph, tr in (
                    ("Present", pre + root, f"{person}.A-{gloss}", f"{subj} {third} the {obj}"),
                    ("Past", pre + suffix(root, "ɛ̀", "rɛ̀"), f"{person}.A-{gloss}-PST", f"{subj} {past} the {obj}"),
                    ("Future", pre + "dɔ̄" + root, f"{person}.A-FUT-{gloss}", f"{subj} will {gloss} the {obj}")):
                self.token(e, [tense, f"{person}.A", "NP.O"], f"{form} {o}", f"{morph} {obj}", tr, rec)

    def simple(self, letter, gloss, form, wc, ref=None, morphemes=None):
        e = self.entry(ref or self.db.suggest_reference(letter), form, gloss, wc, classes=False)
        self.token(e, [], form, morphemes or gloss, gloss, True)
        return e

    def matrices(self):
        s = self.db.settings

        def S(*tags):
            return mx.Spec(frozenset(tags))
        poss = [f"{p}.POSS" for p, *_ in PRONOUNS]
        s.matrices = [
            mx.MatrixConfig("Nouns: citation, plural and frames", mx.LEMMA_TAG,
                            x=[mx.Spec.citation(), S("Plural"), S("Frame 1"), S("Frame 2")]),
            mx.MatrixConfig("Nouns: number and possession", mx.TAG_TAG,
                            y=[S("Singular"), S("Plural")], x=[S(p) for p in poss]),
            mx.MatrixConfig("Verbs: imperatives", mx.LEMMA_TAG,
                            x=[mx.Spec.citation(), S("Imperative", "2SG.A"), S("Imperative", "2PL.A"),
                               S("Imperative", "2SG.A", "Negative"), S("Imperative", "2PL.A", "Negative")]),
            mx.MatrixConfig("Verbs: person and tense", mx.TAG_TAG,
                            y=[S("3SG.A", "NP.O"), S("3PL.A", "NP.O")],
                            x=[S("Present"), S("Past"), S("Future")]),
        ]

    def build(self):
        shutil.rmtree(HERE / "Soundfiles", ignore_errors=True)
        for letter, gloss, form in NOUNS:
            self.noun(letter, gloss, form)
        for v in VERBS:
            self.verb(*v)
        for i, (person, form, eng, _) in enumerate(PRONOUNS):
            self.simple("R", eng, form, "PRONOUN", ref=f"R{i + 1:03d}")
        for i, (gloss, form, morphemes) in enumerate(NUMBERS):
            self.simple("Q", gloss, form, "QUANT", ref=f"Q{i + 1:03d}", morphemes=morphemes)
        for gloss, form in ADJECTIVES:
            self.simple("P", gloss, form, "ADJECTIVE")
        for gloss, form in ADVERBS:
            self.simple("N", gloss, form, "ADVERB")
        self.matrices()
        storage.save(self.db, HERE / "Sample.xml", backup=False)
        workspace.save(workspace.Workspace(), self.db)        # the saved matrices are in its workspace
        shutil.rmtree(HERE / "Backups", ignore_errors=True)
        return self.db


def main():
    db = Builder().build()
    tokens = sum(len(e.tokens) for e in db.entries)
    print(f"Wrote {HERE / 'Sample.xml'}: {len(db.entries)} lemmas, {tokens} tokens, "
          f"{len(list((HERE / 'Soundfiles' / 'Tokens').glob('*.wav')))} recordings.")


if __name__ == "__main__":
    main()
