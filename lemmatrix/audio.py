"""Recording and playback.

Microphone input uses `sounddevice`. Recording what the computer is playing
("computer audio") uses `soundcard`'s loopback devices, which works on Windows.
Both libraries are imported only when needed, so the rest of the program runs
even where no audio system is available.

WAV files are written here directly so the speaker can be stored in the file's
own metadata (INFO "IART", shown as "artist") and the collection date in
"ICRD".
"""

from __future__ import annotations

import re
import struct
import threading
import wave
from pathlib import Path

import numpy as np


class AudioError(Exception):
    pass


# --------------------------------------------------------------------------
# WAV files
# --------------------------------------------------------------------------

def _info_chunk(info: dict[str, str]) -> bytes:
    body = b"INFO"
    for key, value in info.items():
        if not value:
            continue
        data = value.encode("utf-8") + b"\x00"
        if len(data) % 2:
            data += b"\x00"
        body += key.encode("ascii") + struct.pack("<I", len(data)) + data
    if body == b"INFO":
        return b""
    return b"LIST" + struct.pack("<I", len(body)) + body


def write_wav(path: str | Path, samples: np.ndarray, sample_rate: int, bits: int = 16,
              artist: str = "", date: str = "") -> None:
    """Write mono float samples (-1..1) as PCM WAV with optional INFO metadata."""
    samples = np.clip(np.asarray(samples, dtype=np.float64).reshape(-1), -1.0, 1.0)
    if bits == 16:
        pcm = (samples * 32767).astype("<i2").tobytes()
    elif bits == 24:
        ints = (samples * 8388607).astype("<i4")
        pcm = ints.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    elif bits == 32:
        pcm = (samples * 2147483647).astype("<i4").tobytes()
    else:
        raise AudioError(f"Unsupported bit depth: {bits}")
    channels = 1
    block = channels * bits // 8
    fmt = struct.pack("<HHIIHH", 1, channels, sample_rate, sample_rate * block, block, bits)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    data = pcm + (b"\x00" if len(pcm) % 2 else b"")
    chunks += b"data" + struct.pack("<I", len(pcm)) + data
    chunks += _info_chunk({"IART": artist, "ICRD": date})
    blob = b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(blob)
    tmp.replace(path)


def read_info(path: str | Path) -> dict[str, str]:
    """Read the INFO metadata (e.g. IART) from a WAV file."""
    raw = Path(path).read_bytes()
    out: dict[str, str] = {}
    pos = 12
    while pos + 8 <= len(raw):
        cid, size = raw[pos:pos + 4], struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if cid == b"LIST" and body[:4] == b"INFO":
            p = 4
            while p + 8 <= len(body):
                key, n = body[p:p + 4].decode("ascii", "replace"), struct.unpack("<I", body[p + 4:p + 8])[0]
                out[key] = body[p + 8:p + 8 + n].rstrip(b"\x00").decode("utf-8", "replace")
                p += 8 + n + (n % 2)
        pos += 8 + size + (size % 2)
    return out


_DATE = re.compile(r"(\d{4})[-:/.](\d{2})[-:/.](\d{2})")


def _chunks(path: Path, wanted=(b"LIST", b"bext")):
    """{chunk id: body} of the wanted chunks, skipping over the sound itself (read by seeking)."""
    out = {}
    with open(path, "rb") as fh:
        head = fh.read(12)
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            return out
        while True:
            h = fh.read(8)
            if len(h) < 8:
                break
            cid, size = h[:4], struct.unpack("<I", h[4:])[0]
            if cid in wanted and size < (1 << 20):
                out.setdefault(cid, fh.read(size))
                fh.seek(size % 2, 1)
            else:
                fh.seek(size + (size % 2), 1)
    return out


def recorded_date(path: str | Path) -> tuple[str, str]:
    """(YYYY-MM-DD, where it came from) from a WAV file's own metadata, or ("", "").

    Looks at the INFO creation date (ICRD, which Lemmatrix writes) and the Broadcast WAV
    origination date (bext, which field recorders and many editors write)."""
    import datetime as _dt
    found = {}
    try:
        chunks = _chunks(Path(path))
    except OSError:
        return "", ""
    body = chunks.get(b"LIST", b"")
    if body[:4] == b"INFO":
        p = 4
        while p + 8 <= len(body):
            key, n = body[p:p + 4], struct.unpack("<I", body[p + 4:p + 8])[0]
            if key == b"ICRD":
                found["ICRD"] = body[p + 8:p + 8 + n].rstrip(b"\x00").decode("utf-8", "replace")
            p += 8 + n + (n % 2)
    bext = chunks.get(b"bext", b"")
    if len(bext) >= 330:
        found["bext"] = bext[320:330].decode("ascii", "replace")
    for source, label in (("ICRD", "the file's creation date (ICRD)"), ("bext", "the recorder's date (bext)")):
        m = _DATE.search(found.get(source, ""))
        if m:
            y, mo, d = m.groups()
            try:
                return _dt.date(int(y), int(mo), int(d)).isoformat(), label
            except ValueError:
                continue
    return "", ""


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a PCM WAV file as mono float samples."""
    with wave.open(str(path), "rb") as w:
        n, rate, width, ch = w.getnframes(), w.getframerate(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(n)
    return _decode(raw, width, ch), rate


def read_segment(path: str | Path, start: float, end: float) -> tuple[np.ndarray, int]:
    """Mono float samples of a stretch of a PCM WAV file (seconds; clipped to the file)."""
    with wave.open(str(path), "rb") as w:
        n, rate, width, ch = w.getnframes(), w.getframerate(), w.getsampwidth(), w.getnchannels()
        a, b = max(0, int(start * rate)), min(n, int(end * rate))
        w.setpos(min(a, n))
        raw = w.readframes(max(0, b - a))
    return _decode(raw, width, ch), rate


def clip_wav(src: str | Path, dst: str | Path, start: float, end: float, artist: str = "",
             date: str = "") -> None:
    """Copy a stretch of a PCM WAV file into a file of its own, as it is (same sample rate, bit
    depth and channels), with the speaker and date in its INFO metadata."""
    with wave.open(str(src), "rb") as w:
        n, rate, width, ch = w.getnframes(), w.getframerate(), w.getsampwidth(), w.getnchannels()
        a, b = max(0, int(start * rate)), min(n, int(end * rate))
        if b <= a:
            raise AudioError("The stretch to cut is empty.")
        w.setpos(a)
        raw = w.readframes(b - a)
    block = ch * width
    fmt = struct.pack("<HHIIHH", 1, ch, rate, rate * block, block, width * 8)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"data" + struct.pack("<I", len(raw)) + raw + (b"\x00" if len(raw) % 2 else b"")
    chunks += _info_chunk({"IART": artist, "ICRD": date})
    blob = b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    tmp.write_bytes(blob)
    tmp.replace(dst)


def duration(path: str | Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate() or 1)


def _decode(raw: bytes, width: int, ch: int) -> np.ndarray:
    if width == 2:
        a = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        ints = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        ints = np.where(ints & 0x800000, ints - 0x1000000, ints)
        a = ints.astype(np.float32) / 8388608
    elif width == 4:
        a = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
    elif width == 1:
        a = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
    else:
        raise AudioError(f"Unsupported sample width: {width}")
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------

class Recorder:
    """Records mono audio from the microphone or from computer audio.

    `level` holds the latest peak (0..1) for a level meter.
    """

    def __init__(self, source: str = "microphone", sample_rate: int = 44100):
        self.source = source
        self.sample_rate = sample_rate
        self.level = 0.0
        self._blocks: list[np.ndarray] = []
        self._stream = None
        self._thread = None
        self._running = False

    def start(self):
        self._blocks = []
        self._running = True
        if self.source == "computer":
            self._start_loopback()
        else:
            self._start_microphone()

    def _start_microphone(self):
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise AudioError(f"Audio isn't available on this computer ({exc}).") from exc

        def callback(indata, frames, time, status):
            block = indata[:, 0].copy()
            self._blocks.append(block)
            self.level = float(np.abs(block).max()) if len(block) else 0.0

        try:
            self._stream = sd.InputStream(samplerate=self.sample_rate, channels=1,
                                          dtype="float32", callback=callback)
            self._stream.start()
        except Exception as exc:  # PortAudio errors have their own types
            self._running = False
            raise AudioError(f"Couldn't start the microphone: {exc}") from exc

    def _start_loopback(self):
        try:
            import soundcard as sc
        except (ImportError, OSError) as exc:
            raise AudioError(f"Recording computer audio needs the 'soundcard' package ({exc}).") from exc
        try:
            speaker = sc.default_speaker()
            mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        except Exception as exc:
            raise AudioError(f"Couldn't find the computer's audio output: {exc}") from exc

        def run():
            with mic.recorder(samplerate=self.sample_rate, channels=1) as rec:
                while self._running:
                    block = rec.record(numframes=self.sample_rate // 20)[:, 0]
                    self._blocks.append(block.astype(np.float32))
                    self.level = float(np.abs(block).max()) if len(block) else 0.0

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self) -> np.ndarray:
        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self.level = 0.0
        if not self._blocks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._blocks)

    @property
    def running(self) -> bool:
        return self._running


# --------------------------------------------------------------------------
# Playback
# --------------------------------------------------------------------------

def load_for_playing(path: Path) -> tuple[np.ndarray, int]:
    """Read a recording, explaining in plain words why if it can't be read."""
    from .storage import is_cloud_only
    cloud = is_cloud_only(path)
    try:
        return read_wav(path)
    except (OSError, EOFError, wave.Error, AudioError, ValueError) as exc:
        if cloud:
            raise AudioError(
                f"{path.name} is stored online only, and it couldn't be downloaded just now "
                "(are you offline?).\n\nTo keep recordings playable without internet, right-click "
                "the sound folder in File Explorer and choose \"Always keep on this device\".") from exc
        raise AudioError(f"Couldn't play {path.name}: {exc}") from exc


class Player:
    """Plays one or more WAV files in turn, in the background."""

    def __init__(self):
        self._stop = threading.Event()
        self._thread = None

    def play(self, paths, on_done=None):
        """Play WAV files in turn. They are read first, so a file that can't be read
        (e.g. online-only while offline) raises AudioError here with the reason."""
        paths = [Path(p) for p in paths if p and Path(p).exists()]
        if not paths:
            self.stop()
            return False
        self.stop()
        sounds = [load_for_playing(p) for p in paths]
        return self._start([lambda s=s: s for s in sounds], on_done)

    def play_samples(self, samples, rate: int, on_done=None):
        """Play samples made by the program (e.g. a pitch rendering)."""
        return self._start([lambda: (samples, rate)], on_done)

    def _start(self, sources, on_done=None):
        self.stop()
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise AudioError(f"Audio isn't available on this computer ({exc}).") from exc
        self._stop.clear()

        def run():
            try:
                for source in sources:
                    if self._stop.is_set():
                        break
                    data, rate = source()
                    sd.play(data, rate)
                    while sd.get_stream().active and not self._stop.is_set():
                        self._stop.wait(0.05)
                    sd.stop()
            finally:
                if on_done:
                    on_done()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
