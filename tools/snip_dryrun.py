# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""✂ auto-snip's dry run (IDEAS.md idea 10, build plan step 4): what auto-snip *would* cut from
each WAV in a folder, without touching them. A tool for setting the margins on real recordings;
nothing in Lemmatrix uses it.

    python tools/snip_dryrun.py FOLDER [OUTPUT_FOLDER]

Prints a table (most cut first) and writes `snip report.csv`; with OUTPUT_FOLDER, also each
snipped take as `<name> (snipped).wav` there, to listen to beside the original. Add `--no-gaps`
to trim the ends only (as for utterances and segments).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from lemmatrix import audio, snip  # noqa: E402


def main(argv):
    gaps = "--no-gaps" not in argv
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    folder = Path(args[0])
    out = Path(args[1]) if len(args) > 1 else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(folder.glob("*.wav")):
        try:
            data, rate = audio.read_any(path)
        except Exception as exc:                       # noqa: BLE001
            rows.append((path.name, 0, 0, 0, f"couldn't read: {exc}"))
            continue
        snipped, rep = snip.snip(data, rate, gaps=gaps)
        rows.append((path.name, rep.length, rep.new_length, rep.length - rep.new_length, rep.describe()))
        if out and rep.changed:
            audio.write_wav(out / f"{path.stem} (snipped).wav", snipped, rate)
    rows.sort(key=lambda r: -r[3])
    with open(folder / "snip report.csv" if not out else out / "snip report.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "seconds", "snipped seconds", "cut", "what"])
        w.writerows([(n, f"{a:.2f}", f"{b:.2f}", f"{c:.2f}", d) for n, a, b, c, d in rows])
    for n, a, b, c, d in rows:
        print(f"{c:6.2f} s  {n}: {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
