# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Settings → Advanced: *Women, Fire, and Dangerous Things* (Lakoff 1987) (IDEAS.md ideas 68, 79, 86; Josh, 27
October). Options for experienced users, this computer's, all off on a new computer, reached only in
Settings → Advanced (never from the menus at the top). ⚡ power search lives in `search.py`; this
module holds the other two:

- **🔥 hot mic** (idea 68): a take records straight over the soundfile already there, no question
  asked (token, utterance and segment dialogues); the Record button wears the hot mic icon.
- **📋 fast paste** (idea 79): in Phonetic or Phonemic, Shift+Down / Shift+Up copies the field into
  the other transcription, replacing what's there (`ui/fastpaste.py`).

No Qt here.
"""

from __future__ import annotations

from typing import Callable

HOT_MIC_KEY = "recording/hot_mic"
FAST_PASTE_KEY = "edit/fast_paste"
HOT_MIC, FAST_PASTE = "🔥 hot mic", "📋 fast paste"

_state = {HOT_MIC_KEY: False, FAST_PASTE_KEY: False}
_listeners: list[Callable[[str, bool], None]] = []


def on(key: str) -> bool:
    return bool(_state.get(key, False))


def hot_mic() -> bool:
    return on(HOT_MIC_KEY)


def fast_paste() -> bool:
    return on(FAST_PASTE_KEY)


def set_on(key: str, value: bool):
    value = bool(value)
    if _state.get(key, False) == value:
        return
    _state[key] = value
    for fn in list(_listeners):
        try:
            fn(key, value)
        except RuntimeError:                       # a Qt object already deleted
            _listeners.remove(fn)


def load(prefs):
    """This computer's choices (off unless set)."""
    for key in (HOT_MIC_KEY, FAST_PASTE_KEY):
        set_on(key, prefs.get_bool(key, False))


def listen(fn: Callable[[str, bool], None]):
    _listeners.append(fn)


def unlisten(fn):
    if fn in _listeners:
        _listeners.remove(fn)
