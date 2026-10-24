# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Build the ɛλicit test database: a little Italian, with Danish as the second gloss language.

    python samples/make_elicit_test.py [folder with the recordings]

writes samples/Elicit test/ITA-STD_Elicit_Test.xml, its Soundfiles and its Images. The
recordings are Josh's (acqua, casa, libro, sole, torta, il_gatto_dorme, le_mie_due_torte_grandi,
as WAVs, 20 October 2026); without a folder, the ones already in the database's folder are used
again. The pictures are simple placeholders drawn here.

It is for trying out ɛλicit (IDEAS.md idea 19): each lemma's Comment says how to ask for it,
so that one request covers every kind of card:

  new, citation token, with a picture         gatto 'cat' (D035)
  new, citation token, no picture             pane 'bread' (J114)
  new, tagged token, with a picture           gatti 'cats' (D035, Plural)
  new, tagged token, no picture               torte 'cakes' (J114b, Plural)
  new, a verb with an animated GIF            dormire 'to sleep' (V094)
  new, tagged token with no Translation       libri (K220, Plural): the warning
  rerecord of a token                         acqua 'water' (L062)
  rerecord, speaker without audio sharing     sole 'sun' (L002, SP2): the ethics warning
  rerecord of an utterance                    il gatto dorme (U001)
  new, an utterance without a recording       il cane mangia (U003)

and a few lemmas not to ask for (cane, casa, mangiare, grande, due, and U002).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from lemmatrix import layout, storage, workspace  # noqa: E402
from lemmatrix import wordlists as wl  # noqa: E402
from lemmatrix.defaults import new_database  # noqa: E402
from lemmatrix.model import Person  # noqa: E402

FOLDER = HERE / "Elicit test"
NAME = "ITA-STD_Elicit_Test"
DATE = "2026-10-20"

ASK_NEW = "ɛλicit test: ask for this (new recording)"
ASK_NEW_IMAGE = "ɛλicit test: ask for this (new recording; it has a picture)"
ASK_RE = "ɛλicit test: ask for this (rerecord)"
NOT = "ɛλicit test: not to ask for"

# ref, lemma, gloss en, gloss da, word class, phonemic, comment,
#   [(tags, phonemic, translation en, translation da, recording, speaker, comment)]
LEMMAS = [
    ("D035", "gatto", "cat", "kat", "NOUN", "ˈɡatto", ASK_NEW_IMAGE,
     [(["Plural"], "ˈɡatti", "cats", "katte", "", "", ASK_NEW_IMAGE)]),
    ("D034", "cane", "dog", "hund", "NOUN", "ˈkane", NOT, []),
    ("L062", "acqua", "water", "vand", "NOUN", "ˈakkwa", ASK_RE, []),
    ("J114", "pane", "bread", "brød", "NOUN", "ˈpane", ASK_NEW, []),
    ("J114b", "torta", "cake", "kage", "NOUN", "ˈtorta", NOT,
     [(["Plural"], "ˈtorte", "cakes", "kager", "", "", ASK_NEW)]),
    ("K002", "casa", "house", "hus", "NOUN", "ˈkaza", NOT,
     [(["Plural"], "ˈkaze", "houses", "huse", "", "", NOT)]),
    ("K220", "libro", "book", "bog", "NOUN", "ˈlibro", NOT,
     [(["Plural"], "ˈlibri", "", "", "", "", "ɛλicit test: ask for this (new recording; no Translation, "
                                             "so Lemmatrix warns)")]),
    ("L002", "sole", "sun", "sol", "NOUN", "ˈsole",
     "ɛλicit test: ask for this (rerecord; SP2 hasn't agreed to audio sharing, so Lemmatrix warns)", []),
    ("V094", "dormire", "to sleep", "at sove", "VERB", "dorˈmire", ASK_NEW_IMAGE + " (an animated GIF)", []),
    ("V158", "mangiare", "to eat", "at spise", "VERB", "manˈdʒare", NOT, []),
    ("P001", "grande", "big", "stor", "ADJECTIVE", "ˈɡrande", NOT, []),
    ("Q002", "due", "two", "to", "QUANT", "ˈdue", NOT, []),
]
# The citation tokens recorded, and by whom.
RECORDED = {"L062": ("acqua", "SP1"), "J114b": ("torta", "SP1"), "K002": ("casa", "SP1"),
            "K220": ("libro", "SP1"), "L002": ("sole", "SP2")}

# ref, label, phonemic, translation en, da, recording, comment
UTTERANCES = [
    ("U001", "the cat is sleeping", "il ˈɡatto ˈdɔrme", "the cat is sleeping", "katten sover",
     "il_gatto_dorme", ASK_RE),
    ("U002", "my two big cakes", "le ˈmie ˈdue ˈtorte ˈɡrandi", "my two big cakes", "mine to store kager",
     "le_mie_due_torte_grandi", NOT),
    ("U003", "the dog is eating", "il ˈkane ˈmandʒa", "the dog is eating", "hunden spiser", "", ASK_NEW),
]


# ---------------------------------------------------------------------------------------------
# Placeholder pictures (600 px, so the request shrinks them to 500)
# ---------------------------------------------------------------------------------------------

def _cat(d, cx, cy, r, colour, asleep=False):
    ear = r * 0.75
    for side in (-1, 1):
        d.polygon([(cx + side * r * 0.85, cy - r * 0.35), (cx + side * r * 0.25, cy - r * 0.85),
                   (cx + side * r * 0.95, cy - r * 0.35 - ear)], fill=colour)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour)
    eye = r * 0.16
    for side in (-1, 1):
        ex = cx + side * r * 0.38
        if asleep:
            d.arc([ex - eye * 1.6, cy - eye * 2, ex + eye * 1.6, cy + eye * 0.6], 20, 160, fill="white",
                  width=max(3, int(r * 0.06)))
        else:
            d.ellipse([ex - eye, cy - eye * 1.4, ex + eye, cy + eye * 0.6], fill="white")
            d.ellipse([ex - eye * 0.45, cy - eye, ex + eye * 0.45, cy + eye * 0.4], fill="#222222")
    d.polygon([(cx - r * 0.1, cy + r * 0.2), (cx + r * 0.1, cy + r * 0.2), (cx, cy + r * 0.32)], fill="#f2a3b3")
    for side in (-1, 1):
        for k in (-1, 0, 1):
            d.line([(cx + side * r * 0.25, cy + r * 0.32 + k * r * 0.08),
                    (cx + side * r * 1.15, cy + r * 0.25 + k * r * 0.2)], fill="white", width=max(2, int(r * 0.03)))


def make_images(folder: Path):
    from PIL import Image, ImageDraw, ImageFont
    folder.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (600, 600), "#e8f4f3")
    _cat(ImageDraw.Draw(im), 300, 330, 180, "#e08a2c")
    im.save(folder / "D035.png")
    im = Image.new("RGB", (600, 600), "#e8f4f3")
    d = ImageDraw.Draw(im)
    _cat(d, 170, 360, 120, "#e08a2c")
    _cat(d, 430, 330, 135, "#6b6b6b")
    im.save(folder / "D035_PL.png")
    try:
        font = ImageFont.load_default(size=70)
    except TypeError:
        font = ImageFont.load_default()
    frames = []
    for k in range(4):
        fr = Image.new("RGB", (600, 600), "#1f3550")
        d = ImageDraw.Draw(fr)
        d.ellipse([440, 40, 540, 140], fill="#f4e7a1")
        d.ellipse([470, 30, 560, 120], fill="#1f3550")              # a crescent moon
        _cat(d, 250, 380, 150, "#e08a2c", asleep=True)
        for j in range(k):
            d.text((380 + j * 55, 240 - j * 60), "z" if j < 2 else "Z", fill="white", font=font)
        frames.append(fr)
    frames[0].save(folder / "V094.gif", save_all=True, append_images=frames[1:], duration=500, loop=0)


# ---------------------------------------------------------------------------------------------

def build(recordings: Path | None = None):
    db = new_database()
    md, s = db.metadata, db.settings
    md.language_code, md.language_name = "ITA", "Italian"
    md.variety_code, md.variety_name = "STD", "Standard Italian"
    md.name = "Elicit Test"
    md.description = ("A small invented Italian database (Danish as the second gloss language) for trying out "
                      "ɛλicit. Built by samples/make_elicit_test.py; the recordings are Josh Smolders'.")
    md.participants = [Person("SP1", "Speaker 1", identifiable=True, audio_sharing=True),
                       Person("SP2", "Speaker 2", identifiable=False, audio_sharing=False)]
    md.researchers = [Person.researcher("RS1", "Researcher 1", email="researcher@example.org")]
    s.gloss_languages = ["en", "da"]
    s.primary_gloss = "en"
    s.auto_update_names = True

    old = FOLDER
    sources: dict[str, Path] = {}                 # "acqua", "il_gatto_dorme" -> the WAV
    if recordings is not None:
        for p in Path(recordings).glob("*.wav"):
            head, _, rest = p.stem.partition("-")  # uploads come as "97aa7559-acqua.wav"
            sources[(rest if len(head) == 8 and rest else p.stem).lower()] = p
    else:                                         # rebuilding: the recordings already in its folder
        before = storage.load(old / f"{NAME}.xml")
        for e in before.entries:
            if e.tokens and e.tokens[0].file:
                sources[before.lemma(e)] = storage.sound_folder(before) / e.tokens[0].file
        recs = {ref: rec for ref, *_, rec, _ in UTTERANCES}
        for u in before.utterances:
            if u.token.file and recs.get(u.ref):
                sources[recs[u.ref]] = storage.utterance_folder(before) / u.token.file
    tmp = HERE / "Elicit test.building"
    shutil.rmtree(tmp, ignore_errors=True)
    db.path = str(tmp / f"{NAME}.xml")
    layout.create_layout(db.path)

    def source(word: str) -> Path:
        hit = sources.get(word.lower())
        if hit is None or not hit.exists():
            raise SystemExit(f"No recording for {word!r}: give the folder with Josh's WAVs.")
        return hit

    gloss = s.entry_field("gloss")
    comment = s.entry_field("comment")
    tr = s.token_field("translation")
    for ref, lemma, en, da, cls, phon, note, others in LEMMAS:
        e = db.new_entry(ref, lemma, en, cls)
        e.set(gloss.name, da, "da")
        e.set(comment.name, note)
        cit = e.tokens[0]
        cit.set("Phonemic", phon)
        cit.set(tr.name, en, "en")
        cit.set(tr.name, da, "da")
        if ref in RECORDED:
            word, speaker = RECORDED[ref]
            cit.speaker, cit.collected = speaker, DATE
            cit.file = db.expected_filename(e, cit)
            shutil.copy2(source(word), storage.sound_folder(db) / cit.file)
        for tags, p, t_en, t_da, _, _, t_note in others:
            t = db.new_token(e, tags)
            t.set("Phonemic", p)
            if t_en:
                t.set(tr.name, t_en, "en")
            if t_da:
                t.set(tr.name, t_da, "da")
            t.set("Comment", t_note)
            e.tokens.append(t)
        db.entries.append(e)
    # The references are the EACW's (Josh, 23 October: the first build numbered them D001, D002… in
    # order, so Link to wordlists gave *cat* the numbers of *animal*); cake (J114b, under bread) and
    # book (K220, after the list's last K) are the database's own. Linked as Tools → Link to
    # wordlists… would, and in the list's order.
    wl.link_as_eacw(db)
    for ref, label, phon, en, da, rec, note in UTTERANCES:
        u = db.new_utterance(ref, label)
        t = u.token
        t.set("Phonemic", phon)
        t.set(tr.name, en, "en")
        t.set(tr.name, da, "da")
        t.set("Comment", note)
        if rec:
            t.speaker, t.collected = "SP1", DATE
            t.file = db.expected_filename(u, t)
            shutil.copy2(source(rec), storage.utterance_folder(db) / t.file)
        db.utterances.append(u)
    make_images(layout.images_folder(db.path))
    storage.save(db, db.path, backup=False)
    workspace.save(workspace.Workspace(), db)                 # beside it, so opening a copy doesn't warn
    shutil.rmtree(tmp / "Backups", ignore_errors=True)
    for sub in ("Exports", "Documentation"):      # empty folders aren't kept by git; Lemmatrix makes them
        shutil.rmtree(tmp / sub, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    tmp.rename(old)
    db.path = str(old / f"{NAME}.xml")
    return db


def main():
    rec = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    db = build(rec)
    n = sum(1 for _, t in db.all_tokens() if t.file)
    print(f"Wrote {db.path}: {len(db.entries)} lemmas, {len(db.utterances)} utterances, {n} recordings.")


if __name__ == "__main__":
    main()
