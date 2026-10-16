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
    def confirm_delete(self) -> bool:
        return self._get("safety/confirm_delete", True, bool)

    @confirm_delete.setter
    def confirm_delete(self, v): self.q.setValue("safety/confirm_delete", bool(v))

    @property
    def autosave_minutes(self) -> int:
        return self._get("safety/autosave_minutes", 0, int)

    @autosave_minutes.setter
    def autosave_minutes(self, v): self.q.setValue("safety/autosave_minutes", int(v))

    # display
    @property
    def ipa_size(self) -> int:
        return self._get("display/ipa_size", 13, int)

    @ipa_size.setter
    def ipa_size(self, v): self.q.setValue("display/ipa_size", int(v))

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
