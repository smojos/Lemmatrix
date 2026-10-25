# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""A secret kept in Windows' Credential Manager (the audit, P8, 25 October): ɛλicit's Google
sign-in, which used to sit in plain text in the settings (the registry). The Credential
Manager keeps it encrypted for this Windows user. Through ctypes (advapi32's CredWriteW,
CredReadW, CredDeleteW), so no new requirement.

Elsewhere (macOS, Linux), or if Windows refuses, `available()` is False and the caller keeps
the secret where it kept it before.

No Qt in this module.
"""

from __future__ import annotations

import sys

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
MAX_BLOB = 5 * 512                       # CRED_MAX_CREDENTIAL_BLOB_SIZE


class CredError(Exception):
    pass


_api = None


def _load():
    global _api
    if _api is not None:
        return _api
    import ctypes as ct
    from ctypes import wintypes as wt

    class FILETIME(ct.Structure):
        _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]

    class CREDENTIALW(ct.Structure):
        _fields_ = [("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR),
                    ("Comment", wt.LPWSTR), ("LastWritten", FILETIME),
                    ("CredentialBlobSize", wt.DWORD), ("CredentialBlob", ct.POINTER(ct.c_ubyte)),
                    ("Persist", wt.DWORD), ("AttributeCount", wt.DWORD), ("Attributes", ct.c_void_p),
                    ("TargetAlias", wt.LPWSTR), ("UserName", wt.LPWSTR)]

    adv = ct.WinDLL("advapi32", use_last_error=True)
    adv.CredWriteW.argtypes = [ct.POINTER(CREDENTIALW), wt.DWORD]
    adv.CredWriteW.restype = wt.BOOL
    adv.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ct.POINTER(ct.POINTER(CREDENTIALW))]
    adv.CredReadW.restype = wt.BOOL
    adv.CredDeleteW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD]
    adv.CredDeleteW.restype = wt.BOOL
    adv.CredFree.argtypes = [ct.c_void_p]
    adv.CredFree.restype = None
    _api = (ct, CREDENTIALW, adv)
    return _api


def available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        _load()
    except (OSError, AttributeError):
        return False
    return True


def write(target: str, secret: str, user: str = "Lemmatrix"):
    """Keep the secret under this target name. Raises CredError."""
    ct, CREDENTIALW, adv = _load()
    data = secret.encode("utf-8")
    if len(data) > MAX_BLOB:
        raise CredError("too long for the Credential Manager")
    buf = (ct.c_ubyte * len(data)).from_buffer_copy(data) if data else None
    cred = CREDENTIALW()
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.Comment = "Lemmatrix: the ɛλicit Google Drive sign-in"
    cred.CredentialBlobSize = len(data)
    cred.CredentialBlob = ct.cast(buf, ct.POINTER(ct.c_ubyte)) if buf is not None else None
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.UserName = user
    if not adv.CredWriteW(ct.byref(cred), 0):
        raise CredError(f"CredWriteW failed ({ct.get_last_error()})")


def read(target: str) -> str | None:
    """The secret, or None when there is none. Raises CredError."""
    ct, CREDENTIALW, adv = _load()
    p = ct.POINTER(CREDENTIALW)()
    if not adv.CredReadW(target, CRED_TYPE_GENERIC, 0, ct.byref(p)):
        err = ct.get_last_error()
        if err == ERROR_NOT_FOUND:
            return None
        raise CredError(f"CredReadW failed ({err})")
    try:
        n = p.contents.CredentialBlobSize
        return ct.string_at(p.contents.CredentialBlob, n).decode("utf-8") if n else ""
    finally:
        adv.CredFree(p)


def delete(target: str):
    """Forget the secret (nothing to forget is fine). Raises CredError."""
    ct, _, adv = _load()
    if not adv.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
        err = ct.get_last_error()
        if err != ERROR_NOT_FOUND:
            raise CredError(f"CredDeleteW failed ({err})")
