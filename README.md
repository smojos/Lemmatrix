# Lemmatrix

A custom linguistics database program specialized for creating and storing human readable
XML paradigm information for phonological and morphological analysis: lemmas with their
tokens (transcriptions, pitch, tags and one recording each). Modelled on how Dekereke
behaves; no Dekereke code is used. The full working spec is in [DESIGN.md](DESIGN.md).

**Status:** first prototype (Stage 1, version 0.1).

## Running it on Windows

1. Pull the latest version in GitHub Desktop.
2. Double-click **`Run Lemmatrix.bat`**.
   The first run creates its own Python 3.13 environment (`py -3.13`) and installs the
   packages, which takes a few minutes. Later runs start straight away.
3. Choose **Open a copy of the sample** to try it with invented data. The copy goes to
   `Documents\Lemmatrix Sample`, so the sample in the repository stays untouched.

4. Once it has run, double-click **`Make desktop shortcut.bat`** to put a Lemmatrix shortcut,
   with its icon, on the desktop and in the Start menu. The shortcut starts Lemmatrix without
   the black console window. If an update needs new packages, it opens `Run Lemmatrix.bat`
   for you to install them first.

On Mac or Linux, run `./run_lemmatrix.sh` instead.

The icon is drawn in `lemmatrix/resources/lemmatrix.svg`; `tools/make_icons.py` makes the
PNG sizes and `lemmatrix.ico` from it (needs `cairosvg` and Pillow).

For heavier testing there's also **`samples/Test-300.xml`**: 300 invented lemmas with about
7,450 tagged forms and no recordings (File → Open). It's rebuilt by
`samples/make_test_database.py`. If you save changes to it, GitHub Desktop will list the file
as changed; discard that change to get the original back.

To run the automated tests, double-click **`Run tests.bat`** (after the first run).

If something goes wrong, a message box shows the details, and they're also written to
`lemmatrix-errors.log` in this folder. Send that to Claude.

## What works in this version

- **Database files:** open, save, save as, new database; backups of the previous version
  in a `Backups` folder beside the database (10 kept); optional autosave.
- **Lemma list:** a filter menu on every column (Show all, Blanks, Non-blanks, Filter for… on
  open fields, Choose… on closed fields), Configure columns, quick search, add / edit /
  delete lemmas, references suggested from the category.
- **The Matrix**, three tabs, each with its own options bar (the bar's height can be dragged):
  - *All data* (the default): one row per token, the same column filters (Tags is a closed
    list with Any / Exactly / No selected), Configure columns, in-place editing, right-click menu.
  - *Lemma/Tag:* the lemma list's lemmas down the side, tag columns (Citation / Exact /
    Loose) across the top; Configure cell, Configure matrix (duplicate a line, Remove all,
    Restore all present), Save / Rename / Delete / Clear matrix.
  - *Tag/Tag:* the selected lemma's paradigm from a configured matrix; contradictory cells
    are greyed out.
  - Tokens matching one cell sit side by side with chips for what they add (e.g. +GEN).
  - Double-click a token to edit it; double-click an empty cell to add one there;
    Delete, Enter, Ctrl+Space (play) and Ctrl+Shift+Space (play the pitch) work on the selected token; the ⇄ button swaps rows and columns.
  - One options row for every tab: Auto-play token soundfile, Show only lemmas with token data.
  - The last view of each database (tab, lemma, matrices) comes back when you reopen it.
- **Token dialogue:** live pitch drawing, tag chips (one per group, defaults pre-selected),
  live file name with its full path, record / stop with a level meter, play, delete recording,
  update file name, Open in Praat, play the pitch (buzz, hum or whistle),
  Back / Next column by column, Ctrl+R, Ctrl+Space, Ctrl+Shift+Space, Alt+← / Alt+→. Recording sets the token's
  speaker and date to the current session's.
- **Pitch notation:** digits are points; each colon lengthens the step between two points
  (`4:42` long high level then a quick fall). A lone digit becomes a short level (`5` → `55`).
- **Notebook:** one page a day, in `<database>.notebook` beside the database: researchers,
  participants and locations, notes (in Charis), the day's comments with links to their
  lemmas and tokens, the day's recordings, and questions (open or resolved). View → Notebook
  (Ctrl+B) or the notepad in the Current Session; the pencil writes the day's session.
  View → Questions lists every question. Add a note for a past day; no future days.
- **Current Session:** researcher, participant and location chips, the speaker (the first
  participant, until another is chosen), the date.
- **Edit menu:** metadata (language, variety, author), Fields (lemma and token fields, open or
  closed, with an XML preview), Lists (researchers, participants with their consent files,
  locations, the closed fields' lists, and the tag structure, where duplicate names and codes
  show in red), and Settings: General (autosave),
  Sound (file-name pattern, sound folder, recording, deleting recordings with their tokens,
  path to Praat), Display (light or dark theme, accent colour for highlights, chips and pitch
  traces, IPA font size), Pitch (display range, playback voice).
- **Bulk edit** (Edit → Bulk edit…, Ctrl+E): a window of its own with a Lemmas tab and a
  Tokens tab, which start with the main window's filters, and a tick on every row. Operations:
  Replace (plain text or a regular expression), Shortcuts (y / j, tie bars on affricates,
  raise or lower pitch), Set value (a field, a tag added or removed, the speaker, the date,
  the word class), Copy and Clear. Preview shows every change in the grid first; any problem
  cancels the whole operation; Apply is one undo step, recordings renamed included.
- **Tags:** one free hierarchy of groups and tags; any tag can go on any token, one per group.
  Groups can be marked "usual for" word classes: the token dialogue shows those first (Show all
  tags for the rest), defaults come from them, and tags outside them get a dashed amber chip
  (Settings → General → Warnings). Databases from before 18 October are upgraded when opened.
- **Export** (File → Export) as CSV: the filtered database (what the current tab shows: All
  data's rows and columns, or the matrix grid) or the entire database (one row per token with
  every lemma and token field). UTF-8, so Excel shows IPA correctly.
- **Undo and redo** for all changes to entries and tokens.

## Not in this version yet

- CV shape filters and everything in the Analyze menu (Stage 2, the analysis engine).
- Unicode tone letters as an alternative pitch display; "Insert character".
- Converting Dekereke databases (Claude will do that with a one-off script).
- Recording has only been tested in the build environment, which has no sound card.
  Microphone and computer-audio recording need checking on a real Windows machine.

## Project layout

```
lemmatrix/            the program
  model.py            entries, tokens, tag structure, people, places (no user interface)
  bulk.py             bulk edit: what an operation would change (no user interface)
  storage.py          reading and writing the XML file, backups
  notebook.py         the notebook: sessions, the record of comments, the .notebook file
  filenames.py        building sound file names from the pattern
  matrix.py           laying out tokens for the paradigm views
  pitch.py            pitch notation
  audio.py            recording, playback and WAV metadata
  defaults.py         default fields, tags and reference categories
  ui/                 windows and dialogues (Qt for Python)
samples/              invented sample database with synthetic recordings
tests/                automated tests
tools/screenshots.py  renders the windows to PNG files, for checking layouts
tools/*.py            one-off conversions of Josh's Dekereke and FLEx data
```
