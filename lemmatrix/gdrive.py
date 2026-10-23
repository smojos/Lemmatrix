# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Google Drive for ɛλicit (IDEAS.md idea 19, stage 2), with nothing but the standard library.

Signing in is the installed-app flow: the browser opens Google's sign-in page, which sends the
answer back to a little server on this computer (127.0.0.1, a free port), with PKCE. The only
permission asked for is drive.file: Lemmatrix sees the files it makes itself, nothing else in
the researcher's Drive. The sign-in (a refresh token) is kept on this computer by the caller.

No Qt in this module; the network calls block, so the program runs them off the main thread.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass

from . import cloud_keys

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
SCOPE = "https://www.googleapis.com/auth/drive.file"
FOLDER = "application/vnd.google-apps.folder"
PAGE_ORIGIN = "https://smojos.github.io"      # upload links answer this page (CORS)
TIMEOUT = 60


class DriveError(Exception):
    pass


class SignInNeeded(DriveError):
    pass


# --------------------------------------------------------------------------
# Signing in
# --------------------------------------------------------------------------

_DONE_PAGE = ("<!doctype html><meta charset='utf-8'><title>Lemmatrix</title>"
              "<body style='font:18px system-ui;margin:40px;color:#1b1b1b'>"
              "<h2 style='color:#198583'>Lemmatrix is signed in to Google Drive.</h2>"
              "<p>You can close this tab and go back to Lemmatrix.</p>")
_FAIL_PAGE = ("<!doctype html><meta charset='utf-8'><title>Lemmatrix</title>"
              "<body style='font:18px system-ui;margin:40px'><h2>Not signed in.</h2>"
              "<p>You can close this tab; Lemmatrix will say what happened.</p>")


def authorize(open_browser, cancelled=lambda: False, wait: float = 300) -> dict:
    """Sign in through the browser. open_browser(url) opens it; returns the token dict
    (access_token, refresh_token, expires_at). Raises DriveError."""
    if not cloud_keys.google_ready():
        raise DriveError("This copy of Lemmatrix has no Google Drive keys yet.")
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                         # noqa: N802 (the http.server name)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state:
                self.send_response(404)
                self.end_headers()
                return
            got.update({k: v[0] for k, v in q.items()})
            ok = "code" in got
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write((_DONE_PAGE if ok else _FAIL_PAGE).encode("utf-8"))

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 0.5
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cloud_keys.GOOGLE_CLIENT_ID, "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent"})
    try:
        open_browser(url)
        end = time.monotonic() + wait
        while not got and time.monotonic() < end and not cancelled():
            server.handle_request()
    finally:
        server.server_close()
    if not got:
        raise DriveError("Signing in to Google Drive was cancelled or took too long.")
    if "code" not in got:
        raise DriveError(f"Google Drive didn't sign in: {got.get('error', 'no answer')}.")
    tok = _token_request({"code": got["code"], "code_verifier": verifier, "redirect_uri": redirect,
                          "grant_type": "authorization_code"})
    if not tok.get("refresh_token"):
        raise DriveError("Google didn't give Lemmatrix a lasting sign-in (no refresh token). Try again.")
    return tok


def _token_request(fields: dict) -> dict:
    data = dict(fields, client_id=cloud_keys.GOOGLE_CLIENT_ID, client_secret=cloud_keys.GOOGLE_CLIENT_SECRET)
    req = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(data).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            tok = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        if "invalid_grant" in body:
            raise SignInNeeded("The Google Drive sign-in has expired or was withdrawn: sign in again.") from exc
        raise DriveError(f"Google's sign-in service answered {exc.code}: {body[:200]}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise DriveError(f"Couldn't reach Google ({exc}). Are you online?") from exc
    tok["expires_at"] = time.time() + float(tok.get("expires_in", 3600)) - 60
    return tok


def revoke(token: dict):
    """Withdraw the sign-in at Google (Sign out of Google Drive); best effort."""
    t = token.get("refresh_token") or token.get("access_token")
    if not t:
        return
    try:
        urllib.request.urlopen(urllib.request.Request(
            REVOKE_URL, data=urllib.parse.urlencode({"token": t}).encode(), method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=TIMEOUT).close()
    except (urllib.error.URLError, OSError):
        pass


# --------------------------------------------------------------------------
# The Drive
# --------------------------------------------------------------------------

@dataclass
class Response:
    status: int
    headers: dict
    body: bytes

    def json(self):
        return json.loads(self.body.decode("utf-8")) if self.body else {}


class Drive:
    """The researcher's Drive, as far as drive.file lets Lemmatrix see it.

    token: the dict authorize() returned; on_token(token) is called when it is refreshed, so the
    caller can keep the new one. opener: urllib's, replaceable in tests."""

    def __init__(self, token: dict, on_token=None, opener=None):
        self.token = dict(token or {})
        self.on_token = on_token
        self.opener = opener or urllib.request.urlopen
        self._lock = threading.Lock()

    # ---- the access token ---------------------------------------------
    def access(self) -> str:
        with self._lock:
            if not self.token.get("refresh_token"):
                raise SignInNeeded("Sign in to Google Drive first.")
            if not self.token.get("access_token") or time.time() >= self.token.get("expires_at", 0):
                fresh = _token_request({"refresh_token": self.token["refresh_token"],
                                        "grant_type": "refresh_token"})
                fresh.setdefault("refresh_token", self.token["refresh_token"])
                self.token = fresh
                if self.on_token:
                    self.on_token(dict(fresh))
            return self.token["access_token"]

    def call(self, method: str, url: str, body: bytes | None = None, headers: dict | None = None,
             ok=(200, 201, 204)) -> Response:
        h = {"Authorization": "Bearer " + self.access()}
        h.update(headers or {})
        req = urllib.request.Request(url, data=body, method=method, headers=h)
        try:
            with self.opener(req, timeout=TIMEOUT) as r:
                res = Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")
            if exc.code == 401:
                raise SignInNeeded("Google Drive asked to sign in again.") from exc
            if exc.code == 404:
                raise DriveError("not found") from exc
            try:
                msg = json.loads(text)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                msg = text[:200]
            raise DriveError(f"Google Drive answered {exc.code}: {msg}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise DriveError(f"Couldn't reach Google Drive ({exc}). Are you online?") from exc
        if res.status not in ok:
            raise DriveError(f"Google Drive answered {res.status}.")
        return res

    # ---- files ----------------------------------------------------------
    def create_folder(self, name: str, parent: str = "") -> str:
        meta = {"name": name, "mimeType": FOLDER}
        if parent:
            meta["parents"] = [parent]
        r = self.call("POST", API + "/files?fields=id", json.dumps(meta).encode(),
                      {"Content-Type": "application/json; charset=UTF-8"})
        return r.json()["id"]

    def find_folder(self, name: str) -> str:
        """A folder Lemmatrix made at the top of the Drive, by name ("" if none)."""
        q = f"name = '{name}' and mimeType = '{FOLDER}' and 'root' in parents and trashed = false"
        r = self.call("GET", API + "/files?" + urllib.parse.urlencode({"q": q, "fields": "files(id)"}))
        files = r.json().get("files", [])
        return files[0]["id"] if files else ""

    def upload(self, name: str, data: bytes, mime: str, parent: str) -> str:
        """A small file in one go (multipart). Returns its id."""
        boundary = "lemmatrix" + uuid.uuid4().hex
        meta = json.dumps({"name": name, "parents": [parent]}).encode()
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n").encode() + meta + \
            (f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode() + data + f"\r\n--{boundary}--".encode()
        r = self.call("POST", UPLOAD + "?uploadType=multipart&fields=id", body,
                      {"Content-Type": f"multipart/related; boundary={boundary}"})
        return r.json()["id"]

    def share_by_link(self, file_id: str):
        """Anyone with the file's id can read it (the page fetches it with the API key)."""
        self.call("POST", f"{API}/files/{file_id}/permissions?fields=id",
                  json.dumps({"type": "anyone", "role": "reader"}).encode(),
                  {"Content-Type": "application/json; charset=UTF-8"})

    def upload_link(self, name: str, mime: str, parent: str, origin: str = PAGE_ORIGIN) -> str:
        """A resumable upload session for a file to come (a recording): its address is all the
        page needs to upload it, with no sign-in. Google keeps it for a week. The page's origin is
        sent with it, so Google answers the page's upload (CORS)."""
        r = self.call("POST", UPLOAD + "?uploadType=resumable&fields=id,name",
                      json.dumps({"name": name, "parents": [parent]}).encode(),
                      {"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": mime,
                       "Origin": origin})
        link = r.headers.get("location", "")
        if not link:
            raise DriveError("Google Drive didn't give an upload link.")
        return link

    def list_folder(self, folder: str) -> list[dict]:
        out, page = [], ""
        while True:
            q = {"q": f"'{folder}' in parents and trashed = false",
                 "fields": "nextPageToken, files(id, name, size, mimeType)", "pageSize": "200"}
            if page:
                q["pageToken"] = page
            r = self.call("GET", API + "/files?" + urllib.parse.urlencode(q)).json()
            out += r.get("files", [])
            page = r.get("nextPageToken", "")
            if not page:
                return out

    def download(self, file_id: str) -> bytes:
        return self.call("GET", f"{API}/files/{file_id}?alt=media").body

    def delete(self, file_id: str):
        """Delete for good (not the bin): destroyed means destroyed."""
        try:
            self.call("DELETE", f"{API}/files/{file_id}")
        except DriveError as exc:
            if str(exc) != "not found":
                raise
