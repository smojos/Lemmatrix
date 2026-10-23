# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Opening recordings in Praat.

Praat is started with "--send" and a small script that reads the sound and
opens it with View & Edit. If Praat is already running, that Praat opens it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class PraatError(Exception):
    pass


def _candidates() -> list[Path]:
    if sys.platform.startswith("win"):
        roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
                                             "LOCALAPPDATA", "USERPROFILE")]
        out = []
        for r in filter(None, roots):
            r = Path(r)
            out += [r / "Praat.exe", r / "Praat" / "Praat.exe", r / "Programs" / "Praat" / "Praat.exe",
                    r / "Desktop" / "Praat.exe", r / "Downloads" / "Praat.exe"]
        return out
    if sys.platform == "darwin":
        return [Path("/Applications/Praat.app"), Path.home() / "Applications" / "Praat.app"]
    return [Path("/usr/bin/praat"), Path("/usr/local/bin/praat"), Path("/snap/bin/praat")]


def find_praat() -> str:
    """A likely path to Praat on this computer, or "" if none is found."""
    for p in _candidates():
        if p.exists():
            return str(p)
    found = shutil.which("praat") or shutil.which("Praat")
    return found or ""


def executable(path: str) -> Path:
    """The program to run: inside a Mac .app bundle if one was chosen."""
    p = Path(path)
    if p.suffix.lower() == ".app" and p.is_dir():
        inner = p / "Contents" / "MacOS" / "Praat"
        if inner.exists():
            return inner
    return p


ZOOM_MARGIN = 1.0                           # seconds shown either side of a selected line


def script_for(sound: Path, textgrid: Path | None = None, select: tuple[float, float] | None = None) -> str:
    """The script Praat runs. select: (start, end) of a line to zoom to and select."""
    quoted = str(sound).replace('"', '""')
    if textgrid is None:
        return f'Read from file: "{quoted}"\nView & Edit\n'
    tg = str(textgrid).replace('"', '""')     # the sound and its TextGrid, in one editor
    script = (f'sound = Read from file: "{quoted}"\ngrid = Read from file: "{tg}"\n'
              "selectObject: sound, grid\nView & Edit\n")
    if select is not None:
        start, end = select
        script += (f"editor: grid\n"
                   f"    Zoom: {max(0.0, start - ZOOM_MARGIN):.4f}, {end + ZOOM_MARGIN:.4f}\n"
                   f"    Select: {start:.4f}, {end:.4f}\n"
                   "endeditor\n")
    return script


def open_sound(praat_path: str, sound: str | Path, textgrid: str | Path | None = None,
               select: tuple[float, float] | None = None) -> None:
    """Open a soundfile in Praat's sound editor (with its TextGrid, if given, zoomed to the
    stretch select if given). Raises PraatError with a readable reason."""
    sound = Path(sound)
    if not sound.exists():
        raise PraatError(f"{sound.name} isn't in the sound folder.")
    if textgrid is not None and not Path(textgrid).exists():
        textgrid = None
    if not praat_path:
        raise PraatError("Lemmatrix doesn't know where Praat is yet.")
    exe = executable(praat_path)
    if not exe.exists():
        raise PraatError(f"Praat isn't at {praat_path}.")
    script = Path(tempfile.gettempdir()) / "lemmatrix-open-in-praat.praat"
    script.write_text(script_for(sound.resolve(), Path(textgrid).resolve() if textgrid else None,
                                 select if textgrid else None), encoding="utf-8")
    kwargs = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([str(exe), "--hide-picture", "--send", str(script)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True, **kwargs)
    except OSError as exc:
        raise PraatError(f"Couldn't start Praat: {exc}") from exc
