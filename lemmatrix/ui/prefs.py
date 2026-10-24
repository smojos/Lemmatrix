# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Per-computer preferences (not stored in the database file)."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings


class Prefs:
    def __init__(self):
        # Tests set LEMMATRIX_SETTINGS so they never touch the real preferences.
        self.q = QSettings("Lemmatrix", os.environ.get("LEMMATRIX_SETTINGS", "Lemmatrix"))

    def _get(self, key, default, kind=str):
        v = self.q.value(key, default)
        if kind is bool:
            return v in (True, "true", "1", 1)
        try:
            return kind(v)
        except (TypeError, ValueError):
            return default

    # the comparison area's tab (Pitch or Segments; idea 46): this computer's
    @property
    def comparison_tab(self) -> str:
        return self._get("comparison/tab", "pitch")

    @comparison_tab.setter
    def comparison_tab(self, v): self.q.setValue("comparison/tab", v)

    # recording
    @property
    def record_source(self) -> str:
        return self._get("recording/source", "microphone")

    @record_source.setter
    def record_source(self, v): self.q.setValue("recording/source", v)

    @property
    def bit_depth(self) -> int:
        return self._get("recording/bits", 16, int)

    @bit_depth.setter
    def bit_depth(self, v): self.q.setValue("recording/bits", int(v))

    @property
    def sample_rate(self) -> int:
        return self._get("recording/rate", 44100, int)

    @sample_rate.setter
    def sample_rate(self, v): self.q.setValue("recording/rate", int(v))

    # playback and safety
    @property
    def auto_play(self) -> bool:
        return self._get("playback/autoplay", False, bool)

    @auto_play.setter
    def auto_play(self, v): self.q.setValue("playback/autoplay", bool(v))

    @property
    def delete_recordings_with_tokens(self) -> bool:
        return self._get("safety/delete_recordings_with_tokens", True, bool)

    @delete_recordings_with_tokens.setter
    def delete_recordings_with_tokens(self, v): self.q.setValue("safety/delete_recordings_with_tokens", bool(v))

    def get_bool(self, key: str, default: bool = False) -> bool:
        return self._get(key, default, bool)

    @property
    def you(self) -> dict:
        """The researcher using this computer (Josh, 23 October): name, code and email, filled into
        File → New database from the last new database, and kept by the new-day reset."""
        return {k: str(self.q.value(f"you/{k}", "") or "") for k in ("name", "code", "email")}

    @you.setter
    def you(self, v: dict):
        for k in ("name", "code", "email"):
            self.q.setValue(f"you/{k}", (v or {}).get(k, ""))

    def get_value(self, key: str):
        return self.q.value(key)

    def set_value(self, key: str, value):
        self.q.setValue(key, value)

    @property
    def google_token(self) -> dict:
        """ɛλicit's Google Drive sign-in on this computer (a refresh token: it reaches only the files
        Lemmatrix made itself, the drive.file permission); {} when signed out."""
        import json
        try:
            return json.loads(self.q.value("elicit/google_token", "") or "{}")
        except (ValueError, TypeError):
            return {}

    @google_token.setter
    def google_token(self, token: dict):
        import json
        self.q.setValue("elicit/google_token", json.dumps(token) if token else "")
        self.q.sync()

    def get_list(self, key: str) -> list[str]:
        v = self.q.value(key, [])
        if isinstance(v, str):
            return [x for x in v.split("|") if x]
        return list(v or [])

    def set_list(self, key: str, values: list[str]):
        self.q.setValue(key, "|".join(values))

    @property
    def warn_unusual_tags(self) -> bool:
        """Mark tags that aren't usual for their lemma's word class (Settings → General → Warnings)."""
        return self._get("warnings/unusual_tags", True, bool)

    @warn_unusual_tags.setter
    def warn_unusual_tags(self, v): self.q.setValue("warnings/unusual_tags", bool(v))

    @property
    def underline_spelling(self) -> bool:
        """Red wavy lines under English words that may be misspelled (Settings → General → Warnings)."""
        return self._get("warnings/spelling", True, bool)

    @underline_spelling.setter
    def underline_spelling(self, v): self.q.setValue("warnings/spelling", bool(v))

    @property
    def confirm_delete(self) -> bool:
        return self._get("safety/confirm_delete", True, bool)

    @confirm_delete.setter
    def confirm_delete(self, v): self.q.setValue("safety/confirm_delete", bool(v))

    @property
    def autosave_minutes(self) -> int:
        return self._get("safety/autosave_minutes", 5, int)      # on by default (18 October)

    @autosave_minutes.setter
    def autosave_minutes(self, v): self.q.setValue("safety/autosave_minutes", int(v))

    @property
    def splash_seconds(self) -> float:
        """How long the splash screen stays at least (0: only while Lemmatrix starts)."""
        return max(0.0, min(5.0, self._get("display/splash_seconds", 2.5, float)))

    @splash_seconds.setter
    def splash_seconds(self, v): self.q.setValue("display/splash_seconds", float(v))

    @property
    def welcome_mode(self) -> str:
        """The welcome window at start-up (Josh, 23 October): "" until it has been shown once
        (the first start), then "never" (the most recent database opens straight away); "always"
        once ticked in Settings → General or in the window itself."""
        v = self._get("start/welcome", "", str)
        return v if v in ("", "always", "never") else ""

    @welcome_mode.setter
    def welcome_mode(self, v): self.q.setValue("start/welcome", v if v in ("", "always", "never") else "never")

    @property
    def show_welcome(self) -> bool:
        """Settings → General → Show the welcome window at every start (ticked: "always")."""
        return self.welcome_mode == "always"

    @show_welcome.setter
    def show_welcome(self, on: bool): self.welcome_mode = "always" if on else "never"

    # display
    @property
    def ipa_size(self) -> int:
        return self._get("display/ipa_size", 13, int)

    @ipa_size.setter
    def ipa_size(self, v): self.q.setValue("display/ipa_size", int(v))

    @property
    def theme(self) -> str:
        return self._get("display/theme", "light")

    @theme.setter
    def theme(self, v): self.q.setValue("display/theme", v)

    @property
    def accent(self) -> str:
        from .theme import DEFAULT_ACCENT
        v = self._get("display/accent", DEFAULT_ACCENT)
        # earlier defaults were never anyone's choice, so they follow the current default
        return DEFAULT_ACCENT if v.lower() in ("#3a78d4", "#385867", "#198768") else v

    @accent.setter
    def accent(self, v): self.q.setValue("display/accent", v)

    @property
    def full_backup_folder(self) -> str:
        """Where File → Full backup offers to save ("" = Documents). Local backups always go in
        the database's own Backups folder."""
        return self._get("safety/full_backup_folder", "")

    @full_backup_folder.setter
    def full_backup_folder(self, v): self.q.setValue("safety/full_backup_folder", v)

    def full_backup_dates(self, path: str) -> dict:
        """For one database: last (the last full backup), snoozed (no reminder before), first_seen."""
        key = self._view_key(path).replace("views/", "fullbackup/")
        return {k: self._get(f"{key}/{k}", "") for k in ("last", "snoozed", "first_seen")}

    def set_full_backup_date(self, path: str, which: str, day: str):
        key = self._view_key(path).replace("views/", "fullbackup/")
        self.q.setValue(f"{key}/{which}", day)

    @property
    def pitch_volume(self) -> int:
        return self._get("pitch/volume", 70, int)

    @pitch_volume.setter
    def pitch_volume(self, v): self.q.setValue("pitch/volume", int(v))

    @property
    def autoplay_tokens(self) -> bool:
        """One Auto-play setting for every tab (before, each matrix had its own)."""
        v = self.q.value("matrix/autoplay")
        if v is None:
            return self.get_bool("matrix/autoplay_lemma-tag") or self.get_bool("matrix/autoplay_tag-tag")
        return self._get("matrix/autoplay", False, bool)

    @autoplay_tokens.setter
    def autoplay_tokens(self, v): self.q.setValue("matrix/autoplay", bool(v))

    @property
    def only_lemmas_with_data(self) -> bool:
        return self._get("matrix/only_with_data", False, bool)

    @only_lemmas_with_data.setter
    def only_lemmas_with_data(self, v): self.q.setValue("matrix/only_with_data", bool(v))

    @property
    def praat_path(self) -> str:
        v = self._get("programs/praat", "")
        if not v:
            from ..praat import find_praat
            v = find_praat()
        return v

    @praat_path.setter
    def praat_path(self, v): self.q.setValue("programs/praat", v)

    @property
    def pitch_voice(self) -> str:
        return self._get("pitch/voice", "whistle")

    @pitch_voice.setter
    def pitch_voice(self, v): self.q.setValue("pitch/voice", v)

    # the last view of each database (tab, lemma, matrices), as JSON
    @staticmethod
    def _view_key(path: str) -> str:
        import hashlib
        return "views/" + hashlib.md5(os.path.normcase(os.path.abspath(path)).encode("utf-8")).hexdigest()

    def view_for(self, path: str) -> dict:
        import json
        try:
            v = json.loads(self._get(self._view_key(path), "") or "{}")
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}

    def set_view_for(self, path: str, view: dict):
        import json
        self.q.setValue(self._view_key(path), json.dumps(view, ensure_ascii=False))

    def session_for(self, path: str) -> dict:
        """The Current Session's people and places last used with a database."""
        import json
        try:
            v = json.loads(self._get(self._view_key(path).replace("views/", "sessions/"), "") or "{}")
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}

    def set_session_for(self, path: str, session: dict):
        import json
        self.q.setValue(self._view_key(path).replace("views/", "sessions/"),
                        json.dumps(session, ensure_ascii=False))

    def move_database(self, old: str, new: str):
        """A renamed database keeps its view, session and full-backup dates (File → Rename database)."""
        a, b = self._view_key(old), self._view_key(new)
        if a == b:
            return
        for prefix in ("views/", "sessions/"):
            ka, kb = a.replace("views/", prefix), b.replace("views/", prefix)
            v = self.q.value(ka)
            if v is not None:
                self.q.setValue(kb, v)
                self.q.remove(ka)
        for which in ("last", "snoozed", "first_seen"):
            ka = a.replace("views/", "fullbackup/") + "/" + which
            v = self.q.value(ka)
            if v is not None:
                self.q.setValue(b.replace("views/", "fullbackup/") + "/" + which, v)
                self.q.remove(ka)
        last = self.last_file
        if last and os.path.normcase(os.path.abspath(last)) == os.path.normcase(os.path.abspath(old)):
            self.last_file = new
        self.recent = [dict(r, path=new) if _same(r["path"], old) else r for r in self.recent]

    # ---- File → Open recent (IDEAS.md idea 51; Josh, 23 October) -----------------------------
    RECENT_KEPT = 10

    @property
    def recent(self) -> list[dict]:
        """The databases opened lately on this computer, most recently opened first: each
        {"path": …, "title": "Language - Variety - Name"}."""
        import json
        try:
            v = json.loads(self.q.value("files/recent", "") or "[]")
        except (ValueError, TypeError):
            return []
        return [r for r in v if isinstance(r, dict) and r.get("path")][:self.RECENT_KEPT]

    @recent.setter
    def recent(self, items: list[dict]):
        import json
        self.q.setValue("files/recent", json.dumps(list(items)[:self.RECENT_KEPT], ensure_ascii=False))

    def add_recent(self, path: str, title: str = ""):
        """`path` opened (or saved) just now: to the top of the list, once."""
        if not path:
            return
        path = os.path.abspath(path)
        self.recent = [{"path": path, "title": title}] + [r for r in self.recent if not _same(r["path"], path)]

    def get_bytes(self, key: str):
        return self.q.value(key)

    # session and files
    @property
    def speaker(self) -> str:
        return self._get("session/speaker", "")

    @speaker.setter
    def speaker(self, v): self.q.setValue("session/speaker", v)

    @property
    def last_file(self) -> str:
        return self._get("files/last", "")

    @last_file.setter
    def last_file(self, v): self.q.setValue("files/last", v)


def _same(a: str, b: str) -> bool:
    """Two paths to the same file (capitals ignored where the system ignores them)."""
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
