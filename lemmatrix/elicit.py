# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders
"""ɛλicit (IDEAS.md idea 19, stage 1, 20 October 2026): remote elicitation through a web page.

A **request** is a list of cards for one speaker. Lemmatrix writes it as a zip (request.json,
the images and the recordings to repeat), which the researcher sends with a link to the web
page (docs/elicit/). The speaker works through the cards on a phone or computer; the page
saves the recordings on the device and, at the end, gives them back as a zip (response.json
and the WAVs), which the speaker sends to the researcher. **Receive ɛλicitation** reads that
zip, and the review dialogue puts the approved recordings into the database.

Stage 1 has no cloud: the zips travel by hand (WhatsApp, Signal, email). Each request keeps a
folder of its own in the main folder's Elicit folder:

    Elicit/2026-10-20_SP1_3f9c2a/
    ├─ request.json        what was asked (the cards, with the ids of their tokens and lemmas)
    ├─ Elicit_request_SP1_2026-10-20.zip   the file to send
    ├─ received/           the speaker's zip, unpacked (response.json and the recordings)
    └─ review.json         what the researcher decided, card by card

No Qt in this module.
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import os
import re
import shutil
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import elicit_prompts, filenames, layout, storage
from .model import Database, Entry, Token, is_utterance, nfc

FORMAT = "lemmatrix-elicit-request"
RESPONSE_FORMAT = "lemmatrix-elicit-response"
VERSION = 1
ELICIT = "Elicit"
EXPIRY_DAYS = 14
SIZE_WARNING = 50 * 1024 * 1024          # bytes: warn before sending a bigger request
IMAGE_MAX = 500                          # px: longer sides are shrunk
WEB_PAGE = "https://smojos.github.io/Lemmatrix/elicit/"
# A guess at a recording's size on the phone, for the size warning: 16-bit mono at 48 kHz.
BYTES_PER_SECOND = 96_000
SECONDS = {"token": 6, "utterance": 9}

NEW, RERECORD, NEW_UTTERANCE = "new", "rerecord", "new-utterance"
APPROVED, REJECTED = "approved", "rejected"


class ElicitError(Exception):
    pass


def elicit_folder(db_path) -> Path:
    return layout.main_folder(db_path) / ELICIT


# --------------------------------------------------------------------------
# What can be asked for
# --------------------------------------------------------------------------

@dataclass
class Item:
    """One thing to ask for: a token of a lemma or an utterance (kind NEW or RERECORD), or a new
    utterance typed in the request dialogue (NEW_UTTERANCE, with its translations)."""
    kind: str
    entry: Entry | None = None
    token: Token | None = None
    translations: dict[str, str] = field(default_factory=dict)   # a new utterance's, by language


def item_label(db: Database, it: Item) -> str:
    """"D001 gatto · Plural", "U001 il gatto dorme", or the new utterance's translation."""
    if it.kind == NEW_UTTERANCE:
        return "New utterance: " + (it.translations.get(db.settings.primary_gloss) or
                                    next(iter(it.translations.values()), ""))
    e, t = it.entry, it.token
    if is_utterance(e):
        return f"{e.ref} {_form(db, t) or e.label}".strip()
    tags = db.settings.tags.display(t.tags)
    return f"{e.ref} {db.lemma(e)} · {tags}".strip()


def _form(db: Database, t: Token) -> str:
    for role in ("phonemic", "phonetic"):
        f = db.settings.token_field(role)
        if f and t.get(f.name):
            return t.get(f.name)
    return ""


def _translation_field(db: Database):
    return db.settings.token_field("translation")


def card_texts(db: Database, it: Item, languages) -> tuple[str, dict[str, str]]:
    """What a card shows the speaker: ("gloss", {lang: gloss}) for a citation token,
    ("translation", {lang: text}) for any other token or an utterance, ("none", {}) for a
    rerecord (the original recording is the prompt)."""
    if it.kind == RERECORD:
        return "none", {}
    if it.kind == NEW_UTTERANCE:
        return "translation", {l: it.translations[l] for l in languages if it.translations.get(l)}
    e, t = it.entry, it.token
    if not is_utterance(e) and t.is_citation:
        g = db.settings.entry_field("gloss")
        return "gloss", {l: e.get(g.name, l) for l in languages if g and e.get(g.name, l)}
    f = _translation_field(db)
    texts = {l: t.get(f.name, l) for l in languages if f and t.get(f.name, l)}
    return "translation", texts


def missing_translation(db: Database, it: Item) -> bool:
    """A token (not a citation token) or utterance asked for anew with no English Translation:
    the card would have nothing to show."""
    if it.kind != NEW:
        return False
    kind, texts = card_texts(db, it, [db.settings.primary_gloss])
    return kind == "translation" and not texts


def recording_path(db: Database, e: Entry, t: Token) -> Path | None:
    if not t.file or not db.path:
        return None
    p = storage.folder_for(db, e) / t.file
    return p if p.exists() else None


def ethics_problem(db: Database, it: Item) -> str:
    """For a rerecord: why sending its recording to another speaker may not be allowed ("" if fine)."""
    if it.kind != RERECORD:
        return ""
    code = it.token.speaker
    if not code:
        return "its recording has no speaker"
    p = db.metadata.participant(code)
    if p is None:
        return f"its speaker {code} isn't in the participants list"
    if not p.audio_sharing:
        return f"its speaker {code} hasn't agreed to audio sharing"
    return ""


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------

@dataclass
class Card:
    n: int
    kind: str                         # new, rerecord, new-utterance
    target: str = ""                  # token or utterance ("" for a new utterance)
    entry: str = ""                   # the lemma's or utterance's id
    token: str = ""                   # the token's id
    ref: str = ""
    label: str = ""                   # for the researcher (the review), not shown on the page
    show: str = "none"                # gloss, translation or none
    texts: dict = field(default_factory=dict)        # language -> what the card shows
    translations: dict = field(default_factory=dict)  # a new utterance's
    image: str = ""                   # in the zip, e.g. media/03.jpg
    original: str = ""                # in the zip, the recording to repeat
    file: str = ""                    # the recording's name in the response zip
    repeat: bool = False              # "Please say it 2 or 3 times."
    image_id: str = ""                # through Google Drive: the picture's file id (shared by link)
    original_id: str = ""             # the recording to repeat
    upload: str = ""                  # the recording's upload link (Google's, for one week)


@dataclass
class Request:
    id: str
    created: str
    expires: str
    speaker: dict
    researcher: dict
    database: dict
    languages: list
    language_names: dict
    prompts: dict
    accent: str
    cards: list
    format: str = FORMAT
    version: int = VERSION
    page: str = WEB_PAGE
    transport: str = "file"           # file (a zip sent by hand) or drive (a link; Google Drive)
    audio: str = "wav"                # how the page sends the recordings: wav, or flac (lossless, smaller)
    drive: dict = field(default_factory=dict)   # folder, request (file ids), response, status (upload links), link

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)

    @classmethod
    def from_dict(cls, d: dict) -> "Request":
        if d.get("format") != FORMAT:
            raise ElicitError("This isn't an ɛλicit request.")
        d = dict(d)
        d["cards"] = [Card(**c) for c in d.get("cards", [])]
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def card(self, n: int) -> Card | None:
        return next((c for c in self.cards if c.n == n), None)


def person_dict(p, code: str) -> dict:
    return {"code": code, "name": (p.name if p and p.name else code), "email": (p.email if p else "")}


def person_name(person: dict, lang: str) -> str:
    """The speaker's or researcher's name as the prompts in this language write it."""
    return (person.get("names") or {}).get(lang) or person.get("name", "")


def new_request(db: Database, items, speaker: str, researcher: str, l2: str = "", l2_language_name: str = "",
                repeat: bool = True, accent: str = "#198583", today: _dt.date | None = None,
                audio: str = "flac", l2_names: dict | None = None) -> Request:
    """A request for these items (in order). l2: the second language (a gloss language) or "".
    l2_names: {"speaker": ..., "researcher": ...}, their names as written in the second language
    (blank: the name in the participants or researchers list)."""
    today = today or _dt.date.today()
    md, s = db.metadata, db.settings
    en = s.primary_gloss
    languages = [en] + ([l2] if l2 and l2 != en else [])
    lang_name = md.language_name or md.language_code or "the language"
    names = {en: lang_name}
    if len(languages) > 1:
        names[l2] = l2_language_name.strip() or lang_name
    prompts = {}
    for lang in languages:
        p = elicit_prompts.prompts(lang if lang != en else "en")
        if p:
            prompts[lang] = dict(p)
    if en not in prompts:                         # a primary language other than English: English prompts
        prompts[en] = dict(elicit_prompts.PROMPTS["en"])
    cards = []
    for n, it in enumerate(items, 1):
        show, texts = card_texts(db, it, languages)
        if it.kind == NEW_UTTERANCE:
            c = Card(n, NEW_UTTERANCE, label=item_label(db, it), show=show, texts=texts,
                     translations={k: nfc(v) for k, v in it.translations.items() if v})
            c.file = f"{n:02d}_new_utterance.{audio}"
        else:
            e, t = it.entry, it.token
            c = Card(n, it.kind, "utterance" if is_utterance(e) else "token", e.id, t.id, e.ref,
                     item_label(db, it), show, texts)
            if show == "translation" and not texts and not is_utterance(e):      # the warning was given
                g = s.entry_field("gloss")             # the gloss and the tags that say something
                shown = [n for n in s.tags.sort(t.tags) if not (s.tags.tag(n) and s.tags.tag(n).default)]
                tags = ", ".join(shown)
                c.texts = {l: f"{e.get(g.name, l)} ({tags})" if tags else e.get(g.name, l)
                           for l in languages if g and e.get(g.name, l)}
                c.show = "gloss"
            c.repeat = repeat and not is_utterance(e) and it.kind == NEW
            c.file = f"{n:02d}_{filenames.praat_name(e.ref)}.{audio}"
        cards.append(c)
    rid = uuid.uuid4().hex[:12]
    people = {"speaker": person_dict(md.participant(speaker), speaker),
              "researcher": person_dict(md.researcher(researcher), researcher)}
    for role, name in (l2_names or {}).items():          # "names": {language: name}, for the prompts
        name = nfc((name or "").strip())
        if len(languages) > 1 and role in people and name and name != people[role]["name"]:
            people[role]["names"] = {languages[1]: name}
    return Request(
        id=rid, created=_dt.datetime.now().isoformat(timespec="seconds"),
        expires=(today + _dt.timedelta(days=EXPIRY_DAYS)).isoformat(),
        speaker=people["speaker"], researcher=people["researcher"],
        database={"name": md.name, "language_code": md.language_code, "language_name": md.language_name,
                  "variety_code": md.variety_code, "variety_name": md.variety_name},
        languages=languages, language_names=names, prompts=prompts, accent=accent, cards=cards, audio=audio)


def media_for(db: Database, items) -> dict[int, dict[str, Path]]:
    """card number -> {"image": path, "original": path} of the files a request takes along."""
    out = {}
    for n, it in enumerate(items, 1):
        if it.kind == NEW_UTTERANCE:
            continue
        files = {}
        if it.kind == NEW and not is_utterance(it.entry):
            img = filenames.find_image(db, it.entry, it.token)
            if img is not None:
                files["image"] = img
        if it.kind == RERECORD:
            rec = recording_path(db, it.entry, it.token)
            if rec is not None:
                files["original"] = rec
        if files:
            out[n] = files
    return out


def estimated_size(db: Database, items, audio: str = "flac") -> int:
    """Bytes: the files sent with the request, and a guess at the recordings coming back (FLAC
    about 60% of WAV for speech)."""
    total = 0
    for files in media_for(db, items).values():
        for p in files.values():
            try:
                total += min(p.stat().st_size, 400_000) if p.suffix.lower() in (".jpg", ".jpeg", ".png") \
                    else p.stat().st_size
            except OSError:
                pass
    for it in items:
        kind = "utterance" if (it.kind == NEW_UTTERANCE or is_utterance(it.entry)) else "token"
        total += SECONDS[kind] * BYTES_PER_SECOND * (0.6 if audio == "flac" else 1)
    return int(total)


def shrink_image(src: Path, longest: int = IMAGE_MAX) -> tuple[bytes, str]:
    """The image as bytes, its longer side at most `longest` pixels (animated GIFs keep their
    frames). Returns (bytes, extension). Without Pillow, the file as it is."""
    ext = src.suffix.lower()
    try:
        from PIL import Image, ImageSequence
    except ImportError:
        return src.read_bytes(), ext
    with Image.open(src) as im:
        w, h = im.size
        if max(w, h) <= longest:
            return src.read_bytes(), ext
        scale = longest / max(w, h)
        size = (max(1, round(w * scale)), max(1, round(h * scale)))
        out = io.BytesIO()
        if ext == ".gif":
            frames, durations = [], []
            for frame in ImageSequence.Iterator(im):
                durations.append(frame.info.get("duration", im.info.get("duration", 100)))
                frames.append(frame.convert("RGBA").resize(size, Image.LANCZOS))
            frames[0].save(out, "GIF", save_all=True, append_images=frames[1:], duration=durations,
                           loop=im.info.get("loop", 0), disposal=2)
        elif ext == ".png":
            im.resize(size, Image.LANCZOS).save(out, "PNG")
        else:
            im.convert("RGB").resize(size, Image.LANCZOS).save(out, "JPEG", quality=85)
            ext = ".jpg"
        return out.getvalue(), ext


def request_folder_name(req: Request) -> str:
    return f"{req.created[:10]}_{filenames.praat_name(req.speaker['code'])}_{req.id[:6]}"


def zip_name(req: Request) -> str:
    return f"Elicit_request_{filenames.praat_name(req.speaker['code'])}_{req.created[:10]}.zip"


def _media_blobs(db: Database, req: Request, items) -> list[tuple[str, bytes]]:
    """The pictures (shrunk) and the recordings to repeat, named media/03.jpg, media/07_original.wav,
    with the cards' image and original set to those names."""
    media = media_for(db, items)
    blobs: list[tuple[str, bytes]] = []
    for c in req.cards:
        files = media.get(c.n, {})
        if "image" in files:
            data, ext = shrink_image(files["image"])
            c.image = f"media/{c.n:02d}{ext}"
            blobs.append((c.image, data))
        if "original" in files:
            c.original = f"media/{c.n:02d}_original{files['original'].suffix.lower()}"
            blobs.append((c.original, files["original"].read_bytes()))
    return blobs


def _local_folder(db: Database, req: Request) -> Path:
    if not db.path:
        raise ElicitError("Save the database first.")
    folder = elicit_folder(db.path) / request_folder_name(req)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_request(db: Database, req: Request, items) -> Path:
    """Write the request's folder in Elicit and the zip to send. Returns the zip's path.

    The zip is stored, not compressed (the web page reads it without a library; the recordings
    and pictures hardly compress anyway)."""
    folder = _local_folder(db, req)
    blobs = _media_blobs(db, req, items)
    (folder / "request.json").write_text(req.to_json(), encoding="utf-8")
    target = folder / zip_name(req)
    tmp = target.with_name(target.name + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("request.json", req.to_json().encode("utf-8"))
        for name, data in blobs:
            zf.writestr(name, data)
    os.replace(tmp, target)
    return target


def message_text(req: Request) -> str:
    """The message to paste into WhatsApp, Signal or an email: with a Drive request just the link
    (in the last line, on its own, so phones make it tappable); otherwise with the request's file."""
    by_link = req.transport == "drive"
    key = "message_link" if by_link else "message"
    out = []
    for lang in req.languages:
        values = {"name": person_name(req.speaker, lang), "researcher": person_name(req.researcher, lang),
                  "link": "" if by_link else req.page}
        p = req.prompts.get(lang)
        text = p.get(key) if p else ""
        if text:
            text = text.format(**values).strip()
            if text not in out:
                out.append(text)
    if by_link:
        out.append(req.drive.get("link", ""))
    return "\n\n".join(out)


# --------------------------------------------------------------------------
# Through Google Drive (stage 2)
# --------------------------------------------------------------------------

DRIVE_FOLDER = "ɛλicit"                  # at the top of the researcher's Drive, made by Lemmatrix
DRIVE_EXPIRY_DAYS = 7                    # Google's upload links last a week
RESPONSE, STATUS = "response.json", "status.json"


def publish_drive(db: Database, req: Request, items, drive, api_key: str, progress=None) -> str:
    """Put the request in a folder of its own in the researcher's Drive and make its link.

    The pictures, the recordings to repeat and request.json are uploaded and shared by link (so
    the page can read them with the API key); every card gets an upload link for its recording,
    and the request one for response.json (finished) and one for status.json (turned down). The
    folder itself is not shared. Something going wrong deletes the folder again. Returns the link."""
    req.transport = "drive"
    req.expires = (_dt.date.fromisoformat(req.created[:10]) + _dt.timedelta(days=DRIVE_EXPIRY_DAYS)).isoformat()
    folder_local = _local_folder(db, req)
    blobs = _media_blobs(db, req, items)
    steps = len(blobs) + len(req.cards) + 4
    done = [0]

    def step(text):
        done[0] += 1
        if progress is not None:
            progress(done[0], steps, text)
    top = drive.find_folder(DRIVE_FOLDER) or drive.create_folder(DRIVE_FOLDER)
    folder = drive.create_folder(request_folder_name(req), top)
    try:
        ids = {}
        for name, data in blobs:
            step(f"Uploading {name}")
            mime = {".png": "image/png", ".gif": "image/gif", ".wav": "audio/wav"}.get(
                Path(name).suffix.lower(), "image/jpeg")
            fid = drive.upload(Path(name).name, data, mime, folder)
            drive.share_by_link(fid)
            ids[name] = fid
        for c in req.cards:
            step(f"Making the upload link for card {c.n}")
            c.image_id = ids.get(c.image, "")
            c.original_id = ids.get(c.original, "")
            c.upload = drive.upload_link(c.file, "audio/flac" if c.file.endswith(".flac") else "audio/wav", folder)
        step("Making the links for the end")
        req.drive = {"folder": folder, "response": drive.upload_link(RESPONSE, "application/json", folder),
                     "status": drive.upload_link(STATUS, "application/json", folder)}
        step("Uploading the request")
        rid = drive.upload("request.json", req.to_json().encode("utf-8"), "application/json", folder)
        drive.share_by_link(rid)
        req.drive["request"] = rid
        req.drive["link"] = f"{req.page}#d={rid}&k={api_key}"
        step("Done")
    except BaseException:
        try:
            drive.delete(folder)
        except Exception:                         # noqa: BLE001 (the first problem is the one to report)
            pass
        raise
    (folder_local / "request.json").write_text(req.to_json(), encoding="utf-8")
    return req.drive["link"]


@dataclass
class DriveState:
    """What a Drive request's folder holds now."""
    finished: bool = False
    turned_down: str = ""                 # status.json's reason (not around, no agreement, wrong language)
    uploaded: int = 0                     # recordings uploaded so far
    files: dict = field(default_factory=dict)   # name -> file id
    gone: bool = False                    # the folder isn't there any more

    def summary(self, req: Request) -> str:
        if self.gone:
            return "its folder in Google Drive is gone"
        if self.turned_down:
            return f"turned down on the phone ({self.turned_down})"
        if self.finished:
            return f"finished: {self.uploaded} recording{'s' if self.uploaded != 1 else ''}"
        return f"{self.uploaded} of {len(req.cards)} recorded so far"


def drive_state(drive, st: Stored) -> DriveState:
    folder = st.request.drive.get("folder", "")
    out = DriveState()
    try:
        files = drive.list_folder(folder)
    except Exception as exc:                      # noqa: BLE001
        if str(exc) == "not found":
            out.gone = True
            return out
        raise
    out.files = {f["name"]: f["id"] for f in files}
    names = {c.file for c in st.request.cards}
    out.uploaded = sum(1 for n in out.files if n in names)
    out.finished = RESPONSE in out.files
    if STATUS in out.files:
        try:
            out.turned_down = json.loads(drive.download(out.files[STATUS]).decode("utf-8")).get("reason", "") \
                or "no reason given"
        except (ValueError, UnicodeError):
            out.turned_down = "no reason given"
    return out


def outstanding_drive(db: Database) -> list[Stored]:
    """Drive requests not yet received (their folder is still in Drive)."""
    return [st for st in stored_requests(db.path)
            if st.request.transport == "drive" and st.response is None and not st.request.drive.get("closed")]


def close_drive(drive, st: Stored, note: str = ""):
    """Delete the request's folder in Drive (destroyed means destroyed) and note it locally."""
    folder = st.request.drive.get("folder", "")
    if folder:
        drive.delete(folder)
    st.request.drive["closed"] = note or _dt.date.today().isoformat()
    (st.folder / "request.json").write_text(st.request.to_json(), encoding="utf-8")


def receive_drive(db: Database, st: Stored, drive, state: DriveState | None = None, progress=None) -> Stored:
    """Download what came back to Drive into the request's received/ folder, then delete the folder
    in Drive. Unfinished (the speaker stopped), what is there is taken and the rest marked not
    reached. Raises ElicitError or the drive's errors; nothing is deleted then."""
    state = state or drive_state(drive, st)
    if state.gone:
        raise ElicitError("This request's folder is no longer in Google Drive.")
    if state.finished:
        data = json.loads(drive.download(state.files[RESPONSE]).decode("utf-8"))
    else:
        data = {"format": RESPONSE_FORMAT, "version": VERSION, "request": st.request.id,
                "speaker": st.request.speaker["code"], "finished": "",
                "cards": [{"n": c.n, "status": "recorded", "file": c.file} for c in st.request.cards
                          if c.file in state.files]}
    if data.get("request") != st.request.id:
        raise ElicitError("The answer in Google Drive belongs to another request.")
    tmp = st.folder / "received.part"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        cards = [a for a in data.get("cards", []) if a.get("status") == "recorded" and a.get("file")]
        for k, a in enumerate(cards, 1):
            f = a["file"]
            if not _SAFE.match(f) or f.startswith("."):
                raise ElicitError(f"A recording has a name that can't be used: {f}")
            if f not in state.files:
                a["status"] = "missing"
                continue
            if progress is not None:
                progress(k, len(cards), f)
            (tmp / f).write_bytes(drive.download(state.files[f]))
        _wav_from_flac(tmp, data)
        (tmp / "response.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    if st.received.exists():
        shutil.rmtree(st.received, ignore_errors=True)
    tmp.rename(st.received)
    close_drive(drive, st, "received " + _dt.date.today().isoformat())
    return load_stored(st.folder)


# --------------------------------------------------------------------------
# Requests made, and their responses
# --------------------------------------------------------------------------

@dataclass
class Stored:
    """A request in the Elicit folder, with whatever came back and what was decided."""
    folder: Path
    request: Request
    response: dict | None = None
    review: dict = field(default_factory=dict)   # card number (str) -> {"decision": …, "applied": …}

    @property
    def received(self) -> Path:
        return self.folder / "received"

    def answer(self, n: int) -> dict | None:
        if not self.response:
            return None
        return next((a for a in self.response.get("cards", []) if a.get("n") == n), None)

    def recording(self, n: int) -> Path | None:
        a = self.answer(n)
        if not a or a.get("status") != "recorded" or not a.get("file"):
            return None
        p = self.received / a["file"]
        return p if p.exists() else None

    def save_review(self):
        (self.folder / "review.json").write_text(json.dumps(self.review, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")


def load_stored(folder: Path) -> Stored | None:
    try:
        req = Request.from_dict(json.loads((folder / "request.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, ElicitError):
        return None
    st = Stored(folder, req)
    try:
        st.response = json.loads((folder / "received" / "response.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st.response = None
    try:
        st.review = json.loads((folder / "review.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st.review = {}
    return st


def stored_requests(db_path) -> list[Stored]:
    folder = elicit_folder(db_path) if db_path else None
    if folder is None or not folder.is_dir():
        return []
    out = []
    for sub in sorted(folder.iterdir()):
        if sub.is_dir() and (sub / "request.json").exists():
            st = load_stored(sub)
            if st is not None:
                out.append(st)
    return out


def applied_in(db: Database, card: Card, entry: dict) -> bool:
    """Whether an approved card's recording is (still) in the database: undoing the review, or
    closing without saving, takes it out again, and then the card is waiting once more."""
    applied = (entry or {}).get("applied") or {}

    def same_file(item, t) -> bool:               # the name, and the size noted (a rerecord keeps the name)
        if t.file != applied.get("file"):
            return False
        size = applied.get("size")
        if size is None or not db.path:
            return True
        try:
            return (storage.folder_for(db, item) / t.file).stat().st_size == size
        except OSError:
            return False
    if card.kind == NEW_UTTERANCE:
        u = db.utterance_by_id(applied.get("utterance", ""))
        return u is not None and same_file(u, u.token)
    item = db.item_by_id(card.entry)
    if item is None:
        return True                               # gone from the database: nothing left to do
    t = next((t for t in item.tokens if t.id == card.token), None)
    return t is None or same_file(item, t)


def waiting(db: Database, st: Stored) -> list[Card]:
    """The cards with a recording that hasn't been decided on (or was approved and is no longer
    in the database)."""
    out = []
    for c in st.request.cards:
        if st.recording(c.n) is None:
            continue
        r = st.review.get(str(c.n))
        if r is None or (r.get("decision") == APPROVED and not applied_in(db, c, r)):
            out.append(c)
    return out


def waiting_reviews(db: Database) -> list[tuple[Stored, int]]:
    """Requests with recordings waiting for review, and how many each."""
    out = []
    for st in stored_requests(db.path):
        n = len(waiting(db, st))
        if n:
            out.append((st, n))
    return out


def read_response_zip(path) -> tuple[dict, zipfile.ZipFile]:
    try:
        zf = zipfile.ZipFile(path)
        data = json.loads(zf.read("response.json").decode("utf-8"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise ElicitError("This isn't a file of ɛλicit recordings (there's no response.json in it).") from exc
    if data.get("format") != RESPONSE_FORMAT:
        raise ElicitError("This isn't a file of ɛλicit recordings.")
    return data, zf


_SAFE = re.compile(r"^[\w.\-]+$")


def _wav_from_flac(tmp: Path, data: dict):
    """The FLAC recordings in a received folder become WAVs (Lemmatrix keeps WAVs), with the
    speaker and the day in their metadata; response.json is changed to match."""
    from . import audio
    for a in data.get("cards", []):
        f = a.get("file", "")
        if a.get("status") == "recorded" and f.lower().endswith(".flac") and (tmp / f).exists():
            wav = Path(f).with_suffix(".wav").name
            try:
                audio.flac_to_wav(tmp / f, tmp / wav, data.get("speaker", ""), (a.get("date") or "")[:10])
            except audio.AudioError as exc:
                raise ElicitError(str(exc)) from exc
            (tmp / f).unlink()
            a["file"] = wav


def receive(db: Database, path) -> Stored:
    """Unpack the speaker's zip into its request's folder (received/). Raises ElicitError."""
    data, zf = read_response_zip(path)
    rid = data.get("request", "")
    st = next((s for s in stored_requests(db.path) if s.request.id == rid), None)
    if st is None:
        raise ElicitError("These recordings answer a request that isn't one of this database's "
                          "(it may have been made from another database).")
    tmp = st.folder / "received.part"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        with zf:
            for a in data.get("cards", []):
                f = a.get("file", "")
                if a.get("status") == "recorded" and f:
                    if not _SAFE.match(f) or "/" in f or f.startswith("."):
                        raise ElicitError(f"A recording has a name that can't be used: {f}")
                    (tmp / f).write_bytes(zf.read("recordings/" + f))
            _wav_from_flac(tmp, data)
            (tmp / "response.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except KeyError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ElicitError(f"A recording is missing from the file: {exc}") from exc
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    old = st.received
    if old.exists():                              # received before: the newer file replaces it
        shutil.rmtree(old, ignore_errors=True)
    tmp.rename(old)
    return load_stored(st.folder)


# --------------------------------------------------------------------------
# Applying a review
# --------------------------------------------------------------------------

@dataclass
class Plan:
    pairs: list = field(default_factory=list)          # (entry or utterance, changed copy)
    renames: list = field(default_factory=list)        # (from, to), in order
    new_utterances: list = field(default_factory=list)
    new_renames: list = field(default_factory=list)    # (held copy, its place in Utterances)
    applied: dict = field(default_factory=dict)        # card number -> what to write in review.json
    notes: list = field(default_factory=list)
    copies: list = field(default_factory=list)         # the received recordings copied into the held folder


def _held(db: Database, name: str, taken: set) -> Path:
    folder = storage.held_folder(db)
    folder.mkdir(parents=True, exist_ok=True)
    stem, suf = Path(name).stem, Path(name).suffix
    target, k = folder / name, 2
    while target.exists() or target in taken:
        target, k = folder / f"{stem} ({k}){suf}", k + 1
    taken.add(target)
    return target


def recorded_date(st: Stored, n: int) -> str:
    a = st.answer(n) or {}
    return (a.get("date") or a.get("recorded") or st.response.get("finished") or "")[:10]


def utterance_label(text: str) -> str:
    """A new utterance's file label: the first six words of its translation (as for clips)."""
    words = re.sub(r"[^\w\s'’-]", " ", text or "").split()
    return " ".join(words[:6])


def plan(db: Database, st: Stored, numbers) -> Plan:
    """What approving these cards changes: tokens and utterances get the new recordings (copied
    into the held folder first, then renamed into place, so undo can take them out again), and
    new utterances are made. A recording replaced goes to the held folder (Recycle Bin on closing)."""
    p = Plan()
    taken: set = set()
    speaker = st.request.speaker["code"]
    changed: dict[str, Entry] = {}               # entry id -> its changed copy (several cards, one entry)
    next_u: dict[str, int] = {}
    for n in numbers:
        c = st.request.card(n)
        rec = st.recording(n)
        if c is None or rec is None:
            continue
        date = recorded_date(st, n)
        if c.kind == NEW_UTTERANCE:
            letter = "U"
            if letter not in next_u:
                ref = db.suggest_utterance_reference(letter)
                next_u[letter] = int(ref[len(letter):])
            num = next_u[letter]
            next_u[letter] += 1
            ref = f"{letter}{num:0{db.settings.ref_digits}d}"
            primary = c.translations.get(db.settings.primary_gloss) or next(iter(c.translations.values()), "")
            u = db.new_utterance(ref, utterance_label(primary), speaker, date)
            f = _translation_field(db)
            if f:
                for lang, text in c.translations.items():
                    u.token.set(f.name, text, lang)
            name = db.expected_filename(u, u.token)
            dest = storage.utterance_folder(db) / name
            if dest.exists():
                p.notes.append(f"{ref}: {name} is already in Soundfiles/Utterances; not added.")
                continue
            held = _held(db, name, taken)
            shutil.copy2(rec, held)
            p.copies.append(held)
            u.token.file = name
            p.new_utterances.append(u)
            p.new_renames.append((held, dest))
            p.applied[n] = {"utterance": u.id, "file": name}
            continue
        item = db.item_by_id(c.entry)
        base = changed.get(c.entry) or (item.copy() if item is not None else None)
        t = next((t for t in base.tokens if t.id == c.token), None) if base is not None else None
        if t is None:
            p.notes.append(f"{c.label}: no longer in the database; not added.")
            continue
        t.speaker = speaker
        if date:
            t.collected = date
        t.rerecord = False
        name = db.expected_filename(base, t)
        folder = storage.folder_for(db, base)
        for old in dict.fromkeys(x for x in (t.file, name) if x):
            if (folder / old).exists():           # the recording replaced (or a stray file in the way)
                p.renames.append((folder / old, _held(db, old, taken)))
        held = _held(db, name, taken)
        shutil.copy2(rec, held)
        p.copies.append(held)
        p.renames.append((held, folder / name))
        t.file = name
        changed[c.entry] = base
        p.applied[n] = {"file": name}
    p.pairs = [(db.item_by_id(i), e) for i, e in changed.items()]
    return p


def discard_plan(p: Plan):
    """Remove the copies a plan made (when it isn't carried out)."""
    for held in p.copies:
        Path(held).unlink(missing_ok=True)


def skipped(st: Stored) -> list[Card]:
    if not st.response:
        return []
    return [c for c in st.request.cards if (st.answer(c.n) or {}).get("status") == "skipped"]


def items_again(db: Database, st: Stored, numbers) -> list[Item]:
    """Cards to send again (skipped or rejected), as items for a new request."""
    out = []
    for n in numbers:
        c = st.request.card(n)
        if c is None:
            continue
        if c.kind == NEW_UTTERANCE:
            out.append(Item(NEW_UTTERANCE, translations=dict(c.translations)))
            continue
        e = db.item_by_id(c.entry)
        t = next((t for t in e.tokens if t.id == c.token), None) if e is not None else None
        if t is not None:
            out.append(Item(c.kind, e, t))
    return out

