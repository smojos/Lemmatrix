# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Knowing when a database is open somewhere else.

While a database is open, Lemmatrix keeps a small marker file next to it:
".<database file name>.lemmatrix-lock", saying which computer (and user) has it
open, since when, and when Lemmatrix last checked in. OneDrive or Dropbox syncs
the marker like any other file, so another computer opening the same database
sees it and can warn. The marker is removed when the database is closed.

A crash leaves the marker behind. On the same computer that is detected (the
program that wrote it is no longer running) and the marker is simply replaced;
from another computer, the "last active" time helps judge whether it's stale.
"""

from __future__ import annotations

import datetime as _dt
import getpass
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path

SUFFIX = ".lemmatrix-lock"


ANOTHER_RUNNING = ("Another instance of Lemmatrix is currently running on this computer. Please save and "
                   "close it before starting another to avoid bugs.")


def single_instance():
    """A lock held while this Lemmatrix runs, or None if another one on this computer holds it.

    Keep the returned object alive for as long as the program runs."""
    from PySide6.QtCore import QDir, QLockFile
    name = os.environ.get("LEMMATRIX_SETTINGS", "Lemmatrix")      # tests use a name of their own
    lock = QLockFile(QDir(QDir.tempPath()).filePath(f"{name}.running.lock"))
    lock.setStaleLockTime(0)                  # a lock left by a crash is noticed by its process id
    return lock if lock.tryLock(0) else None


def lock_path(db_path: str | Path) -> Path:
    p = Path(db_path)
    return p.with_name("." + p.name + SUFFIX)


def this_computer() -> str:
    return os.environ.get("COMPUTERNAME") or socket.gethostname() or "this computer"


def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""


def _now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259                            # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@dataclass
class LockInfo:
    computer: str = ""
    user: str = ""
    pid: int = 0
    opened: str = ""
    seen: str = ""

    def mine(self) -> bool:
        return self.computer == this_computer() and self.pid == os.getpid()

    def describe(self) -> str:
        who = self.computer + (f" (by {self.user})" if self.user else "")
        return f"{who}, opened {self.opened}" + (f", last active {self.seen}" if self.seen else "")


def read(db_path: str | Path) -> LockInfo | None:
    p = lock_path(db_path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return LockInfo(str(data.get("computer", "")), str(data.get("user", "")), int(data.get("pid", 0)),
                        str(data.get("opened", "")), str(data.get("seen", "")))
    except (OSError, ValueError, TypeError):
        return None


def held_elsewhere(db_path: str | Path) -> LockInfo | None:
    """The marker of another copy of Lemmatrix that has this database open, if any."""
    info = read(db_path)
    if info is None or info.mine():
        return None
    if info.computer == this_computer() and not _pid_alive(info.pid):
        return None                         # left behind by a crash on this computer
    return info


def claim(db_path: str | Path, opened: str | None = None) -> None:
    """Write (or refresh) this program's marker for the database."""
    p = lock_path(db_path)
    old = read(db_path)
    data = {"computer": this_computer(), "user": _user(), "pid": os.getpid(),
            "opened": opened or (old.opened if old and old.mine() else _now()), "seen": _now()}
    try:
        if os.name == "nt" and p.exists():  # Windows won't overwrite a hidden file: unhide first
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(p), 0x80)      # FILE_ATTRIBUTE_NORMAL
        p.write_text(json.dumps(data, indent=1), encoding="utf-8")
        if os.name == "nt":                 # keep it out of the way in File Explorer
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(p), 0x02)      # FILE_ATTRIBUTE_HIDDEN
    except OSError:
        pass                                # a read-only folder: just no warning for others


def release(db_path: str | Path) -> None:
    """Remove the marker, but only if it's this program's."""
    info = read(db_path)
    if info is not None and info.mine():
        try:
            lock_path(db_path).unlink()
        except OSError:
            pass
