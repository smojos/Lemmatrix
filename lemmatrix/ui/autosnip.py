# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""✂ auto-snip's files (IDEAS.md idea 10, Josh, 27 October; `lemmatrix/snip.py` does the cutting).

- **A fresh take** is trimmed before it is saved (the recording panel's `auto_snip`); the untrimmed
  take is kept in Soundfiles › _Deleted recordings as *<name> (untrimmed).wav*, which goes to the
  Recycle Bin when the database closes, so a clipped quiet edge can always be recovered.
- **The ✂ button** (*proselytize this soundfile*) snips a soundfile already there (made outside
  Lemmatrix, or recorded while auto-snip was off): the original goes to the same place as
  *<name> (unsnipped).wav*, and the snipped one takes its name, with the same speaker and date.
"""

from __future__ import annotations

import wave
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from .. import advanced, audio, snip


def _held(main, path: Path, label: str) -> Path:
    return main.doc.hold_recording(path.with_name(f"{path.stem} ({label}){path.suffix}"))


def hold_untrimmed(main, path: Path, samples, rate: int, artist: str = "", date: str = ""):
    """The take as it was recorded, before auto-snip trimmed it: kept for now, never in the way."""
    try:
        audio.write_wav(_held(main, Path(path), "untrimmed"), samples, rate, main.prefs.bit_depth,
                        artist=artist, date=date)
    except (OSError, audio.AudioError):
        pass                                      # the trimmed take is saved; the copy is a courtesy


def _bits(path: Path, fallback: int) -> int:
    try:
        with wave.open(str(path), "rb") as w:
            bits = w.getsampwidth() * 8
        return bits if bits in (16, 24, 32) else fallback
    except (wave.Error, OSError, EOFError):
        return fallback


def proselytize(main, parent, path: Path, gaps: bool) -> bool:
    """Snip the soundfile at `path` once (the ✂ button). True when it changed."""
    path = Path(path)
    if not path.exists():
        return False
    if path.suffix.lower() != ".wav":
        QMessageBox.information(parent, advanced.AUTO_SNIP, "Only WAV soundfiles can be snipped.")
        return False
    try:
        data, rate = audio.read_any(path)
    except Exception as exc:                      # noqa: BLE001
        QMessageBox.warning(parent, advanced.AUTO_SNIP, f"Couldn't read {path.name}: {exc}")
        return False
    if getattr(data, "ndim", 1) > 1:
        QMessageBox.information(parent, advanced.AUTO_SNIP, f"{path.name} is stereo: only mono "
                                "soundfiles (as Lemmatrix records them) can be snipped.")
        return False
    out, rep = snip.snip(data, rate, gaps=gaps, **advanced.snip_margins())
    if not rep.changed:
        QMessageBox.information(parent, advanced.AUTO_SNIP, f"{path.name}: {rep.describe()}.")
        return False
    info = {}
    try:
        info = audio.read_info(path)
    except OSError:
        pass
    bits = _bits(path, main.prefs.bit_depth)
    held = _held(main, path, "unsnipped")
    main.player.stop()
    try:
        path.rename(held)
    except OSError as exc:
        QMessageBox.warning(parent, advanced.AUTO_SNIP, f"Couldn't snip {path.name} (is it open in "
                            f"Praat?): {exc}")
        return False
    try:
        audio.write_wav(path, out, rate, bits, artist=info.get("IART", ""), date=info.get("ICRD", ""))
    except (OSError, audio.AudioError) as exc:
        try:
            held.rename(path)                     # put the original back
        except OSError:
            pass
        QMessageBox.warning(parent, advanced.AUTO_SNIP, f"Couldn't save the snipped {path.name}: {exc}")
        return False
    return True
