# Lemmatrix

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23512411.svg)](https://doi.org/10.5281/zenodo.23512411)

*Human readable, machine processable, ethically collected and shared linguistic data.*

Lemmatrix™ is a free, open-source program for phonological and grammatical analysis and
linguistic documentation, for any language. It keeps lemmas with their tokens
(transcriptions, pitch, tags and one recording each), shows them as paradigm matrices, and
holds utterances and texts with their Praat TextGrids, all in readable XML. It is inspired by
tools such as FLEx, Praat, ELAN, Dekereke and Excel; no code from any of them is used.

**Status:** prototype (Stage 1, version 0.2).

## Your data, and your own work

Lemmatrix keeps two kinds of thing apart, and the difference runs through the whole program.

- **The data** is what you collected and what describes it: lemmas and tokens with their
  recordings, utterances, texts with their TextGrids, the fields, tags and lists that describe
  them (your tone classes, word classes, reference categories), the metadata, and the consent
  ticks that say how it may be shared. It lives in the database file and its soundfiles, and it
  is what you archive and share: *ethically collected and shared*.
- **Your own work** is what you make of the data: the notebook's notes, questions and To Dos,
  your Cogitate hypotheses with the evidence for and against them, your workspace, and later the
  results of the Analyze tools and the papers you Compose. These are your academic ideas and your
  private property, not data for public sharing.

Both are on screen together (that is the point), but they are stored apart. **File → Full
backup** keeps everything, for you. **File → Export → Ethical archive** and **Anonymous
archive** share the data only: the notebook stays out unless you tick it in, and the workspace
goes blank. Others can look at your archived data and come to their own conclusions; they don't
get to piggyback on your unpublished thoughts. The **Ethical archive** names only the people
ticked *Identifiable?* and carries only the recordings of speakers who agreed to audio sharing,
as their consent forms allow; the **Anonymous archive** names nobody at all (codes renumbered, no
recordings), and is the one to use when you ask an AI for help with your data.

© 2026 Joshua A. G. Smolders. Free software under the
[GNU Affero General Public License, version 3 or later](LICENSE) (AGPL-3.0-or-later), with
[additional terms](NOTICE.md); the artwork is [all rights reserved](ARTWORK.md).

**Free, always.** Lemmatrix is free to download and use, at no charge, and it always will be.
Get it from its official homes: this repository, or Zenodo
([10.5281/zenodo.23512411](https://doi.org/10.5281/zenodo.23512411)).

**Order is the computer's job.** In other programs I had to rename soundfiles by hand, or open up the XML in Notepad++ to reorder examples by hand, so my OCD wasn't triggered knowing they were underlyingly out of order. Linguists should not have to waste time and energy bringing order to their data when computers can do it for them.
Lemmatrix names your soundfiles from your data and renames them when it changes, and keeps your
lemmas in order for you.

## About

Lemmatrix is an independent, personal open-source project by Joshua A. G. Smolders,
developed on personal time and equipment and at personal expense. It is not a deliverable of
any employer, funder or institution. It grew out of needs from many years of linguistic
fieldwork, and is free for anyone to use, share and change under its licence.

The author designs and specifies Lemmatrix and tests it; the code is written with an AI
coding assistant (Claude, by Anthropic) under his direction. The graphics and icons are his
own: the program icon and the splash screen are his drawings, and the icons in the program
are drawn in code from his designs and drafts. See [AUTHORS](AUTHORS), and
[DESIGN.md](DESIGN.md) for how the program works and why.

In the author's words: *“One of the main goals of this program is to make the UI extremely versatile and user friendly, for those linguists who are a little more on the artistic end of the spectrum like myself.”*

(A note on spelling: these documents write *soundfile* and *soundfiles* as one word. That's
deliberate, part of the author's personal campaign to make it a compound, like *filename*.)

## Running it on Windows

1. Download this repository, or clone it (e.g. with GitHub Desktop) and pull the latest version.
2. Double-click **`Run Lemmatrix.bat`**.
   The first run creates its own Python 3.13 environment (`py -3.13`) and installs the
   packages, which takes a few minutes. Later runs start straight away.
3. Choose **Open a copy of the sample** to try it with invented data: a made-up language
   (LXX) with 98 lemmas, saved matrices and synthetic recordings, built by
   `samples/make_sample.py`. It isn't a real language; any resemblance to one is coincidental. The copy goes to
   `Documents\Lemmatrix Sample`, so the sample in the repository stays untouched.

4. Once it has run, double-click **`Make desktop shortcut.bat`** to put a Lemmatrix shortcut,
   with its icon, on the desktop and in the Start menu. The shortcut starts Lemmatrix without
   the black console window. If an update needs new packages, it opens `Run Lemmatrix.bat`
   for you to install them first.

On Mac or Linux, run `./run_lemmatrix.sh` instead.

The icon is drawn in `lemmatrix/resources/lemmatrix.svg`; `tools/make_icons.py` makes the
PNG sizes and `lemmatrix.ico` from it (needs `cairosvg` and Pillow).

**ɛλicit** (remote elicitation, stage 1) has its own test database: **File → Open a copy of the
ɛλicit test database** opens a little Italian, with Danish as the second gloss language
(`samples/Elicit test`, built by `samples/make_elicit_test.py`; each lemma's Comment says how to
ask for it). The ɛλicit button, left of Texts and utterances, makes a request: a zip to send to a
speaker with a link to the web page in `docs/elicit/`, served by GitHub Pages at
<https://smojos.github.io/Lemmatrix/elicit/> (Settings → Pages → Deploy from a branch → `main`,
`/docs`). The speaker records on their phone or computer and sends the recordings back as a zip;
**Receive ɛλicitation** reviews them. No soundfile goes through GitHub: the page is only the page,
and the recordings stay on the speaker's device until they send them.

For heavier testing there's also **`samples/Test-300.xml`**: 300 invented lemmas with about
7,760 tagged forms and no recordings (File → Open). It's rebuilt by
`samples/make_test_database.py`. If you save changes to it, GitHub Desktop will list the file
as changed; discard that change to get the original back.

To run the automated tests, double-click **`Run tests.bat`** (after the first run).

If something goes wrong, a message box shows the details, and they're also written to
`lemmatrix-errors.log` in this folder. Include it when you report a problem. If Lemmatrix
ever closes by itself with no message, `lemmatrix-crash.log` in this folder says where it was
(it holds only the last run, so send it before starting Lemmatrix again).

## What works in this version

- **Database files:** open, save, new database; backups of the previous version in a
  `Backups` folder beside the database (10 recent, and older ones spread out in time); autosave.
- **Folder layout:** each database has a main folder of its own, laid out like this:

  ```
  Main folder/
  ├─ <database>.xml           the data
  ├─ <database>.notebook      your own work: notes, questions, To Dos, hypotheses
  ├─ <database>.workspace     what you are working on: saved matrices, filters, the session
  ├─ Soundfiles/Tokens/       the tokens' recordings
  ├─ Backups/                 the automatic backups
  ├─ Documentation/           consent forms and other documentation
  └─ Exports/                 where File → Export starts
  ```

  Consent forms moved into Documentation are found by name and relinked. **File → Full
  backup** saves the whole main folder as one dated zip (e.g. to a cloud folder or another
  drive, set in Settings → General); a reminder comes once the last one is a week old.
- **Utterances** (View → Texts and utterances, Ctrl+U): one-off sentences and phrases with no
  lemma, each with one reference (U Unorganised; W, X, Y, Z of your own), one transcription and
  one recording. Add (record on the spot), Import… or drag WAV files onto the grid (copied into
  `Soundfiles/Utterances`); a grid like All data; an utterance dialogue with its file label,
  tags (groups can be marked "utterances only") and links to lemmas.
- **Texts and songs** (the Texts tab of the same window): a catalogue record (title, genre,
  transcription status, date, people, places) with its recording and Praat TextGrid, copied into
  `Soundfiles/Texts`. The lines are read from the TextGrid with a tier mapping (Edit → Lists →
  Tier mapping; tx, ge, ft by default); a line can be played, played in context, opened in Praat
  with its TextGrid, or clipped as an utterance (its stretch of the recording and its text).
- **Comparative wordlists:** **New database** starts empty or from one of three lists: the
  **Extended African Comparative Wordlist** (EACW, recommended: 2,556 items, 2,281 of them in its
  published list), the **SIL Comparative African Wordlist** (CAWL, 1,700) or the **Swadesh list**
  (207). The EACW comes as its base list or expanded with its hidden items, and global, for all of
  Africa or for one region (North, West, East, South, Central); its lemmas get the list's
  Clarification and Taxon, and its hidden items stay within reach (hover over a reference to see
  them, right-click → Insert EACW items… to add them). The list a database starts from gives its
  references; every lemma also carries the other two lists' numbers, hidden (they're in the
  database file and the Reference column's hover). Type `CAWL 345`, `SWADESH 42` or just `SWADESH`
  in the lemma list's search to find them, and **File → Export → Wordlist…** gives any of the three
  as a plain list (number, lemma, gloss) to the clipboard or a PDF, every item in the list's order,
  matching lemmas of your own by their gloss. **Tools → Link to wordlists…** links an existing
  database whose references are EACW numbers, and **Tools → Convert references from a table…**
  renumbers a database from a conversion map of your own.
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
  The notebook is your own: it goes into every Full backup but into no archive unless you choose.
- **Current Session:** researcher, participant and location chips, the speaker (the first
  participant, until another is chosen), the date.
- **Edit menu:** metadata (language, variety, author), Fields (lemma and token fields, open or
  closed, with an XML preview), Lists (researchers, participants with their consent files,
  locations, the closed fields' lists, and the tag structure, where duplicate names and codes
  show in red), and Settings: General (autosave, the full backup folder, warnings),
  Sound (file-name pattern, recording, deleting recordings with their tokens,
  path to Praat), Display (light or dark theme, accent colour for highlights, chips and pitch
  traces, IPA font size), Pitch (display range, playback voice).
- **Bulk edit** (Edit → Bulk edit…, Ctrl+E): a window of its own with a Lemmas tab and a
  Tokens tab, which start with the main window's filters, and a tick on every row. Operations:
  Replace (plain text or a regular expression), Shortcuts (y / j, tie bars on affricates,
  raise or lower pitch), Set value (a field, a tag added or removed, the speaker, the date,
  the word class), Copy, Clear, and Predict (fills empty English translations with their
  suggestions). Preview shows every change in the grid first; any problem
  cancels the whole operation; Apply is one undo step, recordings renamed included.
- **Predicted translations:** an empty English translation in the token dialogue shows a
  suggestion in grey italics, learned from the other tokens with the same tags ("your father"
  for father gives "your mother" for mother; "goats" gives "men" for man). → accepts it;
  typing replaces it. The tooltip says what it's based on. All data shows the suggestions in
  its empty Translation cells too, in light grey italics (double-click and →, or right-click →
  Accept suggested translation). Works offline (lemminflect).
- **Spelling:** English glosses and translations get a red wavy line under words that may be
  misspelled (token and lemma dialogues, lemma list, All data); right-click for corrections or
  to add the word to the database's own word list. Tools → Check spelling (F7) lists every
  such word, with Replace everywhere, Ignore and Add to word list. Codes in capitals, words in
  brackets and transcriptions aren't checked. Settings → General → Warnings turns the lines off.
- **Tags:** one free hierarchy of groups and tags; any tag can go on any token, one per group.
  Groups can be marked "usual for" word classes: the token dialogue shows those first (Show all
  tags for the rest), defaults come from them, and tags outside them get a dashed amber chip
  (Settings → General → Warnings). Databases from before 18 October are upgraded when opened.
- **Export** (File → Export) as CSV: the filtered database (what the current tab shows: All
  data's rows and columns, or the matrix grid) or the entire database (one row per token with
  every lemma and token field). UTF-8, so Excel shows IPA correctly.
- **Archives** (File → Export): the **Ethical archive** (the data as the consent forms allow:
  identifiable people named, only recordings whose speaker agreed to audio sharing) and the
  **Anonymous archive** (nobody named, every code renumbered, no recordings; for showing your
  setup, or for AI). Both leave your notebook out by default and write a blank workspace; the
  consent forms can travel in a password-protected zip. Researchers and participants have an
  *Identifiable?* tick in Edit → Lists (ticked for a new researcher, not for a new participant).
- **Undo and redo** for all changes to entries and tokens.

## Not in this version yet

- CV shape filters and everything in the Analyze menu (Stage 2, the analysis engine).
- Unicode tone letters as an alternative pitch display; "Insert character".
- Importing from other programs (Dekereke, FLEx) and LIFT or SFM export.
- Recording has only been tested in the build environment, which has no sound card.
  Microphone and computer-audio recording need checking on a real Windows machine.

## Project layout

```
lemmatrix/            the program
  model.py            entries, tokens, tag structure, people, places (no user interface)
  bulk.py             bulk edit: what an operation would change (no user interface)
  predict.py          predicted translations: templates learned from the translations
  spelling.py         English spelling: the word lists, corrections, the database's own words
  storage.py          reading and writing the XML file, backups
  layout.py           the main folder's fixed layout, consent relinking, full backups
  notebook.py         the notebook: sessions, the record of comments, the .notebook file
  anonymise.py        the Ethical and Anonymous archives: the data to share, without your own work
  filenames.py        building soundfile names from the pattern
  elicit.py           ɛλicit: requests, the recordings coming back, the review (elicit_prompts.py: the
                      web page's prompts in each language; elicit_art.py: Josh's ɛλicit drawings)
  matrix.py           laying out tokens for the paradigm views
  pitch.py            pitch notation
  audio.py            recording, playback and WAV metadata
  defaults.py         default fields, tags, lists, people, places and reference categories
  wordlists/          the comparative wordlists (EACW, CAWL, Swadesh) and their mapping
  resets.py           Reset to defaults in Edit → Lists (keeps what is in use)
  tagdefs.py          descriptions of the default tags, with their sources
  ui/                 windows and dialogues (Qt for Python)
samples/              invented sample database with synthetic recordings; the ɛλicit test database
docs/elicit/          ɛλicit's web page (GitHub Pages), where speakers record
tests/                automated tests (tests/data: the prototype's sample, used by the feature tests)
tools/screenshots.py  renders the windows to PNG files, for checking layouts
tools/make_elicit_web.py  the web page's favicon, logo and home-screen icons
LICENSE               the GNU Affero General Public License, version 3
NOTICE.md             the additional terms: the author's credit, marked changes, the name
ARTWORK.md            the icons, splash screen and ɛλicit drawings: all rights reserved
AUTHORS, CITATION.cff who made Lemmatrix and how to cite it
THIRD-PARTY.md        the libraries Lemmatrix uses, with their licences
```

## Support

Questions, bugs and suggestions: **lemmatrix.support@gmail.com**, or an issue at
<https://github.com/smojos/Lemmatrix/issues>. (Help → About Lemmatrix has the address too.)

## Acknowledgements

**Rod Casali**, professor and friend, for his years of dedicated work coding Dekereke and for
helping me through accommodating so many of my requested feature updates. I am unworthy to be counted among great men like
him; Lemmatrix was only possible for me through advances in AI.

**Larry Hayashi**, for teaching me FLEx and field methods so long ago, and for helping me
navigate them ever since.

**Keith Snider**, my mentor and friend, for teaching me about tone and inspiring a love for it.

The developers of **FLEx**, **ELAN**, **Dekereke**, **Praat** and even **Microsoft Excel**, whose tools
shaped how I work and what I wanted Lemmatrix to be.

The countless linguists who built into me over the years and helped me to learn this craft, 
and from whom I gleaned ideas, sometimes without knowing it at the time.
They include, but are not limited to (in alphabetical order): Adam Werle, Ahmed Sosal, Andreas Joswig, Anne-Christie Hellenthal, Bert Remijsen, Bruce Wiebe, Chuck Murphey, Colleen Ahland, Don Killian, Doris Payne, Giorgia Zantei, Helen Eaton, Jamon Pelkey, Jeroen van Ravenhorst, Jim Roberts, Justin Goldberg, Kent Rasmussen, Klaus-Christian Küspert, Love Lee, Manuel Otero, Michael Ahland, Mirella Blum, Nate Bremer, Sean Smith, Steve Nicolle, Theis Greve, Thomas Blecke, Tim Stirtz, Virginia Beavon-Ham.

The **Opo** people, for years of fieldwork in a real language that gave me a linguist's
intuition.

My non-linguist friends and colleagues, who fill my life with purpose, support and meaning.
They include (in alphabetical order, by first name): Adam Yates, Baruach Goaner, Chris Wilson, Enguday Abebew, Girma Degefew, Jared Phillips, Jeremy Johnson, Jonny Shaw, Josh Bourget, Josh Rigby, Kura Lul, Mark Dueck, Otapa Luk, Rob Bustin, Tola Dec.

The many people who supported my work in **SIL** for years and years, who believed in me,
and who gave me the means to live and work in Ethiopia.

**My mother**, for loving me unconditionally, and for being a foundation when life is difficult.

Finally, my wife **Jennifer**, without whom I would be nothing. The default colour of
Lemmatrix, its teal (#198583), belongs to her forever, as a symbol that she underlies
everything I do. And our four children.

## Licence

Lemmatrix is free software: you can redistribute it and/or modify it under the terms of the
GNU Affero General Public License as published by the Free Software Foundation, either version
3 of the License, or (at your option) any later version. It is distributed in the hope that it
will be useful, but **without any warranty**; without even the implied warranty of
merchantability or fitness for a particular purpose. See [LICENSE](LICENSE) for the details.
(Versions 0.1.0 to 0.1.2 were released under the GNU General Public License, version 3 or later.)

**Additional terms** ([NOTICE.md](NOTICE.md), under the licence's section 7): any copy or
modified version keeps the line *Based on Lemmatrix by Joshua A. G. Smolders
(https://doi.org/10.5281/zenodo.23512411)* in its About screen and README; a modified version
says that it has been changed; and it takes a name of its own.

**The artwork is not under the AGPL.** The icons, the splash screen and the ɛλicit drawings are
© Joshua A. G. Smolders, all rights reserved ([ARTWORK.md](ARTWORK.md)). Lemmatrix may be shared
as it is, artwork included; anyone who distributes a modified version must make their own icons
and splash screen for everything.

**The Extended African Comparative Wordlist is CC BY 4.0.** The EACW that new databases can
start from (`lemmatrix/wordlists/eacw.tsv`, with its links to the SIL Comparative African
Wordlist and the Swadesh list) is data, not code: © Joshua A. G. Smolders, under the Creative
Commons Attribution 4.0 licence, so anyone may reuse it, in other wordlists and compilations too,
with credit ([LICENSE-EACW.md](lemmatrix/wordlists/LICENSE-EACW.md)).

**The name.** Lemmatrix™, its alternative spelling λemmatriχ™ (with an initial lambda and a final
chi) and ɛλicit™ are trademarks of Joshua A. G. Smolders. Modified versions
must use a different name.

The libraries Lemmatrix uses keep their own licences: see [THIRD-PARTY.md](THIRD-PARTY.md).

## Citing Lemmatrix

Smolders, Joshua A. G. 2026. *Lemmatrix* (version 0.2.0). Zenodo.
https://doi.org/10.5281/zenodo.23512411

This DOI always points to the latest version. Each version also has its own DOI on Zenodo,
listed on the record's page, for citing the exact one you used (0.2.0:
[10.5281/zenodo.23606293](https://doi.org/10.5281/zenodo.23606293)).

See also [CITATION.cff](CITATION.cff) (GitHub's "Cite this repository" button uses it).

## References

- Dixon, R. M. W. 2010. *Basic Linguistic Theory*, Vol. 1: *Methodology*. Oxford: Oxford
  University Press. The default reference categories (A Human body … V Verbs) are inspired by
  p. 296. They are the categories of the Extended African Comparative Wordlist.
- Smolders, Joshua. 2026. *The Extended African Comparative Wordlist: A lexical organization system for field linguists.* The wordlist Lemmatrix's
  reference categories come from, inspired by Dixon (2010), Snider & Roberts (2006) and Swadesh
  (1952, 1955).
- Snider, Keith & James Roberts. 2006. *SIL Comparative African Wordlist (SILCAWL).* SIL
  Electronic Working Papers 2006-005. Dallas: SIL International. (First published in *Journal of
  West African Languages* 31(2): 73–122.)
- Swadesh, Morris. 1952. Lexico-statistic dating of prehistoric ethnic contacts. *Proceedings of
  the American Philosophical Society* 96(4): 452–463.
- Swadesh, Morris. 1955. Towards greater accuracy in lexicostatistic dating. *International
  Journal of American Linguistics* 21(2): 121–137. Lemmatrix's Swadesh list is the 207-item list
  combining his 100- and 200-word lists.
