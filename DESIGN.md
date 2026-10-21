# Lemmatrix: Design Notes

*The design of Lemmatrix: how the program works and why, with each decision dated as it was made. Lemmatrix is © 2026 Joshua A. G. Smolders, free and open source under GPL-3.0-or-later (see `LICENSE`).*

---

## 1. What we're building

- **Lemmatrix** is a program for phonological and grammatical analysis and linguistic documentation (any language), built from scratch and inspired by tools such as FLEx, Praat, ELAN, Dekereke and Excel. **No code from any of them is reused.**
- **Licence:** free and open source under the GNU General Public License, version 3 or later (GPL-3.0-or-later), © 2026 Joshua A. G. Smolders. See `LICENSE`, `AUTHORS` and `THIRD-PARTY.md`.
- **Terminology:**
  - The basic unit is a **database**, not a "lexicon".
  - Each entry is organised under a **lemma** (not "headword").
  - The right-hand view of tokens is the **matrix view**.
  - **soundfile** and **soundfiles**, always one word (like *filename*), in the program, its messages, comments and documentation (Josh, 20 October). `tests/test_terms.py` fails if it is ever written as two words.
- **Why a new program?** Other tools which I previously used had either limited or unideal functionality, with constant import and export stages creating scattered files, databases and analyses. I found that FLEx was too slow in navigation and filtering for efficient data collection, relied too much on hand editing, its XML output was not human readable, its auto-recorded soundfiles were not easily readable updatable or searchable, and its text analysis could not interact directly with soundfiles. Praat TextGrids are too sensitive when editing, extremely reliant on hand editing, and could not communicate between texts. Dekereke's data model is flat (one row per record), its pitch transcription relies on a font rather than hard underlying data, it cannot handle multiple paradigms in elicitation in a single database without great effort, and it could not interact with text data. All of these were disconnected from each other, and from the notes and questions arising from the various analyses. The core goal here is a two-level model, with lemmas and tokens beneath them, stored as readable XML without repeated data, completely searchable and smartly bulk editable, with all the analysis and export tools a linguist could hope for. In addition it is meant to organize texts and bring them to bear in lexical and grammatical analysis, all while recording the whole process and ensuring modern ethical standards are being employed.
- **Platforms:** Windows first, then Mac and Linux, because colleagues use both.
- **Audience:** field linguists. Free to use, share and change under the licence.

## 2. Technology and setup

- **Language:** Python 3.13 with Qt for Python (PySide6 6.12). It was chosen because it runs on all three platforms, is the most readable option for a non-programmer, and can be fully built and tested in Claude's workspace, including screenshots of the windows.
- **Audio:** `sounddevice` / `soundcard` for recording and playback, including capturing computer audio on Windows.
- **English inflection:** `lemminflect` (MIT licence, offline) for predictive translation (section 5.9).
- **English spelling:** `pyspellchecker` (MIT licence, offline) together with `lemminflect` (section 5.10).
- **Acoustic analysis (later):** `parselmouth` (Praat in Python). It's GPL-licensed, which fits Lemmatrix's own licence.
- **Fonts:** Charis SIL. Tone letters render as contours, with the staves hidden through the font's `cv92` feature. This was tested and works in Qt.
- **Running it on Windows:** `Run Lemmatrix.bat` creates the program's own Python 3.13 environment with `py -3.13` (a plain `python` may be an older version) and installs the packages on the first run.
- **Development:** the author designs and specifies Lemmatrix and tests every version on his own data; the code is written with an AI coding assistant (Claude, by Anthropic), which also writes and runs the automated tests. The code is kept on GitHub and pulled with GitHub Desktop.
- **Data safety:** readable XML, version history, and automated tests (especially for import and save).

## 3. Data design

### File layout

```xml
<?xml version="1.0" encoding="utf-8"?>
<database format="6">
  <metadata>
    <language code="LXX">Sample language</language>
    <variety code="VXX">…</variety>          <!-- one variety per database -->
    <name>Complete Lexicon</name>            <!-- the database's own name (not the file name) -->
    <author>…</author>                       <!-- who owns the database -->
    <researcher code="JS" name="Joshua A. G. Smolders" email="…">description</researcher>
    <participant code="SP1" name="…" consent="Consent/SP1" identifiable="yes" audio-sharing="yes">description</participant>
    <location name="Ethiopia" code="ET">        <!-- nested: country > region > village -->
      <description>…</description>
      <location name="Pade" code="PADE"/>
    </location>
    <description>…</description>
  </metadata>

  <settings>
    <entry-fields>
      <field name="Lemma"/>
      <field name="WordClass"      label="Word Class"      role="word-class" closed="yes">  <!-- built in -->
        <item name="NOUN"><item name="Relational"/></item>  <!-- a list like any other; can nest -->
        <item name="VERB"/> …
      </field>
      <field name="ToneClass"      label="Tone Class"      list="yes"/>
      <field name="InflectionClass" label="Inflection Class" list="yes"/>
      <field name="Comment"/>
    </entry-fields>
    <token-fields>
      <field name="Phonetic" role="phonetic"/>
      <field name="Phonemic" role="phonemic"/>
      <field name="Morphemes" role="morphemes"/>    <!-- the morpheme glosses, under Phonemic (format 4) -->
      <field name="Pitch"    role="pitch"/>
      <field name="Comment"/>
    </token-fields>
    <text-fields>                                <!-- texts' own fields (section 3.11) -->
      <field name="Title" role="title"/>
      <field name="Genre" role="genre" closed="yes"> <item name="narrative"> <item name="folktale"/> … </item> … </field>
      <field name="Status" label="Transcription status" role="status" closed="yes"> … </field>
      <field name="Description"/>
      <field name="Comment"/>
    </text-fields>
    <tier-mapping main="tx">                     <!-- which TextGrid tier fills which field -->
      <tier name="tx" field="Phonetic"/>
      <tier name="ge" field="Morphemes"/>
      <tier name="ft" field="Translation" lang="en"/>
      <tier name="mb" field=""/>                 <!-- ignored -->
    </tier-mapping>
    <glosses languages="en ar" primary="en"/>

    <tag-structure>                              <!-- one free hierarchy; groups nest to any depth; order = tag order -->
      <group name="NOUN" usual="NOUN">           <!-- "usual for": a hint, inherited by subgroups (section 3.3) -->
        <group name="Number">
          <tag name="Singular" code="SG"/>
          <tag name="Plural"   code="PL"/>
        </group>
        <group name="Case">
          <tag name="Nominative" code="NOM"/>
          <tag name="Genitive"   code="GEN"/>
          <!-- … -->
        </group>
      </group>
      <group name="VERB" usual="VERB">
        <!-- … Subject, Object … -->
        <group name="Stem">
          <tag name="Simple" default="yes"/>     <!-- group default: a real tag, but no file-name code -->
          <tag name="Passive" code="PASS"/>
          <!-- … -->
        </group>
        <!-- … Tense, Aspect, Mood, Polarity … -->
      </group>
      <group name="Phonological">                <!-- no hint: usual for every lemma -->
        <group name="Following tone">
          <tag name="before H" code="xH"/>
          <tag name="before L" code="xL"/>
        </group>
        <group name="Preceding tone"> … </group>
      </group>
      <group name="Syntactic"> … </group>
      <group name="Instances">                   <!-- always last in tag order -->
        <group name="Frames">
          <tag name="Frame 1" code="F1"/>          <!-- … Frame 2 = F2 -->
        </group>
        <group name="Examples">
          <tag name="Example 1" code="x1"/>        <!-- … Example 2 = x2 (lowercase: a non-linguistic gloss) -->
        </group>
      </group>
    </tag-structure>

    <references scheme="categories" digits="3">
      <category letter="A">Human body</category>
      <!-- … full default list in section 3.4 … -->
      <category letter="Q" numbering="manual">Quantifiers</category>
      <category letter="R" numbering="manual">Pronouns</category>
      <category letter="U" for="utterances">Unorganised</category>   <!-- … W, X, Y, Z -->
      <category letter="T" for="texts">Texts</category>                 <!-- S: Songs -->
    </references>

    <!-- no folder: recordings are always in Soundfiles/Tokens (section 3.9) -->
    <sounds pattern="{language}-{variety}-{speaker}_{reference}_{gloss}_{tags}"
            utterance-pattern="{language}-{variety}_{reference}_{label}"
            text-pattern="{language}-{variety}_{reference}_{title}" clip-padding="100"
            tag-separator="-"
            auto-update-names="yes"/>
    <pitch display-range="1-5" style="contours"/>
    <playback play-cell-on-click="no"/>
    <analysis syllabification="sonority" syllabic-nasals="yes" ignore=")(" …/>
    <spelling>                                 <!-- the spellcheck's own words (section 5.10); only if any -->
      <word>Pade</word>
    </spelling>
    <display> … field order, widths, fonts and sizes, saved views … </display>
  </settings>

  <entry ref="D001" file-gloss="goat">
    <Lemma>dʌ́ʌm</Lemma>
    <Gloss lang="en">goat</Gloss>
    <Gloss lang="ar">ماعز</Gloss>
    <WordClass>NOUN</WordClass>
    <ToneClass>H</ToneClass>

    <token speaker="SP1" collected="2026-10-16"
           file="LXX-VXX-SP1_D001_goat.wav">              <!-- citation token: no tags -->
      <Phonetic>dʌːm</Phonetic>
      <Phonemic>dʌ́ʌm</Phonemic>
      <Pitch>5:5</Pitch>
      <Translation lang="en">goat</Translation>
    </token>
    <token tags="Plural" speaker="SP1" collected="2026-10-16"
           file="LXX-VXX-SP1_D001_goat_PL.wav">
      <Phonetic>dʌːmã</Phonetic>
      <Phonemic>dʌ́ʌmà</Phonemic>
      <Pitch>5:5 11</Pitch>
      <Translation lang="en">goats</Translation>
    </token>
    <token tags="Plural, 1SG.POSS" speaker="SP1" collected="2026-10-16"
           file="LXX-VXX-SP1_D001_goat_PL-1SG_POSS.wav" id="9f2c41d0ab">
      <Phonetic>mɪdʌːmã</Phonetic>
      <Pitch>11 5:5 11</Pitch>
      <Translation lang="en">my goats</Translation>
      <Comment changed="2026-10-17">…</Comment>  <!-- the day the comment was last changed -->
                                   <!-- rerecord="yes" on a token: flagged to be recorded again -->
    </token>
  </entry>

  <utterances>                                   <!-- format 5: one-off sentences, no lemma (section 3.10) -->
    <utterance ref="W001" file-label="lion house" lemmas="45e08111f1" id="…">
      <token tags="Relative clause" speaker="SP1" collected="2026-10-18"
             file="LXX-VXX_W001_lion_house.wav" id="…">
        <Phonetic>ŋɔːɲ kʷʊːn</Phonetic>
        <Morphemes>lion house</Morphemes>
        <Translation lang="en">the lion's house</Translation>
      </token>
      <source text="…the text's id…" start="0.5000" end="1.5000" modified="2026-10-18T20:00:00">
        <copied tier="tx">ŋɔ́ɔɲ kʊ̀ʊn</copied>        <!-- what was copied from each tier, for Pull -->
        <copied tier="ft">the lion's house</copied>
      </source>
    </utterance>
  </utterances>

  <texts>                                        <!-- format 6: texts and songs (section 3.11) -->
    <text ref="T001" file-label="Hyena and Hare" date="2026-10-18" participants="SP1" researchers="JS"
          locations="PADE" file="LXX-VXX_T001_Hyena and Hare.wav"
          textgrid="LXX-VXX_T001_Hyena and Hare.TextGrid" id="…">
      <Title>Hyena and Hare</Title>
      <Genre>folktale</Genre>
      <Status>translated</Status>
      <!-- <tiers main="…"> … </tiers>: the text's own mapping, if it differs from the database's -->
    </text>
  </texts>
</database>
```

### 3.1 General rules

- **Metadata:** stored as real elements, not XML comments. Elements survive saves, can be edited in a form and can be exported. Each database has **one language** and **one variety** (optional), each with a code, an **author** (owner), and three lists: **researchers** and **participants** (code, name, description; participants also a **consent file**, the document of informed consent, kept relative to the database's folder when it is inside it), and hierarchical **locations** (name, code, description). **Since 20 October** (for ɛλicit, IDEAS.md idea 19): researchers have an **email** (where a request's notice goes), and participants two ticks, **Identifiable?** and **Audio sharing?**, ticked only when the consent form explicitly agrees to them (`identifiable="yes"`, `audio-sharing="yes"`; not written when unticked). No contact details are kept for participants. Names are optional and can be stripped on export for sharing. Older files' single `<researcher>` is read as the author. **A new database starts with placeholders** (20 October), to be edited: researchers RS1 and RS2, participants SP1 and SP2, and the places Canada (CA) › British Columbia (BC) › Ucluelet (UCL-V) and Ethiopia (ET) › Gambella Regional State (GBRS) › Pade (PADE; not a known location, any resemblance is coincidental).
- **Ids:** every entry and token has a short `id`. Notebook links point at it, so they survive changes to references and tags. Files without ids get them when opened; copies with the same id are given new ones.
- **Variety is database-level for now.** Comparing varieties (e.g. cognates across dialects) is left for later. If tokens ever get their own variety, a token without one takes the database's, so databases made now keep working.
- **Open on another computer:** while a database is open, Lemmatrix keeps a small hidden marker file next to it (`.<file name>.lemmatrix-lock`) with the computer, user, when it was opened and when Lemmatrix last checked in (every 5 minutes). OneDrive syncs it, so opening the same database on another computer warns, with **Open anyway** or **Don't open**. The marker goes when the database is closed. A marker left by a crash on the same computer is noticed and replaced quietly; from another computer, "last active" shows whether it's stale.
- **Settings:** stored in the data file, not in a separate file as Dekereke does. The only exceptions are per-computer preferences: paths to programs (e.g. Praat) and the remembered session (section 3.6).
- **Elements and attributes:**
  - Elements hold linguistic content.
  - Attributes hold identity, tags, dates and file names.
  - Empty fields are not written.
- **Encoding:** UTF-8, with Unicode normalised (NFC). Characters that look identical then match in searches and file names.
- **Format version:** the `format` number says which layout of the file this is. **Until version 1.0, Lemmatrix reads only the current format** (18 October): there is no compatibility code for older formats yet. When the format changes, a provisional upgrade from the format before is written, and taken out again once the databases in use have been saved in the new format. Format 6 is the current one: the free tag hierarchy, Instances (Frames, Examples), the fixed folder layout, the Morphemes token field, utterances and texts (sections 3.3, 3.9, 3.10, 3.11). Its provisional upgrade from format 5 adds the T and S categories, the text fields and the tier mapping, and makes the Example codes lowercase. From version 1.0, every older format will be upgraded automatically.
- **Characters XML can't hold** (control characters, e.g. the line break Word puts on the clipboard for Shift+Enter) never reach the file: they are taken out on saving (Word's line breaks become a space, or a new line in the notebook). A file that already has them (from an older version) is repaired on opening, with a note; saving writes the repaired file.

### 3.2 Entries and tokens

- **Entry identity:** the `ref` attribute uniquely identifies each entry.
- **Entry fields:** plain text. **Lemma** is the main entry field. Lemma-level analysis is limited to the lemma list's CV shape filter (section 5.1).
- **Class fields** on every new database:
  - **Word Class** (built in): a closed field with its own list, hierarchical like any other (NOUN › Relational › Kinship). It doesn't restrict tags: it is what the tag groups' "usual for" hints refer to (section 3.3), which is why the field can be renamed but not deleted. Defaults: NOUN, VERB, PRONOUN, QUANT, ADJECTIVE, ADVERB.
  - **Tone Class** and **Inflection Class**: ordinary closed fields (below), renamable and deletable. Their lists start as Tone Class H, L, LH, HL, and Inflection Class Nominal › I, II and Verbal › I, II (20 October; values are stored by name, so the word class tells a noun's I from a verb's I).
  - More class fields can be added.
- **Open and closed fields.** Every lemma or token field is one or the other, chosen when it's created:
  - **Open:** free text, filtered with "Filter for…" (section 5.2).
  - **Closed:** values come from a list kept in settings under the field's name (e.g. Tone Class: H, L, LH, HL). The list can be hierarchical and is edited like the tag structure. Closed fields are filtered with "Choose…". Word Class is closed. Tags count as closed.
- **Edit → Fields** adds, renames, deletes and reorders fields, in one dialogue with two separate lists, **Lemma fields** and **Token fields**; a field belongs to exactly one. A live **XML preview** beside the lists shows one example entry with one token, each field filled with dummy text named after it (e.g. `<ToneClass>ToneClass</ToneClass>`), updating as fields change.
- **Core fields can't be deleted** (19 October, IDEAS.md idea 9): Lemma, Gloss, Word Class, Phonetic, Phonemic, Morphemes, Pitch, Translation and Comment (on lemmas, tokens and texts), and texts' Title, Genre and Status, because other features depend on them. They can be renamed (their Label) and moved; Delete is greyed for them, with the reason in its tooltip. They're found by `role`; a Comment field without one (older files) gets `role="comment"` quietly when the database opens. A core field missing from a database (deleted before it was protected) comes back, empty, on opening, with a note.
  - Word Class is distinct from the reference categories in section 3.4.
- **Glosses:** any number per entry, each with a language (`lang`). Token translations work the same way.
- **Second languages** (20 October, for ɛλicit): the first gloss language (Edit → Metadata) is the primary one, the language of the analysis; the others are there to help speakers understand (Arabic in South Sudan, Amharic in Ethiopia), not for the analysis, so they are **hidden by default everywhere**: offered in the lemma list's, All data's, Utterances' and Bulk edit's Configure columns (`Gloss (ar)`, `Translation (ar)`, editable in place) and in Configure cell (`Translation (ar)`, under Translation), but never in the defaults; in the lemma, token and utterance dialogues they sit under a folded **Other languages (ar)** button, open or closed as last left (per computer). Only the defaults changed: columns already set to show them stay. Spelling and predicted translations stay English only; Entire database export has every language, as before.
- **Token fields:**
  - Default: Phonetic (analysed), Phonemic (searchable), **Morphemes** (the morpheme glosses, the gloss line of IDEAS.md idea 2; not spell-checked), Pitch (pitch tools), Translation, Comment.
  - Built in on every token: tags, speaker, collection date, soundfile name.
  - Custom token fields can be added.
- **One token, one transcription, one soundfile.** Speaker and collection date are metadata on the token (and in the WAV file), not tags, and not part of the default file name.
  - **Recording with another speaker records over the token:** the token takes the session's speaker and date, and its transcription stays as it was.
  - Speaker is searchable and filterable in All data, but not offered in the matrix views.
  - Multiple recordings per token are deliberately left out.
- **Citation token:** the token with no tags. One is created automatically for each new entry.
- **Comments:** comment fields are available on both entries and tokens.

### 3.3 Tags and soundfile names

#### Tag structure (revised 18 October: tags no longer belong to word classes)

- **One customisable hierarchy**, set up in the tag structure editor (Edit → Lists → Tag structure), organised however the user likes: by word class (NOUN, VERB…), by broader categories (Nominal, Verbal), by construction or by frame.
  - **Groups** nest to any depth, e.g. Phonological → Following tone → before H, before L. Groups can also be flat, like Frames.
  - **Leaves:** tags.
- **Any tag can go on any token.** A possessed nominalised form can sit under a verb lemma with its possessor and case tags.
- **Tags under the same group exclude each other:** a token takes at most one tag from each lowest-level group. So:
  - 1SG.A + 3SG.O is allowed (Subject and Object are different groups), but 1SG.A + 3SG.A is not.
  - before H + after L is allowed (Following tone and Preceding tone are different groups), but before H + before L is not.
- **Tag names are unique in the whole structure** (tokens store the names). The editor shows clashes in red and won't accept them.
- **Each tag has a name and a file-name code.** Names may contain spaces ("before H"). Codes shared by two tags are shown in red, and OK asks before keeping them, since their file names couldn't be told apart.
- **Group defaults:** each group can mark **one** tag as its default (e.g. Simple in Stem, Affirmative in Polarity, isolation in Utterance position).
  - The default is a real tag: it is stored on the token, can be filtered on and shows in the matrix.
  - It has **no file-name code**, so it adds nothing to file names. Only a group's default can be without a code.
  - **Defaults are pre-selected on new tokens**, except the citation token, which stays tagless. A default is only added when its group is usual for the lemma (below) and the new token has no other tag from that group (e.g. a cell tagged Negative doesn't also get Affirmative). The user can unpick them.
  - The default defaults (20 October) are Singular (Number), Nominative (Case), Simple (Stem), Present (Tense), Perfective (Aspect), Indicative (Mood), Affirmative (Polarity) and isolation (Utterance position). Other groups have none.
- **Citation means no tags.** It isn't assumed to be singular, simple, affirmative or anything else. Since 20 October Singular is Number's default, so it has no file-name code: a token tagged only with defaults (Singular, Nominative…) would get the citation's file name, and is offered an Example tag like any clash. Tokens with Singular and something else (Singular + 1SG.POSS) are told apart by the other tag, as before.
- **Everything is editable:** groups and tags can all be added (Add group at the top level, Add sub-group inside the selected one, Add tag), renamed, reordered and deleted. Renamed tags are followed in the tokens and saved matrices.
- **Tag order:** the order of groups and tags in the hierarchy is the order used everywhere: in the stored `tags` attribute, in displays and in file names.
- **Storage:** a token stores its tag names in one `tags` attribute, separated by comma and space, e.g. `tags="Plural, Genitive, before H"`, always written in tag order. Tag names therefore may not contain commas.
- **Changing a tag's code** (19 October): on OK, the recordings whose names it puts out of date are renamed straight away when names update automatically; otherwise Lemmatrix asks, **Rename** (only those recordings, one undo step, the same way as Update all soundfile names) or **Leave names out of date**.
- **Deleting a tag (or group) that tokens use** (19 October) says how many tokens use it and, on Yes, takes it off them when the dialogue is OK'd (their recordings' names follow, as for a code change). If taking it off would leave two tokens of a lemma with the same tags (so their recordings would get one name), it lists them and won't delete it until they're sorted out.
- Speaker and variety are not tags. Speaker comes from the participant list and the current session; variety comes from the database metadata.

#### "Usual for": hints, not rules (agreed 18 October)

- **A group can say which word classes it is usual for** (the Usual for column of the tag editor; double-click it, or Usual for…, to tick classes in the Word Class list). Several classes are fine ("usual for NOUN and PRONOUN"). **No hint means usual for every lemma.** A subgroup takes its parent's hint unless it has its own; the column shows an inherited hint in grey brackets. A class includes those nested under it in the Word Class list.
- The hint lives on the group, so **renaming or moving a group keeps it**, and the top level doesn't have to match the word class names (Verbal can be usual for VERB). **Renaming a word class** in Edit → Lists updates the hints and the lemmas; a hint naming a class since deleted shows in red ("no longer in the Word Class list") until it's changed.
- **What the hint does:**
  - **Token dialogue:** the groups usual for the lemma's word class are shown, plus any group the token already has a tag in; **Show all tags (N more groups)** under them shows the rest, and stays on for Back and Next.
  - **Defaults:** only groups usual for the lemma give new tokens their default.
  - **Soft warning:** a tag from a group that isn't usual for the lemma is allowed, but marked: its chip has a dashed amber outline in All data, the matrices (in Lemma/Tag on the token itself, since a column spans many lemmas) and the token dialogue, its tooltip says why, the token dialogue has a note under the tags, and bulk edit's preview counts such tokens. The note and the preview have **Don't show this again**; **Settings → General → Warnings** turns it back on.
- **Changing a lemma's word class** changes nothing else: the tags stay, and any that are no longer usual are marked. (The tag conversion dialogue of 17 October was dropped with this change.)

#### Default tag structure

New databases start with this structure (revised 20 October). Everything in it can be added to, renamed, reordered or deleted, and **Edit → Lists → Tag structure → Reset to defaults** brings it back (section 3.8). The Word Class list starts with NOUN, VERB, PRONOUN, QUANT, ADJECTIVE and ADVERB.

| Top-level group (usual for) | Group | Tags (code); **default** |
|---|---|---|
| Nominal (NOUN) | Number | **Singular**, Plural (PL) |
| Nominal (NOUN) | Case | **Nominative**, Accusative (ACC), Ergative (ERG), Absolutive (ABS), Genitive (GEN), Pertensive (PER), Locative (LOC) |
| Nominal (NOUN) | Possession | 1SG.POSS, 2SG.POSS, 3SG.POSS, 1PL.POSS, 2PL.POSS, 3PL.POSS (codes as names) |
| Verbal (VERB) | Subject | 1SG.A, 1SG.S, 2SG.A, 2SG.S, 3SG.A, 3SG.S, 1PL.A, 1PL.S, 2PL.A, 2PL.S, 3PL.A, 3PL.S, NP.A, NP.S (codes as names; A the agent-like argument, S the single argument, NP a noun phrase) |
| Verbal (VERB) | Object | 1SG.O, 2SG.O, 3SG.O, 1PL.O, 2PL.O, 3PL.O, NP.O (codes as names; O the patient-like argument) |
| Verbal (VERB) | Stem | **Simple**, Infinitive (INF), Passive (PASS), Antipassive (AP), Causative (CAUS) |
| Verbal (VERB) | Tense | **Present**, Past (PST), Future (FUT) |
| Verbal (VERB) | Aspect | **Perfective**, Imperfective (IPFV) |
| Verbal (VERB) | Mood | **Indicative**, Imperative (IMP), Interrogative (INT) |
| Verbal (VERB) | Polarity | **Affirmative**, Negative (NEG) |
| Phonological (every lemma) | Following tone | before H (xH), before L (xL) |
| Phonological (every lemma) | Preceding tone | after H (Hx), after L (Lx) |
| Syntactic (every lemma) | Position vis predicate | preverbal (PREV), postverbal (POSTV), non-verbal predicate (PRED) |
| Syntactic (every lemma) | Utterance position | **isolation**, utterance-initial (INI), utterance-final (FIN) |
| Instances (every lemma) | Frames | Frame 1 (F1), Frame 2 (F2) |
| Instances (every lemma) | Examples | Example 1 (x1), Example 2 (x2) |

- **Defaults have no code** (a group's default adds nothing to file names), so Singular, Nominative, Present and Perfective are written without SG, NOM, PRS and PFV. Oblique (OBL) was in the prototype's Case group and is no longer a default.
- **Tag descriptions** (to do): each default tag and group is to get a one- or two-sentence description, with its source in the SIL Glossary of Linguistic Terms or Grammaticon (`lemmatrix/tagdefs.py`).
- **Environment codes** use x for the form itself: `xH` is "before H", `Hx` is "after H".
- **Instances** (18 October; Josh chose the name) is the **last group in the tag order**, so its codes always end the file name, e.g. `LXX-VXX_D001_goat_PL-xH-F2.wav`. Its tags sort as a second key, like frames always did: each form first on its own, then in its frames and examples.
  - **Frames** are the most basic way of comparing data: each frame is a fixed carrier context the forms are elicited in.
  - **Examples** tell apart tokens of a lemma with the same tags (another example of the same form), so their recordings get names of their own: `…_SG.wav`, `…_SG-x1.wav`. The codes are **lowercase** (Josh, 18 October: his convention for a non-linguistic gloss), as are his frames' (f1–f4).
- **Descriptions** (19 October): every tag and group can have one (the Description column of the tag editor; double-click to edit), e.g. a frame's carrier sentence ("I saw ___"). Stored as a `description` attribute on the `<tag>` or `<group>`. A tag's shows in its tooltip wherever it appears (the token dialogue, All data's and Utterances' Tags column, the matrix headers, Configure matrix's tag picker, Bulk edit's tag list), a group's on its name in the token dialogue. **File → Export → Tag structure as CSV…** lists every group and tag with its code, default, "usual for" and description.
- **Known limit:** S and A subjects share one group, so a token can't have two subjects. Nothing stops an intransitive subject (e.g. 1SG.S) being combined with an object, though. That's left to the user for now.

#### Soundfile names

- **The pattern is fully customisable** in settings. The default:

  `{language}-{variety}_{reference}_{gloss}_{tags}.wav`

  `{speaker}` is no longer in the default pattern but is still available as a placeholder for anyone who wants it.

  - **Empty parts drop their separator.** A dash or underscore is written only if the part next to it has a value, so a database with no variety gets `LXX_D001_goat.wav`, not `LXX-_D001_goat.wav`.
  - **`{tags}`** is all of the token's tag codes joined by the tag separator (default `-`), in tag order. `GEN, PL` and `PL, GEN` therefore give the same name. Group defaults add nothing.
  - **`{gloss}`** uses the entry's `file-gloss`, which is copied from the primary gloss when the entry is created. Later gloss edits don't change it; it can be changed deliberately.
  - **Spaces and punctuation are written as Praat writes them** (19 October, replacing "spaces stay as spaces"): Praat turns spaces and ASCII punctuation other than `+ - = _` into underscores, and its Save suggests that name, so an edited `…_to run.wav` was saved as a second file `…_to_run.wav`. All file names now follow Praat's: `to run` gives `LXX_V012_to_run.wav`, a tag code `1SG.A` gives `…_1SG_A.wav`; the gloss, label and codes themselves keep their spaces and dots. Tokens', utterances' and texts' files alike. On opening, older names are renamed once (whatever the Update names setting); if Praat had already saved its own newer copy beside one, that copy is used and the old one held like a deleted recording; if the old one is newer, both are left and listed. Closing without saving puts everything back.
  - Other placeholders available for custom patterns: `{date}` (collection date), and any entry or token field by name.
- **Examples with the default pattern:**
  - `LXX_D001_goat.wav` (no variety)
  - `LXX-VXX_D001_goat.wav`
  - `LXX-VXX_D001_goat_PL.wav`
  - `LXX-VXX_D001_goat_PL-GEN-xH.wav`
  - `LXX-VXX_D001_goat_PL-f2.wav` (frame codes always come last)
- **Forbidden characters:** glosses, tag codes, language, variety and speaker codes, and references may not contain `/ \ : * ? " < > |` (characters Windows forbids in file names). The program refuses them as they are typed, with a short message.
- **Each token stores its own soundfile name** (`file`): the actual name of its recording on disk. The program also builds the expected name from the pattern and shows it on the token, updating live as tags change.
- **Updating file names** when the expected name differs from the stored one:
  - Setting **"Update soundfile names automatically"** (default: on): the stored name and the recording on disk are renamed straight away.
  - With the setting off, the token shows that its name is out of date, and an **"Update soundfile name"** button renames it.
  - An **"Update all soundfile names"** command does the same across the database, e.g. after changing the pattern.
  - **Online-only recordings** (OneDrive "Files On-Demand") count as present. The matrices show them with a small blue **cloud** instead of the green speaker, and tooltips and the token dialogue say "online only: needs internet to play". If one can't be downloaded (offline), playing it explains why and suggests "Always keep on this device" for the sound folder. Recordings are read before playback starts, so any problem is reported instead of the play staying silent.
  - **Renames stay in step with the database.** A rename is part of its undo step, so undoing it renames the file back. Discarding unsaved changes gives renamed recordings back the names the saved database expects.
  - **Tools → Find missing or unlinked recordings** looks at tokens whose recording isn't where they say (e.g. renamed outside Lemmatrix) and at tokens with no recording, in case one was added to the folder by hand (e.g. cut out of a longer recording). It pairs them with recordings of the same lemma that no other token uses: the expected name first, then the closest name, best matches first. Utterances are matched with unused recordings in `Soundfiles/Utterances` that have their reference in the name (19 October). It links them after you confirm. Opening a database notes in the status bar if any recordings aren't linked.
  - **Tools → Fill in recording dates from the soundfiles…** (18 October): a token's Date from its recording's own metadata: the creation date Lemmatrix writes (INFO `ICRD`), or a field recorder's or editor's (Broadcast WAV `bext`). Only tokens with no date by default; optionally also dates that differ, and optionally the file's last-changed date when a file has none (less reliable). A preview lists every change (lemma, tags, file, date now, new date, where it came from) and what was left alone; Fill in is one undo step. Online-only files are skipped, so nothing is downloaded. Utterances' recordings are included.
  - Renaming never overwrites another file; a clash triggers the duplicate-name warning instead.
  - **Update all soundfile names is one undo step.** Every recording moves through a temporary name first, so names that swap or chain (A → B while B → C) work; ones that can't be renamed are listed.
- **Duplicate names:** the program warns if two tokens would produce the same file name.
- **Same recording name → an Example tag** (18 October). When a token would get the same file name as another token's recording (e.g. Add in a cell that already has a token), recording, and saving the token (OK, Back, Next; once per token), offer the first Example tag that gives it a name of its own (x1, x2…; a new Example N, code xN, is added when all are taken). On saving, Keep as it is leaves it; on recording, Cancel records nothing. **Recording never writes over another token's file.**
- **One recording per token, no takes.** Recording again replaces the token's own recording, after a confirmation ("Replace this token's recording?"); the replaced one goes to the Recycle Bin. A file of that name that no token uses is asked about too. This applies to recordings converted from Dekereke too.
- **Metadata inside the soundfile:** the speaker is written into the WAV file's own metadata as "artist" (the INFO `IART` field). *Proposed:* the collection date goes into the date field (`ICRD`) as well.
- **Deleting a token** deletes its recording too: it waits in `Soundfiles/_Deleted recordings` (so **undo brings it back**, and discarding unsaved changes puts it back) and goes to the Recycle Bin when the database is closed. A held recording that a token still uses (after a crash, say) is put back on opening. A recording another token shares is never deleted with a token. A setting, **"Delete recordings with their tokens"** (default: on), turns this off, so the WAV file stays in the sound folder.
- **Filtering requirement:** the user must be able to pick lemmas (e.g. goat, lion, cow), tags (SG, PL, GEN), a speaker (SP1, in All data) and an environment ("before H"), and see exactly the matching tokens.

### 3.4 References

- **Rules:** references are unique and never renumbered automatically, since they're part of file names. Gaps left by deleted entries stay.
- **Schemes:**
  - Category list (the default).
  - Running sequence with a pattern, e.g. `0001` or `A0001`.
  - Manual entry.
- **Default category list:** customisable in settings, numbered automatically with 3 digits unless noted. Inspired by Dixon (2010: 296), as the Reference categories page of Edit → Lists notes: Dixon, R. M. W. 2010. *Basic Linguistic Theory*, Vol. 1: *Methodology*. Oxford: Oxford University Press. Texts, songs and grammatical paradigms are left out; paradigms are handled as tokens of a lemma.

| Letter | Category | Numbering |
|---|---|---|
| A | Human body | auto |
| B | Human designations | auto |
| C | Kinship terms & ethnonyms | auto |
| D | Mammals | auto |
| E | Birds | auto |
| F | Fish | auto |
| G | Reptiles & amphibians | auto |
| H | Insects & other small things | auto |
| I | Spiritual, disease, ceremony | auto |
| J | Flora, food, drink | auto |
| K | Cultural artifacts | auto |
| L | Inanimate nature | auto |
| M | Speech, thought | auto |
| N | Space, direction, time | auto |
| O | Other | auto |
| P | Property concepts | auto |
| Q | Quantifiers | manual: Q### where the digits are the actual number; additional quantifiers are QQ## |
| R | Pronouns | manual: R + gloss code, e.g. R1PLIN = first person plural inclusive |
| V | Verbs | auto |

### 3.5 Pitch

- **Storage:** digits `0`–`9`, colons, spaces and commas, as typed. Brackets or tone letters are added for display only.
- **Notation (revised 16 October):**
  - **Spaces separate syllables**; a **comma** marks a pause (not necessarily a word boundary).
  - **Digits are pitch points.** A syllable needs at least two points.
  - **Between two adjacent points is one short step. Each colon between them adds one step:** no colon = short, `:` = long, `::` = extra long.
  - Examples:
    - `11` short level low; `1:1` long level low; `1::1` extra-long level low
    - `14` short (quick) rise; `1:4` long steady rise
    - `42` quick fall; `4:2` long fall; `4:42` long level high, then a quick fall; `42:1` quick fall, then a long fall
    - `142` short rise-fall; `1:42` long rise, then a quick fall
  - **A lone digit is doubled automatically** (`5` becomes `55`, a short level), when typed and when older data is opened.
  - Colons at the start or end of a syllable mean nothing and are flagged.
- **Drawing lengths:** a short step is drawn about as long as an underscore `_` in the field's font, a long step as two (`__`), an extra-long step as three. **Syllables are about one underscore apart; a comma makes the gap about two (`__`).**
- **Pitch playback:** a token's pitch can be played as an abstract sound, in one of three voices chosen in Settings → Pitch: **Buzz** (a robotic buzz following the trace exactly), **Hum** (a human-like "mmm mmm mmm") or **Whistle** (a human-like whistle; the default since 19 October). Every short step lasts the same time, colons lengthen steps as in the drawing, syllables are separated by a short silence and a comma by a longer one. Levels are two semitones apart (a wide display range is squeezed into about an octave and a half). The end fades out gently (the last 150 ms) and 360 ms of silence follow, so playback ends without a click (Josh's pick of three versions, 18 October).
- **Pitch display range** (setting, default `1-5`):
  - Sets which digit is drawn lowest and which highest; everything in between is spaced evenly. `1-5` matches Unicode tone letters and keeps typing on the near side of the keyboard.
  - Can be set to anything from 0 to 9, e.g. `0-9` or `1-7` for sentence-length tokens. Changing it redraws all pitch displays.
  - A digit outside the range is drawn beyond the edge and flagged, rather than silently stretching the scale.
- **Display:**
  - **Default: contours drawn by the program.** Works with any range; a comma is drawn as a gap.
  - **Alternative (later): Unicode tone letters** with the staves hidden (Charis SIL `cv92`). Only available when the range is five levels or fewer.
  - The stored data stays as typed either way.
- **Checking:** once syllabification exists, the program compares the number of pitch groups with the syllables in Phonetic and flags mismatches. Commas aren't counted as syllables.

### 3.6 Current session

- **A small panel in the main window** shows the current session:
  - **Researchers**, **Participants** and **Locations** as chips (codes for people, names for places; the tooltip has the rest). **+** adds from the lists (locations as nested menus), clicking a chip removes it; a participant's chip also opens their consent file.
  - **Speaker** (not shown in the panel since 18 October; chosen in the token dialogue only): the first participant, until another is chosen in the token dialogue (or no one); that speaker stays for the following recordings. The token dialogue's speaker list is the session's participants (all participants if none are picked).
  - **Date** (defaults to today; can be changed to backfill older data, but not to a day that hasn't come yet)
  - Two buttons: **Write to notebook** (a pencil and a black arrow pointing at the next button) and **Open notebook** (a notepad in the theme colour) on its right (section 3.7).
- **Speaker and date can be left empty.**
- **What the session does when non-empty:**
  - New tokens (including the automatic citation token) get the session's speaker and collection date.
  - Recording a token sets its speaker and date to the session's (written into the WAV file too); the variety code in file names comes from the database.
  - Changed comments are dated with the session's date (today with No date).
- **Between runs:** the speaker and the people and places are remembered per database exactly as the panel was left when the program closed (removals and an empty panel included), even on a day that has notes in the notebook; the notebook is only used when nothing has been remembered yet (the session's day if it has people or places, otherwise the latest day that does). Picking a day with notes in the Date box still loads that day's people and places, and that is then what is remembered; the date resets to today each time the program opens, so a backfill date isn't carried over by accident, and **moves on at midnight** when the program is left open (18 October): today can then be picked, and a session dated the day before moves to the new day; a backfill date stays.

### 3.7 Notebook

*Agreed 17 October, replacing the FLEx notebook.*

- **A file of its own next to the database:** `LXX-VXX_Complete_Lexicon.notebook` beside `LXX-VXX_Complete_Lexicon.xml` (XML, with backups like the database). It is saved with the database and by **Write to notebook**; its unsaved changes count as unsaved changes. A notebook that can't be read is never written over.
- **One session a day.** Sessions have no titles (FLEx's numbered sessions were for payments); the date orders them. Notes can be added for today or an earlier day (**Add note**, which starts with that day's comments, recordings and speakers) and deleted, but not for a day that hasn't come yet.
- **A session holds:** the date; researchers, participants and locations (codes); **notes** (plain text in Charis, so IPA can be typed); the **comments** of the day, with links; **questions**, each with the date it was asked or last edited and the date resolved, and, when pushed from a token's comment, a **link to the token** (a Token column in the notebook's questions and the Questions window; double-click it, or Go to token, to show it). The **recordings** of the day aren't stored: they are found from the tokens' dates.
- **Comments:** only the comment fields count (a field named Comment, Comments…), or the notes would get huge. Every comment field keeps the day it was last changed (`changed="…"`).
  - Changed again on the same day: written over in that day's record.
  - Changed on a later day: the old record keeps the old text, and the new version goes to the later day.
  - The lemma or token deleted on the same day (or the change undone): it leaves that day's record. Deleted on a later day: the old record keeps it, and its link says "Lemma no longer exists" or "Token no longer exists".
- **Write to notebook** writes or updates the day's session: the panel's researchers, participants and locations, and the day's comments. It never touches the notes or questions. Saving the database brings the day's comments up to date too (and starts the day's session if it has comments but no session yet).
- **The notebook window** (View → Notebook, Ctrl+B, or the panel's button), following the mockup: the title, the session's date (double-click to change it), researcher, participant and location chips (+ to add, click to remove); on the right a search bar (notes, people, places, comments and questions; matches are marked in the notes), a calendar button, and the list of days, **new to old** or **old to new**, with Add note and Delete note; below, the notes; then three tabs (Josh, 18 October: the questions under the comments were too crammed): **Questions** first (its tab says how many are open; Add, Delete, Edit and Resolve/Unresolve, a purple square with a tick, sit at the top of the tab; question | token | status | created/edited | resolved), then **Comments** (comment | link; double-click goes to the lemma or token), then **Recordings** (the day's recordings). The window stays open beside the main one.
- **View → Questions:** all questions in one list, newest day first, showing open, resolved or all, with a search, Resolve / Mark as open, Edit and Open in notebook.
- **People found in the notebook** join the researcher and participant lists when the database opens.

### 3.8 Lists

- **Edit → Lists** edits every list in one dialogue: **Researchers**, **Participants** (the consent file is a link that opens it; Choose consent file… sets it) and **Locations** (nested, with codes and descriptions); the closed fields' lists (Word Class, Tone Class, Inflection Class…); and the **Tag structure** itself. Values renamed in a list are followed in the lemmas and tokens, and renamed word classes in the tag groups' hints too. **Edit → Tag structure** opens it at Tags.
- **Reset to defaults** (20 October): every page has the button (top right, with its name: the icon alone wouldn't say). It puts that list back as a new database has it (`lemmatrix/resets.py`), after asking. **Anything in use is kept:** a person with tokens or sessions, a place used by a session (with the places above it), a value on lemmas, tokens or texts, a reference category with references, a tag on tokens (in a group of the same path). What was kept is listed. Nothing changes until OK; Cancel leaves everything as it was. Tier mapping goes back to tx, ge, ft, mb.
- **Researchers** have Code, Name, **Email** (checked to look like an address) and Description; **Participants** Code, Name, the ticks **Identifiable?** and **Audio sharing?**, Description and Consent file (20 October). The session panel's chips show a participant's agreements and a researcher's email in their tooltips.
- **Renamed codes are followed everywhere:** a participant's in the tokens' speakers and the notebook, a researcher's and a location's in the notebook. Removing someone who is used asks first; tokens and sessions keep the code.
- **Choose consent file…** opens in the main folder's **Documentation** folder (section 3.9). **Edit → Metadata** has an **Open documentation folder** button (Josh, 18 October), which makes the folder if it isn't there yet.

### 3.9 The main folder

*Agreed 18 October (IDEAS.md idea 7) and built the same day as its stage 1.* The code is `lemmatrix/layout.py`.

- **One main folder per database** (any name). Lemmatrix assumes the layout inside it instead of keeping paths in Settings:

  ```
  Main folder/
  ├─ <database>.xml
  ├─ <database>.notebook
  ├─ Soundfiles/
  │  ├─ Tokens/              (lemma tokens)
  │  ├─ Utterances/          (utterances' recordings, section 3.10)
  │  ├─ Texts/               (texts' recordings and TextGrids, section 3.11)
  │  └─ _Deleted recordings/
  ├─ Backups/                (the automatic local backups)
  ├─ Documentation/          (consent forms and other documentation)
  ├─ Images/                 (pictures for ɛλicit requests, 20 October)
  ├─ Elicit/                 (ɛλicit requests and the recordings that came back, section 5.12)
  └─ Exports/                (the default place File → Export offers)
  ```

  - A **new database** starts with Soundfiles/Tokens, Documentation, Images and Exports (Backups comes with the first save).
  - **Images** (20 October, IDEAS.md idea 19): a picture belongs to a token by its name alone, the reference plus the token's tag codes as in soundfile names, written as Praat would name it: `D001.jpg` for the citation token, `D001_PL.jpg` for the plural, `D001_PL-1SG_POSS.gif` for "my goats" (JPG, PNG or animated GIF, any case). **No falling back** on the lemma's picture (one goat is not three). Never shown in Lemmatrix and never in the database (`filenames.image_stem`, `find_image`); **Edit → Metadata → Open images folder** opens it. The full backup includes it; the anonymous backup doesn't.
  - **Settings → Sound has no sound folder** any more.
  - **Deleted tokens' recordings** wait in `Soundfiles/_Deleted recordings`; one left in the old place (inside the sound folder) is still put back or emptied.
  - **Exports** is only the default: CSV exports and the anonymous backup start there, and can be saved anywhere.
- **Consent forms:** a consent link is relative to the main folder when the form is inside it. A form that isn't where its link says is looked for by file name in Documentation (subfolders too) and relinked quietly when the database opens (a status-bar note; saving keeps the new link).
- **One database per main folder:** two in one folder would share Soundfiles, so opening a database with another Lemmatrix database beside it warns. **New database** in a folder that already has one offers to make a folder named after the new database for it.
- **No Save as** (for now), and so no warning about moving soundfiles. A database never saved (rare) asks where to go when it is first saved, with the same check.
- **File → Rename database…** changes the database's name (in the title, Edit → Metadata) and its file name together; the file name follows the name (`LXX-VXX_Complete_Lexicon` → `LXX-VXX_Main_Database`) until it is edited itself. The notebook and the automatic backups in Backups are renamed with it (all or nothing; a name already taken is refused), the window's settings, the Current Session and the full-backup reminder move to the new name, and the database is saved under it. Not while it is open on another computer. Renaming the XML by hand loses the notebook's link (it is found by name) and these settings.
- **File → Full backup…** zips the whole main folder with its subfolders (the open-database marker left out) as `<database> YYYY-MM-DD.zip`, e.g. `LXX-VXX_Complete_Lexicon 2026-10-18.zip`, with the top folder's name inside the zip. Unsaved changes are offered a save first. The save dialogue starts in the **full backup folder** (Settings → General; Documents if none, or the folder of the first backup); a full backup can never go inside the main folder. Recordings are stored as they are (they hardly compress) and everything else compressed; the zip is written under a temporary name, so a cancelled or failed backup leaves nothing. Lemmatrix doesn't delete old full backups.
- **Weekly reminder** (per computer): when the last full backup is 7 or more days old (with none yet: a week after the database was first opened with this version), opening the database shows a message with **Back up now** and **Thanks, remind me again in 7 days**.

### 3.10 Utterances (format 5)

*Agreed 18 October (IDEAS.md idea 7) and built the same day as its stage 2.* The window and dialogue are `ui/utterances.py`.

- **An utterance is a token without a lemma:** one reference, one token (one transcription, one recording), with the usual token fields (Morphemes included), tags, speaker, date and file, an optional **file label** (like a lemma's `file-gloss`, but editable at any time) and **links to lemmas** (by id). Related utterances are found by searching tags or comments. In the model, `Utterance` is an `Entry` with exactly one token, kept in `db.utterances`, so undo, comments, the notebook and backups treat it like an entry.
- **Categories:** the reference's letter is the category. U (Unorganised) and W, X, Y, Z (named "Own category W"… until renamed) are in the reference categories list, marked as for utterances. **Edit → Lists → Reference categories** edits the whole list (letter, name, for lemmas or utterances, automatic or by hand); a letter in use can't change, be removed or switch between lemmas and utterances, and no letter may start another (QQ and Q). The lemma dialogue offers lemma categories only. References go past 999 (W1000 follows W999) with nothing renamed. **Move to another category…** (right-click) gives the next free reference there and renames the recording, after asking.
- **File names** have a pattern of their own (Settings → Sound → Utterance file names, default `{language}-{variety}_{reference}_{label}`; it needs `{reference}`) and no tags: `LXX-VXX_W001_lion_house.wav`, in `Soundfiles/Utterances`. Changing the label renames the recording (when names update automatically), with undo; Update all soundfile names covers utterances too.
- **Three ways to make one:**
  - **Add:** pick the category; the utterance dialogue opens on a new utterance, which is added when it's saved with anything in it (or recorded).
  - **Import…** or **dragging WAVs** onto the grid: pick the category; each file is copied into `Soundfiles/Utterances` under its utterance's name, with the file's name as the label (underscores as spaces, characters forbidden in file names left out) and the session's speaker and date; the originals stay as they are. One undo step for the whole import (undo moves the copies aside, like deleted recordings). A WAV already in `Soundfiles/Utterances` is renamed there, not copied. **A TextGrid beside the WAV** (same name) is read with the tier mapping and fills in the fields (it isn't copied, and there is no source link); with several lines Lemmatrix asks: Join the lines, Pick one…, Add as a text (the recording and TextGrid become a text instead) or Skip this file.
  - **Clip as utterance** in the Texts tab (section 3.11).
- **Tags:** lemma tags can go on utterances. A tag group can be marked **utterances only** (in the tag editor's Usual for… dialogue; the Usual for column then says "utterances only", inherited by sub-groups): a rule, not a hint. Its tags are never offered on lemma tokens, not even under Show all tags, and one put there another way is marked like an unusual tag ("for utterances only"). **New utterances start with no tags** (no word class to take defaults from), and nothing on an utterance is marked unusual.
- **View → Texts and utterances** (Ctrl+U): a window of its own, **laid out like the main window's Matrix pane** (Josh, 18 October: nothing to look for anew): the title in the theme colour with the **Texts** and **Utterances** tabs on the right of its row; the grid; an options row under it (Auto-play token soundfile, the same option as the main window's); and the options panel at the bottom, below a splitter, with the buttons, the quick search and the count line ("3 of 3 utterances shown"). Its size, place and splitters are remembered as they are adjusted (20 October). The Texts tab is section 3.11.
  - **Utterances tab:** a grid like All data (clicking an utterance plays it with Auto-play on): Reference, File label, Tags, Pitch drawing, the token fields, Lemmas, Speaker, Date, Soundfile (Present / Missing / Rerecord), and Category in Configure columns; editable in place (token fields and the file label), the same column filters, quick search, Clear all filters. Add, Import…, Delete, Edit, Play, Configure columns; Delete, Enter, Space, Ctrl+Space and **Ctrl+Shift+Space** (play the pitch; Josh, 18 October) as in All data; a right-click menu with Play pitch and Move to another category…. Deleting holds the recording for undo, as for tokens.
- **The utterance dialogue** is the token dialogue (Ctrl+Space and Ctrl+Shift+Space play from inside any of its fields, the file label, Lemmas search and Date included, as in the token dialogue) with: a header with the reference, the category's name and the editable file label (`W001 · Clause types · hare ran`); the utterance-only groups and the groups with no "usual for" hint first, Show all tags for the rest; no predicted translations (they are learned from lemmas' glosses); a **Lemmas** box (type a reference, form or gloss, pick from the list; click a chip to remove the link); the recording panel as for tokens; Back and Next through the grid's rows.
- **Elsewhere:** the notebook's Recordings tab lists the day's utterances, marked as utterances; utterance comments count as the day's comments and Push to question works, with links that open the utterance in the window. Renamed participants, field values and token fields are followed in utterances; the anonymous backup copies utterance recordings into `Soundfiles/Utterances` and replaces names in their comments.
- **Clipped utterances** show their **Source** in the dialogue: the text's reference and title and the line's times, **Play in context** (the line with 2 s either side, from the text's recording) and **Show the text** (the Texts tab, with the line selected).
- **In the tools** (19 October): Check spelling checks utterances' English translations (and the Utterances grid's Translation column is underlined); File → Export → Entire database has a row for each utterance after the lemmas, with a **Kind** column (Lemma or Utterance; only when the database has utterances), the reference, and the file label in Gloss in file names; Find missing or unlinked recordings looks in `Soundfiles/Utterances`. **Not yet:** Bulk edit.

### 3.11 Texts and songs (format 6)

*Agreed 18 October (IDEAS.md idea 7) and built the same evening as its stage 3.* The tab and the text dialogue are `ui/texts.py`; reading TextGrids is `lemmatrix/textgrid.py`, with `praatio` (MIT licence).

- **A text (T001) or song (S001) is a catalogue record:** reference, the **text fields** (Edit → Fields has a third list, Text fields: Title, Genre, Transcription status, Description and Comment by default, and any of the user's own), date, participants, researchers and locations (codes that follow renames in Edit → Lists), the recording and its TextGrid. **Genre** (narrative › personal narrative, folktale, history; procedural; hortatory; expository; conversation; song; prayer; elicited; other) and **Transcription status** (untranscribed, transcribed, translated, analyzed, finished; 20 October) are closed lists in Edit → Lists. T (Texts) and S (Songs) are reference categories marked for texts.
- **Adding a text** (Add): the text dialogue (600 px wide at first, resizable, its size remembered; file names shown without their folders, the full path in the tooltip), with Choose recording… (a TextGrid of the same name beside it is picked too) and Choose TextGrid… (both open in `Soundfiles/Texts`, or beside the recording already chosen). On OK both are **copied** into `Soundfiles/Texts` under `{language}-{variety}_{reference}_{title}` (Settings → Sound → Text file names), the originals left as they are; one undo step, and undo moves the copies aside. A file that is **already in `Soundfiles/Texts`** is renamed there, not copied (undo, or discarding the changes, gives it its old name back). The title in the names is a **file label** copied when the text is added; editing the title later renames nothing, but **Title in file names** can be changed deliberately, and then both files are renamed (with undo). Update all soundfile names covers texts' files too.
- **The lines stay in Praat.** Lemmatrix reads them from the TextGrid when a text is chosen (again only when the file has changed) and never writes it.
- **Tier mapping:** a database-level list of rules, tier name → token field (Phonetic, Phonemic, Morphemes, Translation with its language, Comment…) or Ignore, and which tier is the **main tier** (its intervals with text are the lines; the other tiers' text is matched to them by overlapping time, joined with spaces). Defaults: tx → Phonetic (main), ge → Morphemes, ft → Translation (en), mb → Ignore. **Speakers:** a tier named `tx@SP1` counts as tx, said by SP1, and is matched only with SP1's other tiers (and tiers with no speaker); without a speaker in the names, a text with one participant gives that participant. The text dialogue lists the TextGrid's tiers with what each fills in and a Main tick, and counts the lines: a tier with no rule yet is **learned** for the next texts; a choice that differs from the database's rules becomes **the text's own mapping**. **Edit → Lists → Tier mapping** edits the database's rules. Renamed token fields are followed in the rules.
- **The Texts tab**, laid out like the rest of the window: the texts on top (Reference, Title, Genre, Transcription status, Date, Participants, Utterances clipped from it, Recording; Researchers, Locations, TextGrid and the other fields in Configure columns; the usual filters and search); below, **the chosen text's lines** (Start, End, Speaker, a column for each mapped field, and the utterances clipped from each line). **Each list has its controls right under it** (Josh, 18 October): under the texts, a panel with Add, Delete, Edit, Configure columns, Clear all filters, the texts' search and their count; under the lines, the window's options panel with **Play line** (also Ctrl+Space, Space, Enter, double-click), **Play in context**, **Clip as utterance…** and **Open in Praat**, the lines' search and their count. Double-clicking a line's Utterances shows that utterance. The window **opens on the Texts tab** (Josh, 18 October), except when it opens to show an utterance.
- **Clip as utterance…** (one line or several, one undo step): pick the utterance category; each line becomes an utterance with its fields from the mapped tiers, the line's speaker (or the text's only participant) and the text's date, a label from the first six words of its translation, and its stretch of the text's recording **cut into a file of its own** in `Soundfiles/Utterances`, with **100 ms either side** (Settings → Sound → Clips keep either side), at the recording's own sample rate and bit depth, the speaker and date in its metadata. The utterance keeps a **link to its line**: the text, the line's times, what was copied from each tier and when the TextGrid was last changed (for Pull, stage 4).
- **Texts' files are named the way Praat names objects** (18 October; tokens' and utterances' too since 19 October, section 4): Praat turns spaces and ASCII punctuation other than `+ - = _` into underscores in an object's name (checked against Praat 6.1), and its Save suggests that name, so `…_Hyena and Hare.TextGrid` was saved by Praat as a new file `…_Hyena_and_Hare.TextGrid` and Lemmatrix never saw the edit. Texts' recordings and TextGrids are now named that way (`LXX-VXX_T001_Hyena_and_Hare.TextGrid`; the title itself keeps its spaces), so Praat's Save replaces the file Lemmatrix reads. On opening, older names are renamed once; if Praat had already saved its own newer copy, that copy is used and the old one held like a deleted recording (closing without saving puts everything back). A test runs the whole round with Praat itself (praat-parselmouth, when installed).
- **Open in Praat** opens the text's recording **with its TextGrid** in one editor, **zoomed to the selected line** (1 s either side) with the line selected (the script's `editor: grid` → `Zoom:` and `Select:`).
- **Deleting a text** holds its recording and TextGrid for undo, like deleted recordings; utterances clipped from it stay, with their own recordings.
- **Notebook:** a **Texts** tab lists the texts dated that day (found from their dates); double-click opens one in the Texts tab.
- **Pull** (stage 4, `lemmatrix/pull.py`; the dialogues are `ui/pull_dialog.py`). A clipped utterance's line is found again (the line with the same times, or else the one that overlaps it most, among the same speaker's tiers) and compared with **what was copied**, not with the utterance as it is now, so edits made in Lemmatrix never count as a change. A TextGrid not saved since the clip isn't read at all. States: the same; **changed** (a tier's text, an emptied interval included); **times moved** (the same text); **line not found**; **TextGrid missing** (or unreadable); text deleted (shown, not flagged). A tier gone from the TextGrid altogether (renamed?) changes nothing.
  - **Flags:** the reference is red, with the reason in its tooltip, and the **Source** column (`T001 0:00.50–0:01.50 – changed`) can be filtered for "Changed in the TextGrid". The window checks again whenever it becomes active (back from Praat), and the Texts tab shows the lines again if the TextGrid changed.
  - **Pull from source…** (right-click, the Source box in the utterance dialogue, Tools → Check clipped utterances…): a dialogue lists each field it will replace, as it is in the utterance and in the TextGrid now (and the times, if they moved); only the fields filled from the tiers that changed are replaced, and the line is remembered as it is now. One undo step for any number. If the times moved, **cut the clip again** is offered (on by default): the new clip has the same name and padding, and the old recording goes to the Recycle Bin (undo can't bring it back, as with a replaced recording).
  - **Unlink from the text…** forgets the line (for one that's gone): the utterance keeps its fields and recording. With undo.
  - **Tools → Check clipped utterances…** lists every flagged one and every one edited here, with Pull… and Push… (the selected ones, or all that can be), Unlink… and Show.
- **Push to source** (agreed with Josh, 18 October): the other direction. A field **edited in Lemmatrix** (it differs from what was copied or last pulled; spacing aside) marks the utterance **"edited here"** in the Source column (not red: it isn't a problem) and in the Source box. **Push to source…** (right-click, the Source box, Check clipped utterances) lists each edited field with its tier, as it is in the TextGrid now and as it will become, each with a **tick box**; an unticked one stays "edited here". Where the line spans **several segments** of a tier (a word-level tier), they are **merged** into one segment with the whole field, with the warning "This push will merge several segments in Praat." The line's **exact** boundaries are read from the TextGrid (the stored ones are rounded to 0.1 ms, and a rounded start once reached into the empty segment before the line, so the merge swallowed the empty segments either side: fixed 19 October); a segment counts only if more than 0.5 ms of it is inside the line, and an empty segment reaching past the line is split at the line's edge, so a push never moves a boundary outside the line. When the line was **changed in Praat** as well, its differing fields are listed too, but **unticked** and marked "changed in Praat" (ticking writes Lemmatrix's version back over Praat's), so either direction can be chosen, e.g. after restoring a TextGrid from Backups. Before writing, the TextGrid is copied into **Backups** (`<name>_<date>_<time>.TextGrid`), since undo can't reach it; the dialogue says to **close the TextGrid in Praat first** (Praat keeps its own copy, and saving it there would undo the push), and offers to open it in Praat afterwards at the line. One write per text; the utterances' links are updated as one undo step. A change made in Praat to another tier and not yet pulled stays flagged.
- **Anonymous backup:** with recordings, the texts' recordings and TextGrids go into `Soundfiles/Texts`; participants' names in the texts' open fields are replaced like the rest. TextGrids themselves can hold names, so the report's reminder applies to them too.

### 3.12 Editing a text's lines (agreed 19 October)

*Josh: "I hate working the TextGrid in Praat and would rather set up the utterance boundaries once, then work in Lemmatrix." Built the same night.* The view is `ui/lines_view.py`; editing a TextGrid is `lemmatrix/lines.py`; the glossing rules are `lemmatrix/interlinear.py`.

- **The TextGrid is the only store** of a text's lines (unless a line is clipped as an utterance): Lemmatrix is a layer over Praat that can't move a boundary. Boundaries are set in Praat, and a line is a segment of the main tier with text: untranscribed segments get a placeholder there (Praat can fill empty segments), pauses stay empty.
- **Held, then written on saving:** a text's TextGrid is read once into memory (empty segments included); each edit is an undo step like any other; **saving the database** writes the TextGrids edited (each copied into Backups first). Not saving leaves the files as they were. If Praat saved a TextGrid after edits were made here, saving asks: *Save my edits* (Praat's version goes to Backups), *Keep Praat's* (the edits here are dropped), or Cancel. The lines title says when a text has edits not yet saved. Open in Praat offers to save first; Push waits for a save. A TextGrid saved in Praat with no edits waiting here is simply read again.
- **The view:** each line is a **cell** with its fields stacked (Configure view: which fields, their order, which **line up**; one setting for all texts; at first the fields the tier mapping fills, with Phonemic and Morphemes lined up), a 24 px margin on the left, long lines scrolling sideways. At the right edge, **pinned**: the line's times, the **speaker** (only when a text has several), the utterances clipped from it (double-click to show one), and the **Comment** box, with a green **?** when it has a comment (**Push to question**, 20 October): the comment becomes an open question in the notebook on the session's day, linked to the line (double-clicking the question's link opens the text at the line), and the box is emptied, as in the token dialogue; the line's right-click menu has **Push comment to question** too. Free translations are shown in ‘quotes’: glosses and translations are in single quotes everywhere since 20 October (the token dialogue, the matrices' tooltips, the lemma pickers and the notebook had “double” ones), and quotes already round a value aren't doubled.
- **Glossing rules (LaTeX, gb4e/expex), for future LaTeX export:** in a lined-up field, spaces separate the units that align, `{braces}` group several words into one unit, `{}` is an empty one (an unglossed word). The symbols are **hidden except while editing**. A word-level tier (several segments in the line) is read as one unit per segment (an empty one as `{}`, one of several words in braces). Josh wants these rules everywhere; the matrix views are a to-do (IDEAS.md idea 2).
- **Edit mode** (the pencil, "Edit mode" beside it; **Ctrl+E** turns it on and off, 20 October): fields show as boxes and a click edits one in place (the Comment too). Enter keeps, Esc drops, **Tab / Shift+Tab** go to the next / previous field and on into the next line, **Up / Down** to the same field of the line above or below, **Ctrl+Space** plays the line (never types a space). Off: the lines are things to play (click with Auto-play, double-click, Space), select (Ctrl, Shift), clip and open in Praat.
- **Writing an edit:** into the tier the mapping gives the field (the line's speaker's). A word-level tier keeps its segments when the field has one unit per segment; otherwise its segments in the line are merged into one, after the warning "This edit will merge several segments in Praat". Empty segments reaching past the line are split at its edge, never swallowed, so no boundary leaves the line. A field with no tier yet gets one (named as the mapping's rule, with the line's @speaker), and the rule is added. The main tier's text can't be emptied (it makes the line).
- **Clipped utterances follow** an edit of their line automatically (one analysis, not several), in the same undo step; unlinked ones don't.
- **Comments → notebook:** a line's Comment is recorded in the day being worked on, linked to the text and line (double-click opens the text at the line); changed again the same day, written over; kept as it was in earlier days. Adding a text records the comments already in its TextGrid in the day the text was recorded.
- **Speakers:** a tier mapped to **Speaker (code)** (Edit → Lists → Tier mapping, or the text dialogue) gives each line its speaker from its text, for conversations; `tx@SP1` tiers still work.
- **Buttons under the lines** (Josh's mockup): Play, Edit mode, **Clip** (Josh's scissors-and-bubble icon, in the theme colour), Open in Praat, Configure view; the search, then **Next empty [field]** (the next line whose chosen field is empty; in edit mode it opens that field); the count.
- **Right-click a line:** **Edit [field]** (the field under the mouse, edited in place, in edit mode or not), **Edit text…** (the text dialogue), then Play line, Play in context, Clip as utterance… and Open in Praat.

## 4. Converting existing databases

- **No import or export of other programs' formats in the program yet** (LIFT and SFM are planned, section 6). Existing databases, e.g. from Dekereke or FLEx, are converted with one-off scripts written for each database's own columns; they aren't part of this repository.
- **Dekereke's files**, for reference: a flat UTF-16 XML file (`<phon_data><data_form>`, with one element per column) plus a separate `*-DkUserSettings.xml`.
- **A conversion** makes the lemmas and their tokens from the columns (e.g. a form and its pitch as the citation token, a plural column as a PL token), keeps the recordings' names (Lemmatrix shows those that are out of date, and Tools → Update all soundfile names renames them when wanted), and reports what it couldn't convert (columns left out, glosses or codes with characters forbidden in file names).

## 5. User interface

*Based on the first mockups and the change list of 16 October (after testing the prototype).*

### 5.1 Main window

- **Menu bar:** File, Edit, Tools, View, Analyze, Help. **Tools** has the soundfile tools and **Check spelling…** (F7, section 5.10). **Edit** holds undo and redo, then Metadata (language, variety, author), Fields, Lists and Tag structure, then **Bulk edit…** (Ctrl+E), then Settings (there is no separate Settings menu). **View** starts with Notebook (Ctrl+B), Questions and **Texts and utterances** (Ctrl+U, section 3.10). Playing the selected token (Ctrl+Space) and its pitch (Ctrl+Shift+Space) are keyboard shortcuts, not menu items.
- **Settings** has four tabs, in this order: **General** (autosave; the **full backup folder**, where File → Full backup starts; **Warnings**: marking tags that aren't usual for their lemma's word class, underlining English words that may be misspelled, and confirming before deleting recordings, which moved here from Sound), **Sound** (file-name pattern, tag separator, automatic renaming; recording source, bit depth, sample rate, deleting recordings with tokens, path to Praat), **Display** (light or dark theme, accent colour, IPA font size) and **Pitch** (lowest and highest pitch digit; pitch playback voice, with a Listen button, and its volume). Each tab separates what is stored in the database from what belongs to this computer.
- **Help → About Lemmatrix** (20 October): the version, © 2026 Joshua A. G. Smolders, the licence (GPL-3.0-or-later, no warranty), the source code's address, and the main libraries with their licences.
- **Splash screen** (20 October, Josh's design, `resources/splash.svg`, `ui/splash.py`): shown while Lemmatrix starts and opens the last database; `{version}` and `{date}` in the SVG are filled with the version and the current year. Any dialogue at start-up (a warning, the welcome box) closes it so nothing is hidden behind it. Its title, λemmatriχ in Doulos SIL, is stored as outlines (converted from Doulos SIL 7.000), so it looks the same on a computer without that font; the version line is Arial text. The SVG's partly see-through gradient is drawn on #198583, as Josh exported it.
- **Themes:** light or dark, for the whole program, the lemma list, All data and the matrices included. One **accent colour** (teal, #198583, the icon's colour, by default since 20 October; a saved #198768, the old default, follows the new one) colours the selected tab, highlights, tag chips and the **pitch traces**; on the dark theme the traces use a lighter shade of it so they stay visible.
- **The last view is remembered** for each database: the tab, the selected lemma, each matrix as it was (saved or not), and swapped axes, plus the window size and panel sizes.
- **Top left, in order:** the database title, the Save button, then File, Edit… (away from the window's close button). The menus are centred in the bar's height, level with the title and Save, flat with no lines under them.
- **Save button:** a small floppy disk in the theme colour (lighter on dark), no background, named in its tooltip (Ctrl+S does the same). It turns grey once saved and stays grey until the database changes (19 October).
- **Database title:** **Language - Variety - Database name** (e.g. Sample language - Sample variety - Complete Lexicon), large and bold, white on the theme colour; the codes stand in for blank names. The database name is its own line in the metadata (Edit → Metadata → Database name; `<name>` in the file), not the file name. **Double-click the title** to open Edit → Metadata.
- **Questions say what their buttons do** (Josh, 20 October): a message never names a button it doesn't have. Plain yes-or-no questions keep Yes and No; where the answer isn't a plain yes or no, the buttons are named for what they do (`widgets.ask`): **Reset to defaults** / Cancel, **Merge segments** / Cancel (editing a line), **Save and rename** / Cancel (Rename database), **Save and open** / **Open without saving** / Cancel (Open in Praat with unsaved line edits; it had an "Ignore" button).
- **Status bar:** there from the start, at the height a message needs, so a message such as "Saved." never makes it grow and nudge the panes (20 October). Saving no longer rebuilds the Current Session chips.
- **Tooltips in the lemma list, All data and Bulk edit's grids** (Josh, 18 October): only what the cell doesn't already show (the tags' full names, a recording's stored and expected names, a predicted translation and how to accept it, the pitch digits behind a drawing), or a cell's own text when the column is too narrow for it. They wait twice Qt's usual time before appearing. Buttons and the matrices keep Qt's usual timing.
- **Button style (Josh's preference, 17 October):** obvious, shared actions (Add, Delete/Remove, Edit, Play, Clear all filters and Clear matrix, both with the reset-filters icon, Save) are an icon only, with the name in the hover tooltip. Configure cell, Configure columns and Configure matrix are icon only too since 19 October (Josh's mockups: the gear with stacked cell lines, with columns, or with a χ beside it (Configure matrix, 20 October), in the theme colour). Buttons whose icon alone doesn't say what they do keep their names: Save, Rename and Delete matrix, the two Add place buttons in Edit → Lists, Resolve, Open in notebook. New buttons follow the same rule.
- **Pane titles:** "Lemma" above the lemma list and "Matrix" above the matrix, medium-large, in the theme colour. The tabs (All data, Lemma/Tag, Tag/Tag) are on the Matrix title's row, at the right, and both title rows are the same height, so the lemma list and the matrix start level.
- **Reset-filters icon** (Clear all filters, everywhere): a funnel inside two turning arrows; the funnel dark on the light theme and light on the dark theme, the arrows in the theme colour (19 October). The column headers' filter buttons use the same funnel shape.
- **Left: lemma list**, with its options bar underneath (section 5.2).
- **Right: the Matrix**, a panel labelled "Matrix" with three tabs, in this order: **All data** (the default), **Lemma/Tag**, **Tag/Tag**. Each tab has its own options bar underneath; the options change with the tab.
- **The options bar is height-adjustable** (a splitter between the matrix and its options).
- **Hiding the option panels:** a chevron at the right of the options row (and View → Hide or show the option panels) hides both bottom panels, the lemma options and the matrix options with Current Session, or shows them again; each can also be dragged down out of sight. Their sizes are remembered between runs.
- **One options row for every tab**, just under the matrix, remembered between runs:
  - **Auto-play token soundfile:** clicking a token plays it (in All data and the matrices), and the token dialogue plays each token it opens on, with Back and Next too.
  - **Show only lemmas with token data:** All data leaves out lemmas whose tokens are all empty; Lemma/Tag leaves out lemmas with nothing in the matrix's columns; Tag/Tag shows nothing for a lemma without token data.
- **Bottom right: current-session panel** (section 3.6): the title and the two notebook buttons, then Researchers, Participants, Locations and Date, the labels on the left and the chips (and the date) lined up in one column after them. Up to 560 px wide (Josh, 20 October), so the chips fit on one line and it needs less height.
- **Icons beside the tabs** (20 October, Josh's mockup): on the Matrix title's row, just left of All data, the **Texts and utterances** button (48 px; Ctrl+U), and to its left the **ɛλicit** button (48 px; its menu: Make ɛλicit request…, Receive ɛλicitation…, and Review waiting recordings… while some wait; section 5.12). Texts and utterances used to be a big button in a panel of its own beside Current Session.
- **Tags appear as small light-blue rounded "chips"** that size to their text: in the All data Tags column, in matrix headers, and in the token dialogue.
- **Icons** (drawn by the program, no image files):
  - Add: green circle with a white plus. Delete: red circle with a white X. Edit: black-on-white pencil.
  - Every "Configure…" option starts with a black-on-white gear; Configure cell, Configure columns and Configure matrix add stacked cell lines, two columns, or a χ beside it, in the theme colour (lighter on dark). The χ is drawn as strokes, not text, so Windows fonts can't change it.
  - Open in Praat: a white waveform on a Praat beige (#909068) rounded square (19 October, Josh's mockup).
  - Find missing or unlinked recordings: a magnifying glass over a music note, in the theme colour.
  - Texts and utterances: Josh's design (20 October), a T speech bubble in the theme colour and a lighter U bubble over it (same hue, #198583 → #5cc3c0), white letters. Kept as an SVG in the code (`icons.TEXTS_UTTERANCES_SVG`), its Charis SIL Bold letters stored as outlines so it looks the same without the font.
  - ɛλicit: Josh's designs (20 October), kept as SVG shapes in `lemmatrix/elicit_art.py` (no Qt; the web page's favicon and logo are made from the same shapes by `tools/make_elicit_web.py`). **The button:** a cloud in the theme colour (lighter on dark) with ɛλ hanging from it. **Recordings waiting for review:** a grey cloud (#4d4d4d; #9a9a9a on dark) with rain in the theme colour. The letters were white on Josh's dark page; outside the cloud they are drawn in ink instead, dark on the light theme and white on the dark one, like the program's other black-and-white icon parts. **The wordmark** (cloud and "ɛλicit") is only the web page's heading, its letters white where they lie on the cloud.
- **Keyboard:** in All data and the matrices, **Delete** deletes the selected token (with confirmation), **Enter** opens it, **Ctrl+Space** plays it and **Ctrl+Shift+Space** plays its pitch, the same keys as in the token dialogue (plain Space plays too). **Ctrl+Alt+Space** opens it in Praat (19 October). **Ctrl+R** opens it and starts recording, in a row of All data or a matrix cell (an empty cell: a new token with the cell's tags), 20 October. Typing a letter no longer jumps to the next row starting with it (Qt's type-to-search, removed 19 October in every data table and the matrices: IPA symbols take several keystrokes, so the jumps only confused). All data has a Play button like the matrices, and the right-click menus have both.
- **Ctrl+Space from inside a text field** (19 October, `ui/ctrlspace.py`): with an IPA keyboard such as Keyman's SIL IPA, Ctrl+Space typed a space instead of playing, because the keyboard lets go of Ctrl while it sends the character. One filter on the whole program catches a space typed into any text field (search bars, in-place editors, the token, utterance and text dialogues, the lines' editor) while Ctrl is held, asking Windows whether Ctrl is held now (`GetAsyncKeyState`) rather than trusting the key event, drops the space, and runs the window's own Ctrl+Space or Ctrl+Shift+Space. The keyboard itself isn't touched. Ctrl+Alt (AltGr) is left alone.
- **Shift + mouse wheel scrolls sideways** (20 October, `ui/shiftwheel.py`), everywhere that scrolls: one filter on the whole program turns it into a sideways scroll (Qt's own Shift + wheel took page-sized steps).

- **File → Export:** **Filtered database (current tab)** exports what the tab shows: in All data its visible rows and columns; in a matrix the grid itself, one cell per cell, with the cell's lines (the pitch drawing as its digits) and side-by-side tokens separated by a blank line. **Entire database** exports one row per token with every lemma and token field (lemmas without tokens get a row of their own), then the utterances (section 3.10). **Tag structure** exports the groups and tags (section 3.3). CSV for now (UTF-8 with a byte-order mark so Excel reads IPA); **SFM** and **LIFT** to follow.
- **File → Export → Anonymous backup…** (18 October; IDEAS.md idea 6): a copy to share or deposit, written to a folder as `<name> (anonymous).xml` and `.notebook`, so it opens in Lemmatrix. Participants' names, descriptions and consent links always go (codes stay), and so do everyone's email addresses (20 October); the Identifiable? and Audio sharing? ticks stay, as a record of what was agreed. Choices: take out researchers' names and the owner's too; include the notebook; replace participants' names written in comments, notebook notes, questions and recorded comments with their codes (full names, and name parts of 3+ letters, as whole words); include the recordings; keep every place, or only the top two levels or the top level (the notebook's places move up to the level kept); consent forms left out, or in a password-protected (AES) zip by participant code. The report at the end lists every name replaced and reminds that free text can hold other identifying details. Needs `pyzipper` (in requirements.txt) for the zip.

### 5.2 Lemma list and column filters

- **Columns:** any lemma field. **Configure columns** (FLEx style): available fields on the left, current columns on the right, **Add >>** and **Remove** between them, up and down arrows to reorder.
- **Quick search** (the box under the list) searches all visible columns of the lemmas that pass the filters.
- **Search marks** (19 October, `ui/searchmark.py`): every search bar marks what it found in yellow (multiplied on the light theme, screened on the dark one, so the text stays readable): the lemma list, All data, Utterances, the texts list, a text's lines (Comment boxes included), Bulk edit's grids, and the notebook's and Questions window's lists. Matches are found as the searches find them (diacritics and capitals ignored, so `dɪɪt` marks `dɪɪtʰ` with its ʰ). A text's lines' search now ignores diacritics too, like the others.
- **Column filters:** each column header has a filter button. Its menu has **Show all**, **Blanks**, **Non-blanks**, and then:
  - **Open fields: "Filter for…"**, a dialogue with a search box and:
    - Anywhere (Alt+A), Whole item (Alt+W), At start (Alt+S), At end (Alt+E), Match for regular expression
    - **Match case** (checkbox)
    - **Match diacritics** (checkbox). When off, combining marks *and* modifier letters (ʰ ʷ ʲ ˠ ˤ ː ˑ …) are ignored, so `dɪɪt` finds `dɪɪtʰ`. Base letters stay distinct: ʈ never matches t.
  - **Closed fields: "Choose…"**, a dialogue with the field's list as a checkable tree:
    - Clicking a group's box ticks it and all its sub-items; Ctrl-click ticks only that item.
    - **Display usage figures** checkbox (off by default): shows how many entries use each item.
    - **Any selected** or **No selected**. For tags, also **Exactly selected**: only the exact combination (group defaults don't count).
- **Ctrl+click a lemma** (cleared when another database is opened) to show only that lemma (the other filters still apply); Ctrl+click again, or Clear all filters, shows the rest again. The first column's funnel lights up and the count line names the lemma.
- Active filters show as a highlighted funnel. **Clear all filters** is in the options bar.
- **Options bar:** Add, Delete, Edit, Configure columns, Clear all filters, quick search, CV shape filter (Stage 2; matches the Lemma field).

### 5.3 All data

- One row per token for every lemma passing the lemma filters, in file order. Cells of text fields can be edited in place. Empty English Translation cells show their predicted translation in light grey italics (section 5.9).
- **Every column has the same filter menu as the lemma list.** All columns are open by default, except Tags, which is closed (so tags can be included or excluded). Speaker can be filtered here.
- **Pitch drawings in a column too narrow for them** (All data, Utterances, Bulk edit) are cut off with an ellipsis, like text, instead of spilling into the next column (20 October).
- **Soundfile's filter menu** (18 October): Show all, **Present** (the recording is in the sound folder), **Missing** (not recorded, or not in the folder), **Rerecord** (flagged in the token dialogue), then Filter for….
- **Options bar:** Add, Delete, Edit, Play, **Move token to another lemma** (λ→λ, section 5.11), **Find missing or unlinked recordings** (icon only, the same as Tools → Find missing or unlinked recordings…, 19 October), Configure columns, Clear all filters, quick search, CV shape filter (Stage 2; matches Phonetic).
- **Right-click menu** with the same options (plus Play, and **Move to another lemma…**; the matrices' menus have it too). On the Pitch column (its digits or its drawing), **Raise pitch** and **Lower pitch**: Bulk edit's pitch shortcut for that one token, one undo step, greyed if it would go past the display range (19 October). The matrices' right-click menu has them too for a token with pitch. On the Tags column, **Filter for same** sets the Tags filter to **Exactly selected** with that token's tags (Citation for a token with none), 19 October.
- **Double-click** a token's cell to open the token dialogue; double-click a **lemma's column** (Reference, Lemma, Gloss, Word Class) to select that lemma in the lemma list instead, as in Lemma/Tag (18 October). Enter still opens the token dialogue.

### 5.4 Lemma/Tag matrix

- **Lemmas down the side, tag columns across the top**, with the columns' tags shown as chips in the headers.
- **Double-click a lemma** in the side header (or the top one, with rows and columns swapped) to select it in the lemma list.
- **The lemmas are the ones the lemma list shows**, whatever their word class (18 October: there is no matrix class any more). To see only nouns, filter the lemma list's Word Class column.
- **A count line under the matrix's options** (bottom panel), e.g. "155 lemmas shown of 300", with the matrix's messages (e.g. Blank matrix…). Tag/Tag's says which lemma it shows. All data's says how many tokens are shown. Nothing above the matrix since 18 October.
- **Blank until a matrix is configured or a saved one chosen** (18 October; it used to show every tag combination present). Configure matrix → Restore all present still fills in every combination the shown lemmas have.
- **Show only lemmas with token data** (in the options row under every tab, section 5.1): here it hides lemmas with nothing in any of the matrix's columns; the count line says how many are hidden.
- **Options bar:**
  - First row: **Add, Delete, Edit, Play** (for the selected token, also in a **right-click menu** on a token, together with **Play pitch** and **Open in Praat**), **Configure cell**, **Configure matrix**, **Clear matrix** (the reset-filters icon, as for Clear all filters: a matrix is a kind of filter).
  - **Configure cell:** what each cell shows. Everything can be included or excluded: the pitch drawing, Pitch, Phonetic, Phonemic, Translation, Comment, other token fields. The ticked lines keep their order; each unticked one waits in its usual place (the token fields' order), so ticking it puts it there (Morphemes above Translation).
  - **Configure matrix:** the list of columns. Each column is a set of tags plus a match type:
    - **Citation:** the token with no tags.
    - **Exact:** exactly these tags (group defaults don't count, so Exact PL still shows PL + isolation).
    - **Loose:** at least these tags, so Loose SG shows SG, SG + GEN, …
    - A small toolbar: green add, **duplicate** (opens a copy of the selected line, so only what differs needs changing), red remove, up and down arrows; each row shows its tags as chips and a Citation / Exact / Loose selector. A new line starts as **Loose**. **Ctrl+click** picks more than one tag in a group; OK then makes one line for each combination (3SG.A, 3PL.A × FUT1, FUT2 gives four lines). Editing a line that way keeps the first combination in its place and puts the rest just below.
    - **Remove all** empties the list; **Restore all present** refills it with every tag combination the shown lemmas have (Citation, then Exact columns).
  - **Save matrix:** saves the current configuration under a name and reloads it. Saved Lemma/Tag matrices are listed in Lemma/Tag and saved Tag/Tag ones in Tag/Tag. The lemmas shown are never saved; they always come from the lemma list.
  - **Rename matrix** and **Delete matrix** act on the chosen saved matrix.
  - **Clear matrix** (first row) returns the view to blank (no rows or columns) until a matrix is configured or chosen.
- **Several tokens matching one cell** (Loose, or duplicates) are shown **side by side**, in tag order, each with a small chip saying what it adds (e.g. "+GEN").
- **Cells don't show a play marker.** Double-clicking a token opens it; double-clicking an empty cell creates a token with that cell's tags and the session's speaker and date.
- **Tags down the side wrap** (20 October): with the axes swapped (and in Tag/Tag's rows), a header's chips wrap onto more lines once it is 170 px wide, and the row grows to fit, instead of being cut off.
- **Tags across the top wrap too** (20 October): onto two lines at most. A column is as wide as its data, and only widens past that when its tags wouldn't fit in two lines; the header row (and the switch button) is two lines tall when any column needs it. A column narrowed by hand cuts the second line off with …
- **The switch button** (top-left corner, two solid arrows ⇄ in the theme colour, with a thin white edge on the light theme; lighter and without the edge on the dark theme) swaps rows and columns on screen only; the configuration itself always has its first grouping on the Y axis ("Lemma" here) and its second on the X axis.

### 5.5 Tag/Tag matrix

- **Shows the selected lemma's paradigm.** Until a matrix is configured or loaded it says "Please configure a matrix".
- **Options bar:**
  - Add, Delete, Edit, Play, also in a right-click menu.
  - **Configure cell**, as in Lemma/Tag.
  - **Configure matrix:** two lists, rows (Y) and columns (X), each a list of tag sets with a match type (Citation / Exact / Loose). Any tags can go on either axis; **cells whose row and column tags contradict** (e.g. 1SG.A × 3SG.A) are greyed out and can't take a token.
  - Duplicate, Remove all and Restore all present as in Lemma/Tag; here Restore all present gives one Loose line for each tag the shown lemmas use.
  - **Save matrix**, **Rename matrix**, **Delete matrix** and **Clear matrix**, as in Lemma/Tag (a saved Tag/Tag matrix works for any lemma; the row and column headers mark tags that aren't usual for it).
- Side-by-side tokens, switch button and double-click behave as in Lemma/Tag.

### 5.6 Token dialogue

*Based on the user's "Edit Token" mockup.* Used for both creating and editing tokens.

- **Push to question** (18 October): a green ? button beside the Comment box. The comment becomes an open question in the notebook on the session's day (today with No date; a day without notes gets them, with the Current Session's people and places), linked to the token, and the box is cleared. A new token is saved first, so the link works.
- **Rerecord flag** (18 October): a faint grey thumbs-down at the top right of the recording area; click it to flag the recording to be made again (it turns red), click again to unflag. Recording over it unflags it. Saved with the token (`rerecord="yes"`) and found with All data's Soundfile filter → Rerecord.

- **Size and place remembered:** however it is closed, the dialogue opens next time at the size and place it had (on this computer).

- **Entry header** at the top: the entry's reference, lemma and gloss (e.g. D001 dʌ́ʌm "goat").
- **Left: token fields** (no "Edit Token" title above them; the header says enough): pitch rendering (live), Pitch, Phonetic, Phonemic, Translation (primary gloss language), Comment, custom fields.
- **Right: tags** as chips grouped under their group names (small, italic, grey) and their top-level groupings' names (NOUN, Phonological…: bold, in the theme colour; also in Configure matrix's tag picker). The groups usual for the lemma's word class are shown, plus any group the token has a tag in; **Show all tags (N more groups)** shows the rest (section 3.3); it is a plain button, not bold, dark grey on grey (light grey on dark grey in the dark theme). A tag that isn't usual for the lemma has a dashed amber outline when picked, and a note under the tags says why, with **Don't show this again**. Picking a tag deselects the others in its group; clicking a picked tag clears it. **Unpicked:** white with a light-blue outline. **Picked:** filled light blue.
- **Bottom: recording panel:** live file name; speaker and date (from the session, changeable for this token); and four icon buttons, each with a tooltip giving its name and shortcut:
  - **Record:** purple rounded square with a white microphone; while recording it becomes a red rounded square with a white square (stop). A small level meter shows clipping or silence.
  - **Play:** green rounded square with a white triangle.
  - **Delete recording:** red rounded square with a white X. Asks first (unless confirmation is off) and moves the file to the Recycle Bin.
  - **Update file name:** blue rounded square with a white update arrow; enabled when the name is out of date and automatic updating is off.
  - **Open in Praat:** teal rounded square with a white waveform; opens the recording in Praat's sound editor (greyed out when there's no recording). Praat's location is set in Settings → Sound; if it isn't known yet, Lemmatrix asks for it the first time.
  - The same options are in a **right-click menu** on the recording panel.
  - Under the file name, the recording's **full path** (or where it will be saved).
- **Pitch rendering:** its height follows the display range (one level is a fixed fraction of a step), so it stays compact. Typing the IPA length mark ː in Pitch gives a colon. A small **play-pitch** button beside it plays the pitch in the chosen voice (also on its right-click menu, and Ctrl+Shift+Space).
- **Bottom row: Back, Next, OK, Cancel.** Back and Next save and move column by column through the current matrix (row by row in All data).
- **Keyboard:** Ctrl+R record/stop, Ctrl+Space play, Ctrl+Shift+Space play pitch (both work with the cursor in a field, and never type a space there: some keyboard layouts and IPA keyboards would otherwise let the field take the key; 18 October), Alt+← / Alt+→ back and next. Ctrl+← / Ctrl+→ jump a word in a text field, as usual; **→** accepts a predicted translation (section 5.9); Tab and Shift+Tab go round the token's fields only (Phonetic, Phonemic, Pitch, Translation, Comment…), selecting each field's text; tags, speaker, date and buttons are for the mouse (Josh, 17 October: fine for now).
- **Recording settings** (source, bit depth, sample rate) are per-computer preferences in Settings only.
- **Other languages** (20 October): with more than one gloss language, a folded **Other languages (ar)** button under the fields opens a Translation row per second language (Tab goes through them when open; Ctrl+Space plays from them). Open or closed as last left, on this computer (section 3.2).
- **Later, not in Stage 1:** "Insert character" beside Phonetic and Phonemic.

### 5.7 Saving and safety

- **Undo and redo** are always available.
- **Timed autosave**, every 5 minutes by default (on since 18 October; Settings → General changes it, 0 turns it off).
- **Backup copies:** on each save, the previous version goes into the Backups folder next to the database (the notebook's too). Kept (Josh, 18 October): the **10 most recent**, and spread out in time: the newest of each of the last seven days (so yesterday's and the day before's, and one that becomes a week old), the newest of each week before that up to five weeks (so one becomes a month old), and the newest at least a month old: about 22 at most.
- **Saves are flushed to the disk** before they replace the old file, so a power cut or a dead battery leaves the old file or the new one, never half of one.
- **A second Lemmatrix on this computer** gets a warning when it starts: "Another instance of Lemmatrix is currently running on this computer. Please save and close it before starting another to avoid bugs."
- **Full backups** (File → Full backup, section 3.9): the whole main folder as one dated zip, with a weekly reminder. *Save as* was removed on 18 October, with its warning about moving soundfiles.

### 5.8 Bulk edit

*Agreed 17 October, from a layout mockup; modelled on FLEx's Bulk Edit.*

- **Edit → Bulk edit…** (Ctrl+E) opens a **window of its own**, which stays open beside the main one. Its size, place and splitter are remembered as they are adjusted (20 October). It first opens as big as fits the screen (at most 1360 × 900), and a remembered size that no longer fits, or a window partly off the screen, is brought back inside it, as for Texts and utterances (`winstate.fit_to_screen`, 20 October). Its title "Bulk edit" is in the theme colour; its tabs look like the Matrix's.
- **Lemmas and Tokens tabs.** Lemmas: one row per lemma, and only lemma fields (and Gloss in file names) change. Tokens: one row per token of the lemmas the Lemmas tab shows; the lemma columns stay visible but **greyed, as in All data**, and only token fields, tags, speaker and date change. The window opens on Tokens.
- **The grid** works like the lemma list and All data: the same columns (Configure columns, remembered separately), the same column filters, quick search and Clear all filters (the reset-filters icon). It **starts with the main window's filters**, then has its own. Every row has a **tick** (all ticked to begin with; the ✓ column can be filtered too), with Tick all shown, Untick all shown and Untick selected. Only shown, ticked rows are changed.
- **Operations** (tabs under the grid):
  - **Replace:** Field, Find, Replace with; options **Regular expression** and **Match case**.
  - **Shortcuts:** three drop-downs, **Shortcut**, **Direction** and **Field** (only the fields the shortcut suits, by role, so renamed fields still work). Built so far:
    - **y / j:** y → j or j → y, for data that mixes the two symbols for the palatal approximant (Lemma, Phonetic, Phonemic). ʲ and ʸ are left alone.
    - **Tie bar on affricates:** add or remove the tie bar between a stop and the fricative at the same place (t͡s, d͡ʒ, t͡ʃ, p͡f, k͡x…). Labial-velars (k͡p) keep theirs.
    - **Pitch:** raise or lower every digit by one. **If any ticked token would go past the display range** (a 5 with the range 1–5, or a 1), it's an error and nothing changes, so the data isn't distorted.
  - **Set value:** a field (a closed field's list, or a new value added to it), **add or remove a tag** (adding one takes off any other tag of its group; a tag that isn't usual for a lemma is allowed, and the preview counts those tokens), the speaker, the date (no future days), or the word class (an ordinary closed field: the tags stay as they are).
  - **Copy:** one field into another: Overwrite, Append (after a space) or Only where empty.
  - **Clear:** empty a field.
  - **Predict** (section 5.9): fills empty English translations with their suggestions (Tokens tab only); translations already there and tokens without a suggestion are left alone, and the preview counts both. It learns from the database as it is, not from the suggestions it is filling in. The preview shows each suggestion, so wrong ones can be unticked.
  - **Conditions:** a greyed placeholder tab for syllable and environment conditions (y → j only before a vowel), which arrive with Stage 2.
- **Options** (each can be turned off or on; these are the defaults):
  - **Keep diacritics: on.** Tone and other marks stay on the new letter: y → j turns ỹ into j̃ and ý into j́. Off: a letter carrying a mark counts as a different letter and is left alone. Modifier letters (ʰ ʷ ʲ) are letters of their own, so yʷ becomes jʷ either way. (Text is compared decomposed; in a regular expression a letter and its marks are separate characters.)
  - **Rename soundfiles: on.** The preview warns how many recordings will be renamed and names them. Off: the names are left out of date, and the preview says how many.
  - **Update comment dates: off.** Changed comments keep their dates. On: the preview warns that they'll be dated with the session's date and go into that day's notebook record.
- **Preview** shows every change in the grid before anything happens: the new value in bold on the accent wash, the old one struck through after it (both in the tooltip), and problems in red with a ⚠. The box beside the options counts the changes ("10 of 26 ticked tokens will change") and lists what else happens: renames, out-of-date names, recordings not in the sound folder, comments, converted tags, new tags, new list values, and that a speaker change doesn't touch the recordings' own metadata.
- **One problem cancels the whole operation:** Apply stays greyed and the box lists the problems (the same one in many rows is one line, with the references). Problems: past the pitch range, two tokens of a lemma with the same tags, two tags of one group, a recording whose new name is taken (or two that would get one name, or recordings that would swap names), characters forbidden in file names, a date in the future, an invalid regular expression.
- **Apply** makes the change as **one undo step** (Ctrl+Z works in the window too), recordings renamed included and renamed back on undo. It checks again first, in case anything changed since the preview. Any change to the operation, the options, the ticks or the filters clears the preview.

### 5.9 Predictive translation

*Agreed and built 18 October.* The engine is `lemmatrix/predict.py`.

- **What it does:** a token whose English Translation is empty gets a suggested translation, in grey italics in the field. **→** accepts it (the field is empty, so → does nothing there otherwise); typing anything replaces it. Nothing is written until it's accepted, and accepting is an ordinary edit (undo works).
- **English translations only:** the token's Translation field with `lang="en"`. Glosses are never predicted: the lemma's English gloss is what the suggestion is built from. Other translation languages get no suggestions (there is no Arabic translation field; anyone adding one is on their own).
- **Templates learned from the data:** for each token with an English translation, Lemmatrix looks for the lemma's English gloss in it as whole words (bracketed notes and any second gloss after ; , or / left out; a leading "to " ignored when the translation doesn't have it; inflected forms found with `lemminflect`, an ambiguous past form read as a participle after have, be or get) and turns it into a template for that token's tags. *father* with SG, 2POSS translated "your father" gives "your {gloss}" for SG + 2POSS, so *mother* with the same tags is offered "your mother". The gloss is inflected as the template needs (goat → goats, man → men, eat → ate); where it can't be, there's no suggestion.
- **Choosing a template:** the token's exact tag set first, with group defaults left out of the comparison (as in Exact columns), so a new token's Simple or isolation doesn't stop it matching converted data. Templates from lemmas of the same word class come first (Kinship before Relational before NOUN), then those from every lemma; if several compete, the most common one wins, and a tie goes to the template from the earliest lemma in the database. The tooltip says what the suggestion is based on (e.g. "from father, uncle, brother"). *Proposed:* when no template has the exact tags, one whose tags differ only in groups that don't change the translation (e.g. Phonological, Frames) is used. Combining templates (PL + GEN from a PL one and a GEN one) is left out for now.
- **Nothing stored:** the templates are worked out from the database when it opens, kept in memory, and updated straight away as translations are typed, changed or deleted. Nothing goes into the XML, and there is no side file.
- **No marker on accepted suggestions** (Josh, 18 October): an accepted suggestion is an ordinary translation and becomes evidence for further suggestions. A wrong one then turns up again and again, which makes it easier to notice; Bulk edit's Replace fixes it everywhere at once.
- **No AI:** everything runs offline in Lemmatrix, and no data leaves the computer.
- **Where** (when the primary gloss language is English):
  - the token dialogue's Translation field;
  - **All data** (Josh, 18 October: option 2): every empty Translation cell shows its suggestion in light grey italics, with what it's based on in the tooltip. It is only shown: the cell stays empty for filters, search, sorting and export. Double-clicking the cell (or F2) shows the suggestion in the editor too, and → accepts it; the right-click menu has **Accept suggested translation**. → outside editing still moves to the next column, as before;
  - Bulk edit's **Predict** tab (section 5.8).

### 5.10 Spelling

*Agreed and built 18 October.* The checking is `lemmatrix/spelling.py`; the windows' part is `ui/spellui.py` and `ui/spelling_dialog.py`.

- **What's checked:** the English gloss and the English translation only (utterances' too, since 19 October). Other languages, transcriptions, comments and the matrices aren't.
- **Not checked** (glossing conventions, not spelling): anything in brackets, words with digits, words in capitals (1SG, PL, NOUN) or with a capital inside them (xH), single letters, and words with letters outside English (IPA, Arabic). A possessive counts as its word (goat's, goats').
- **Two word lists, either is enough:** `pyspellchecker` (general English, the little words included, but American spellings only; also gives the corrections) and `lemminflect` (nouns, verbs and adjectives with all their forms, British spellings included: colour, favour, recognise). Corrections are words one change away (a letter added, dropped, changed or two swapped), most common first; Check spelling's chosen word also gets those two changes away.
- **The database's own word list** (Josh, 18 October: in the database, so it travels with it): a `<spelling>` element in the settings, one `<word>` each, alphabetical; not written when empty. Words are matched without regard to capitals.
- **Underlines:** a red wavy line under each unknown word, in the token dialogue's Translation, the lemma dialogue's English gloss, the lemma list's English gloss and All data's Gloss and Translation (and their in-place editors). Not in the matrices (Josh, 18 October). The fields themselves are unchanged: a transparent layer on top draws the lines. **Settings → General → Warnings → Underline English words that may be misspelled** turns them off (per computer).
- **Right-click** on an underlined word (in a field or a cell): the corrections, which replace the word, and **Add “…” to the word list**.
- **Tools → Check spelling… (F7):** a window of its own beside the main one. Every unknown word, most frequent first, with how often, where (Gloss, Translation) and the first suggestion; under it the chosen word's occurrences (reference, lemma, field with the token's tags, text; double-click goes to the lemma or token). For each word: **Replace with** (a suggestion or typed) **everywhere**, one undo step, keeping a capital where the word had one; **Ignore** (until Lemmatrix is closed); **Add to word list**. The list follows undo and other changes.
- Glosses are where predicted translations come from (section 5.9), so a misspelled gloss would spread into its suggestions; the check catches it at the source.

### 5.11 Moving a token to another lemma

*Agreed and built 19 October (IDEAS.md idea 11).* The moving is `lemmatrix/move.py`; the lemma picker is `ui/move_dialog.py`.

- **Where:** the λ→λ button in All data's options bar (in the theme colour, icon only) and **Move to another lemma…** in the right-click menus of All data and the matrices. It moves the selected token (one at a time: All data selects one row).
- **Choosing the lemma:** a search box (reference, form or gloss; diacritics and capitals ignored) over a list of the lemmas, those of the token's own word class first; the token's own lemma isn't offered. Enter or double-click moves.
- **Any lemma** (not only the same word class): tags don't belong to word classes (section 3.3), so a moved token keeps its tags, and any that aren't usual for the new lemma are marked with the dashed amber outline, as anywhere; the status bar says so.
- **What moves:** the token with its id (so notebook links and comments follow it), fields, tags, speaker, date and recording. The translation stays as it is.
- **The recording** is renamed with the new reference and gloss when names update automatically (Settings → Sound), as part of the move; otherwise its name is left out of date (the status bar says so; Update file name renames it).
- **A citation token** (no tags) takes the place of the new lemma's citation token if that one is empty (nothing typed, no recording); the old lemma just loses it, as if it had been deleted.
- **Same tags as a token already in the new lemma** (or a recording name already taken): the Example tag is offered, **Add x1** (the first free one; a new Example N if all are taken), **Move it as it is** (its recording then keeps its old name) or Cancel.
- **One undo step**, the rename included.
- **Later:** several tokens at once, from **Bulk edit only** (Josh, 19 October: All data stays one row at a time, or there'd be no point to Bulk edit), and turning a token into an utterance or the reverse.

### 5.12 ɛλicit, remote elicitation (stage 1)

*Built 20 October (IDEAS.md idea 19; stage 1 of the build order, with the requests and the review of stages 3 and 4 in a first form, and no cloud yet).* The request, the response and the review are `lemmatrix/elicit.py` (no Qt); the prompts are `lemmatrix/elicit_prompts.py`; the dialogues are `ui/elicit_dialogs.py`; the web page is `docs/elicit/` (GitHub Pages: `https://smojos.github.io/Lemmatrix/elicit/`, once Pages is switched on for the repository's `docs` folder). Formerly written EλICIT; **ɛλicit** since 20 October (Josh).

- **The loop (stage 1; stage 2's link through Google Drive below):** Make ɛλicit request writes a zip (the request) → the researcher sends it by WhatsApp, Signal or email with a link to the page → the speaker opens the page, opens the file and records → the page gives the recordings back as a zip, which the speaker sends → **Receive ɛλicitation** reads it → the review puts the approved recordings in. In stage 1 nothing is uploaded anywhere: the files travel by hand. **No soundfile goes through GitHub**: Pages serves only the page itself, and the recordings stay on the phone until the speaker sends them (stage 2: straight to the researcher's own OneDrive or Google Drive).
- **Make ɛλicit request…** (the button's menu; needs a saved database and a participant). **Layout** (Josh, 21 October): the settings take the left half, under the title, and the ɛλicit wordmark (the web page's heading, in the theme's colours; `icons.elicit_logo`, the white letters masked by the cloud since Qt draws no SVG clip paths) the top right; a subtle line, then **Tokens and Utterances** (bold, its explanation in the hover tip, ⓘ) with the search and the list; another line, then **New Utterances** (the same) with the program's green plus and red X (Add a sentence, Remove the selected sentences; names in the tooltips); the two sections share a splitter, adjustable; **Make request…** in the theme colour; Reset request bottom left.
  - **Speaker** (a participant; the session's speaker first), **Researcher**, **Second language** (a gloss language other than the primary one, or None; the first one by default; one without built-in prompts gets English prompts only, and says so), **the language's name in the second language** (for "How do you say this in …?", e.g. *italiensk*; the database's language name if empty), and **Ask for tokens to be said 2 or 3 times** (ticked; utterances are said once). This settles the repetitions question as a setting per request.
  - **The list:** every lemma token and utterance, with a tick, its reference, form, tags, what the card shows, its recording's speaker, ✓ if it has a picture, and its card: **Rerecord** if it has a soundfile (the card plays it, to be repeated), **New** if it hasn't (the card shows the gloss or translation). There is no choosing (Josh, 20 October: a token or utterance with a soundfile is a rerecord request, otherwise a new one); double-clicking a row ticks it, and the status bar says which kind a right-click Add made. A search over the columns, Everything / Lemma tokens / Citation tokens / Utterances, Ticked only, **Tick the tokens All data shows** (the main window's filters do the choosing) and Untick all. **It always opens on everything** (Ticked only off), so anything can be searched for and ticked (Josh, 20 October: it used to open on the selected token alone). **Right-click → Add to ɛλicit request** (with the ɛλicit icon; **Remove from ɛλicit request** once added) in All data, the matrix cells and Utterances ticks a token or utterance for the next request; the ticks are kept when the dialogue is closed (as they were left in it), cleared once a request is made, and belong to the open database (in memory, not saved). **So are its settings and new sentences** (Josh, 21 October): speaker, researcher, second language and its name, the repetitions tick and Send as come back as last left, and the new sentences typed in too; a request made clears the ticks and sentences and keeps the settings. **Reset request** (bottom left, after asking) unticks everything and clears the new sentences; the settings stay. The first ticked row is scrolled into view.
  - **New utterances:** sentences typed in, with their English and second-language translations; each answer becomes a new utterance on review.
  - **Cards follow the list's order** (lemmas, then utterances, then the new utterances). The count line says how many cards, how many rerecords and the size with the recordings coming back.
  - **Warnings before sending** (one message, Make it anyway or Go back): a non-citation token or utterance asked for anew with **no Translation** (its card shows the lemma's gloss and the tags that say something, e.g. *book (Plural)*; default tags are left out); a rerecord whose recording has no speaker, a speaker not in the list or one who hasn't ticked **Audio sharing?**: "This could potentially constitute an ethics violation"; a request over about **50 MB** (pictures, originals and an estimate of the recordings coming back). Then the **ethics reminder**: send it only to that person, who has a participant agreement with you (with a note if no consent form is linked).
  - **What a card shows:** a citation token its glosses (English and the second language); any other token, or an utterance, its Translation in both; a rerecord nothing but the ear button (the original is the prompt). Glosses and translations only from the database, never machine-translated.
  - **Pictures** come from Images (section 3.9), for new token cards only (not rerecords, not utterances); one with a longer side over 500 px is shrunk when the request is made, an animated GIF keeping its frames (needs `Pillow`, added to requirements.txt).
  - **The request's folder:** `Elicit/<date>_<speaker>_<id>/` with `request.json` (every card, with the ids of its lemma, token or utterance: what the recording will link to), the zip to send (`Elicit_request_SP1_2026-10-20.zip`: `request.json`, the pictures and the originals, **stored, not compressed**, so the page reads it without a library), and later `received/` and `review.json`. The request's data is JSON rather than XML, since the page reads it.
  - **Then:** the message to paste with the file, in English and the second language ("Hello {name}! {researcher} would like you to record some words. Please open {link}…"), with **Copy the message** and **Show the file**. Requests **expire** 14 days after they are made.
- **The web page** (`docs/elicit/`: plain HTML, CSS and JavaScript, no libraries; prompts in English and the request's second language, one under the other):
  - **Opening:** "Open the request file" (English only, before a request is open; the pasted message says it in the second language too). A request already started on this device is offered again: **Carry on**, from the first card not answered, after the three questions again (whoever holds the phone now may be someone else).
  - **The flow** as agreed (IDEAS.md idea 19): Are you {name}? (No → Please give your phone or device to {name}: OK, or {name} is not around → thanks, please let {researcher} know); Have you signed a participation agreement with {researcher}? (No → Please contact {researcher}… → the request is deleted from the device); Do you speak {language}? (No → Goodbye); the opener, with "When your phone or browser asks, please allow the microphone"; **I'm ready** asks for the microphone.
  - **Cards:** the progress line ("3 of 11", in both languages) and a bar; for a new card "How do you say this in Italian?", the picture, the gloss or translation (large), and "Please say it 2 or 3 times" when asked; for a rerecord "Please repeat this exactly" and a large **ear** button that plays the original. A big red **record** button (with a level meter) becomes a stop button; the recording then plays back with **Listen**, **It's good** (next card), **Try again** and **I can't say this one** (a literal wording; next card). No Back.
  - **A gentle fade between screens** (Josh, 20 October: "a calming fade-to-next"): the screen fades out in 0.22 s and the next fades in over 0.32 s; taps are ignored meanwhile; nothing fades on a device set to reduce motion.
  - **Recording:** the browser's microphone with echo cancellation, noise suppression and automatic gain **off**, at the device's own rate (usually 48 kHz), mono, saved as **16-bit WAV** with the speaker's code and the date in its INFO metadata, as Lemmatrix writes them. *Stage 1 sends WAV, not FLAC:* lossless too, about twice the size; FLAC can come with the uploads (stage 2).
  - **Kept on the device** (the browser's IndexedDB, asked to be persistent) after every card, so closing the page loses nothing; deleted when the speaker presses **I've sent it**, or when the request is rejected (not around, wrong language) or ended (no agreement), or has expired.
  - **End:** "Are you finished? Thank you very much!" → **Goodbye** → "Please send the recordings to {researcher}" with **Send** (the phone's share sheet, e.g. straight into WhatsApp, where the browser can share files), **Save the file** and **I've sent it** → "Thank you! You can close this page now." The file is `Elicit_recordings_SP1_2026-10-20.zip`: `response.json` (the request's id, the speaker, and per card recorded or skipped, with the file, the time, the device's date, the length and the rate) and `recordings/`. Cards not reached aren't listed.
  - **The researcher's theme colour** comes with the request and colours the page; light or dark with the device. The favicon is the main ɛλicit icon (its letters dark or white with the browser's mode); the heading is the wordmark; home-screen icons `icon-180.png` and `icon-512.png`.
  - **Safety:** the request's text is only ever put on the page as text (never as HTML). The page has `noindex`.
- **Receive ɛλicitation…** chooses the speaker's zip (Downloads first) and unpacks it into its request's `received/` folder (a zip answering a request this database didn't make is refused; one received again replaces the earlier copy), then opens the review.
- **The review dialogue:** a row per card (#, what was asked for, New / Rerecord / New utterance, what came back: "Recorded (1.3 s)", "Skipped by SP1", "Not reached"; the decision). **Play new** (Space, double-click), **Play old** (a rerecord's recording now), **Approve** / **Reject** (A, R; for a rerecord **Keep new** / **Keep old**), **Undecided**, **Approve all** (every recording not decided yet); each recording plays when selected (a tick to turn that off); a decision moves on to the next one waiting.
  - **Closing applies** the decisions as **one undo step**: approved recordings go in under the token's or utterance's name (the speaker and the recording's date set on the token, its rerecord flag cleared; a recording replaced is held in `_Deleted recordings` like a deleted one, so undo brings it back, and goes to the Recycle Bin when the database closes); a **new utterance** gets the next U reference, its translations, and a file label from the first six words of its English translation. Rejections are noted. **Where new sentences went** (Josh, 21 October: they seemed to vanish, since utterances aren't in All data): after the review, a message names them ("The new sentence is now utterance U004 ('The sun is hot')…, in View → Texts and utterances → Utterances") with **Show them**, and the review's Decision column says "Done (utterance U004)".
  - **Save for later:** anything not decided waits. So does an approved recording that is no longer in the database (undone, or the database closed without saving): `review.json` notes each approved recording's name and size, and the card waits again if the token doesn't have it.
  - **Waiting recordings:** the button shows the rain cloud and its tooltip says how many; its menu gets **Review waiting recordings (N)…**; and opening the database says "ɛλicit: 12 recordings from SP1 are waiting for review." with **Review now** and **Later**, like the full-backup reminder.
  - **Send again…:** the skipped and rejected cards in a new request for the same speaker (rerecords stay rerecords, new utterances keep their translations).
- **Prompts** (`elicit_prompts.py`): English, Danish, Italian, French, Spanish, Portuguese, German, Dutch, Swahili, Arabic (right to left) and Amharic, machine-translated once (20 October) and to be corrected from feedback. Polite forms (vous, usted, Sie, u), except Danish and Italian (du, tu). A gloss language such as `ar-SD` uses `ar`'s prompts.
- **The test database** (`samples/Elicit test`, built by `samples/make_elicit_test.py`; **File → Open a copy of the ɛλicit test database** copies it to `Documents\Lemmatrix Elicit Test`): Italian (ITA, variety STD) with Danish as the second gloss language; 12 lemmas and 3 utterances, Josh's own recordings (acqua, casa, libro, sole, torta; il gatto dorme, le mie due torte grandi), and placeholder pictures drawn by the script (a cat, two cats, an animated sleeping cat for *dormire*). Each lemma's Comment says how to ask for it, so one request covers every case: new citation tokens with and without a picture, tagged tokens with and without one, a GIF verb, a tagged token with no Translation (*libri*: the warning), rerecords of a token and an utterance, a rerecord by SP2, who hasn't agreed to audio sharing (*sole*: the ethics warning), an utterance with no recording (U003), and new utterances typed in; cane, casa, mangiare, grande, due and U002 are not to be asked for.
- **Tests:** `tests/test_elicit.py`, including the whole loop through the real page in Chromium with a fake microphone where Playwright is installed (skipped otherwise).
- **Stage 2, through Google Drive** (built 20–21 October; Josh: zips don't download from WhatsApp on Android, and speakers wouldn't know where to send one back). `lemmatrix/gdrive.py` (standard library only), `lemmatrix/cloud_keys.py`:
  - **Lemmatrix's own Google Cloud project** (Josh's): a Desktop OAuth client and a browser API key, written into `cloud_keys.py`. They are public on purpose: a desktop app's client secret can't be kept and Google doesn't treat it as secret; the key is restricted to `https://smojos.github.io/*` and the Drive API. Until they are there, requests go as zips only (the choice is greyed out).
  - **Signing in:** the first Drive request opens the browser on Google's sign-in (installed-app flow: a one-off server on 127.0.0.1, PKCE). Only **drive.file** is asked for: Lemmatrix sees the files it makes, nothing else. The lasting sign-in (refresh token) is kept per computer (`elicit/google_token` in the settings); **Sign out of Google Drive** in the ɛλicit menu (while signed in) withdraws it.
  - **Make ɛλicit request → Send as: A link, through your Google Drive** (the default once the keys are there) or **A file (zip) to send by hand**. A Drive request makes `ɛλicit/<date>_<speaker>_<id>/` at the top of the Drive (the folder isn't shared); uploads the pictures, the recordings to repeat and `request.json`, each **shared by link** (reader); and makes a **resumable upload link** for every card's recording and two more, for `response.json` (finished) and `status.json` (turned down). Google keeps upload links for a week, so **Drive requests expire after 7 days** (zips: 14). Anything going wrong deletes the folder again. The local `Elicit/` folder keeps `request.json` (with the Drive ids), no zip.
  - **The message** is just the text (English and the second language: "Hello {name}! {researcher} would like you to record some words. Please open this link on your phone or computer:") and the link on its own last line, with **Copy the message** and **Copy the link only**. The link is `https://smojos.github.io/Lemmatrix/elicit/#d=<request.json's id>&k=<API key>`: after the `#`, so it never reaches GitHub's server.
  - **The page** reads the request and its files from Drive with the key, then everything is as before, except: each recording **uploads as soon as it is good** (in order; kept on the device until it has; again when the phone comes back online); at the end, Goodbye shows "Sending the recordings… 7 of 10", waits for the internet if need be ("Your recordings are safe on this device…"), uploads `response.json` and says "Your recordings have reached {researcher}. Thank you very much!" Turned down on the phone (not around, no agreement, doesn't speak the language), it uploads `status.json` with the reason. Opening the link again on the same device carries on.
  - **Receive ɛλicitation** with Drive requests out opens a window listing them (speaker, made, expires, and what is there now: "finished: 10 recordings", "3 of 11 recorded so far", "turned down on the phone (not around)", "expired"), checked in Drive when it opens (**Check again**): **Download and review** (an unfinished one: take what has come and end the request, after asking), **Withdraw…** (deletes its folder), and **From a zip file…**. Downloading puts everything in `received/` and **deletes the request's folder in Drive** (destroyed means destroyed), then the review opens as before.
  - **The button rains for Drive requests too** (Josh, 21 October): on opening a database and every 10 minutes, when signed in, Lemmatrix looks in Drive in the background for requests out that have finished or were turned down; any such request makes the rain cloud show, the tooltip says "SP1 has finished: 10 recordings in Google Drive (Receive ɛλicitation)", and the status bar says so once. Offline or signed out, it just looks again later. The tooltip also says how many requests are out.
  - **One sign-in per computer**, not per database: every database on the computer uses it, and they share the Drive's ɛλicit folder. On a second computer (a database in a synced folder) Lemmatrix asks to sign in once there; the requests in the database's Elicit folder can then be checked and downloaded from either, since drive.file belongs to the person and the app, not to a computer.
  - **Tested by Josh on 21 October, on his Android phone through WhatsApp: it works**, Google answering the page's uploads (Lemmatrix sends the page's origin when it makes the upload links). While waiting for the internet, the page shows the last upload error in small grey text, for diagnosis.
  - **The keys in the public repository:** GitHub's push protection flagged the client ID and secret; Josh allowed them (21 October), as other open-source desktop apps do (Google: for installed apps "the client secret is obviously not treated as a secret"). The worst case is misuse of the project (quota, or Google suspending it), never access to anyone's Drive; the project has no billing account, so nothing can be charged. A second owner can be added to the project later.
  - **The privacy policy** Google asks for is `docs/privacy.html` (https://smojos.github.io/Lemmatrix/privacy.html), linked from both pages; the home page is `docs/index.html`. The consent screen has no logo, so that Google doesn't review the app.
  - **Tests:** a stand-in Drive in memory for publishing, checking, unfinished and turned-down requests and receiving; the Drive client's requests against a stand-in for urllib; and the page's link route in Chromium with Google's endpoints stood in for.
- **Later stages:** OneDrive (if Google works out, perhaps not needed), FLAC, a notice to the researcher's email.

## 6. Roadmap

- **Stage 1, Windows prototype:**
  - The file format, with open and save.
  - The tag structure dialogue (nested groups and tags, with "usual for" hints), with the default structure.
  - The main window as in the mockup: filterable lemma list with entry buttons and search on the left, the matrix view on the right in all three modes, the matrix toolbar (including Play cell), and the current-session panel.
  - The token dialogue, with built-in recording, level meter, tagging, Back/Next and keyboard shortcuts.
  - File-name pattern settings, with the live file name shown on each token, and file-name updating (automatic or by button).
  - Per-field fonts and sizes.
  - Recording and playback per token, from the microphone or computer audio.
  - Undo and redo, optional autosave, and backup copies.
  - Then: converting existing Dekereke databases (section 4).
  - Estimate: a first runnable version within 1–2 working sessions, and a solid prototype in about 2–3 weeks, depending on how often it can be tested.
- **Stage 2, analysis engine:** segment parsing, features, syllabification, CV shapes (including both CV shape filters), consonant and vowel charts, feature-based search and pitch tools (including the drawn contour display). Results get checked against other tools' output on the same data.
- **Stage 3, other formats and extras:** LIFT, Toolbox/SFM, HTML and LaTeX import and export; formant plots; and so on.
- **Later ideas:**
  - Play glosses with text-to-speech (e.g. Google).
  - Machine-translate glosses (needs internet access and probably an API key).

## 7. Design sequence and open questions

**Sequence:** 1. Data design (nearly done) → 2. Default categories and customisability → 3. Functionality → 4. UI (first mockup in; more to come).

**Settled on 20 October (ɛλicit stage 1, section 5.12):** the name is ɛλicit (formerly EλICIT); the button left of Texts and utterances with Make ɛλicit request and Receive ɛλicitation; the rain cloud while recordings wait; the favicon is the main icon; requests as zips sent by hand in stage 1, the page on GitHub Pages (no soundfiles through GitHub); WAV for now; a per-request tick for "Please say it 2 or 3 times"; the language's name in the second language; a calming fade between the page's screens; the Italian/Danish test database with Josh's recordings.

**Settled on 20 October (before ɛλicit, IDEAS.md idea 19):** second gloss languages are for speakers, not the analysis: hidden by default in every view and dialogue, shown only where configured, with what was already configured left as it was; a token's translations in them in the token and utterance dialogues (under Other languages), All data, Utterances, Configure cell and Bulk edit; researchers' emails (always taken out by the anonymous backup); the participants' Identifiable? and Audio sharing? ticks, from the consent forms; an Images folder in the main folder, a picture found by its token's reference and tag codes, with no fallback. The general meaning of "hidden" for core fields and the pitch system (idea 9) is still open.

**Settled on 19 October (evening, small features):** core fields (Comment and Morphemes included) renamable but not deletable, restored on opening if missing; descriptions on tags and groups, shown in tooltips, and a Tag structure CSV export; deleting a used tag takes it off its tokens (refused if two tokens of a lemma would then share their tags); a changed code offers to rename the affected recordings; utterances in Check spelling, Entire database export (rows of their own, with a Kind column) and Find missing recordings; moving a token to any lemma (tags kept and marked if unusual), from All data's λ→λ button and the right-click menus, the recording following the automatic renaming setting, an empty citation token replaced, the Example tag offered for clashes.

**Settled on 19 October (editing text lines, section 3.12):** the TextGrid is the only store, written on save with a backup; boundaries only in Praat, placeholders in the main tier for untranscribed segments; LaTeX glossing rules ({braces}, {}) with the symbols hidden unless editing, to be used everywhere; clipped utterances update automatically; line comments recorded in the notebook (and a new text's comments in the day it was recorded); a Speaker tier for conversations; Configure view one setting for all; Edit mode as a toggle; lines as far right as needed with a margin on the left; transcription keys; Next empty beside the search; Josh's clip icon.

**Settled on 18 October (Push):** merge a word-level tier's segments with a warning ("This push will merge several segments in Praat"); a preview with a tick box per field; "edited here" shown in the Source column; Praat's own copy of an open TextGrid is lived with (close it first, backup in Backups, reopen at the line). The Texts and utterances window opens on Texts.

**Settled on 18 October (Pull, IDEAS.md idea 7 stage 4):** compare with what was copied, not the utterance; replace only the fields of the tiers that changed; a tier gone altogether isn't a change; re-cut offered when the times moved; Unlink for lines that are gone; check again when the window becomes active.

**Settled on 18 October (texts, IDEAS.md idea 7 stage 3):** texts as catalogue records with copied recordings and TextGrids, lines read from the TextGrid with praatio, a database tier mapping learned as texts are added and per-text mappings when they differ, speakers from @ in tier names, clipping with padding and a stored link (fingerprint included), Play in context, Open in Praat with the TextGrid, text fields in Edit → Fields, genre, status and tier mapping in Edit → Lists, the notebook's Texts tab, format 6.

**Settled on 18 October (evening, before stage 3):** no compatibility code for older formats until version 1.0, only provisional upgrades; Example codes lowercase (x1, x2).

**Settled on 18 October (utterances, IDEAS.md idea 7 stage 2):** an utterance is an entry with one token, in its own list; categories U and W–Z marked for utterances, with a Reference categories page in Edit → Lists; file names with a pattern of their own and a file label, no tags; Add, Import… and drag and drop (copies, one undo step); utterance-only tag groups as a rule; no default tags on new utterances; the Texts and utterances window with the Utterances tab; the utterance dialogue with the Lemmas box; format 5.

**Settled on 18 October (folder layout, IDEAS.md idea 7 stage 1):** a fixed layout in each database's main folder (Soundfiles/Tokens, Backups, Documentation, Exports), no sound folder setting; a database still using Soundfiles/Lexicon explained, not reported as missing; consent forms relinked by name from Documentation; one database per main folder, with a new database given a folder of its own; Save as removed; File → Full backup (zip of the main folder, full backup folder in Settings → General) and the weekly reminder; the Morphemes token field; format 4.

**Settled on 18 October (spelling):** English glosses and translations only; pyspellchecker and lemminflect together, with the database's own word list in the settings; red wavy underlines in the token and lemma dialogues, the lemma list and All data, not the matrices, switchable per computer; right-click corrections and Add to the word list; Tools → Check spelling with Replace everywhere, Ignore and Add to word list.

**Settled on 18 October (predictive translation):** English translations only, never glosses; templates from the existing translations by tag set, the gloss inflected with `lemminflect`; no AI; templates kept in memory only, updated as translations change; no marker on accepted suggestions (a repeated mistake is easier to spot, and Bulk edit fixes it); → accepts; a Fill predicted translations operation in Bulk edit (built as the Predict tab); suggestions shown in All data's empty Translation cells too, in light grey italics, accepted by editing the cell and pressing → or from the right-click menu.

**Settled on 18 October (after a code review against a real database):** Instances (Frames, Examples) with format 3, Example tags offered when recordings would share a name and never recording over another token's file; control characters kept out of files and repaired on opening; flushed saves; backups spread out in time; autosave on by default; the session date moving on at midnight; a warning for a second Lemmatrix; the Ctrl+click pin cleared on opening; Save as warning about soundfiles; Update all names as one undo step; deleted tokens' recordings held for undo; leftover code removed; Export anonymous backup.

**Settled on 18 October (tags and word classes):** tags no longer belong to word classes: one free hierarchy, any tag on any token, one tag per group, names unique in the whole structure; Word Class an ordinary (hierarchical) closed field that can't be deleted; "usual for" hints on groups (several word classes, inherited by subgroups, none = every lemma), following renamed classes; the token dialogue shows usual groups plus a Show all tags button, defaults only from usual groups, a soft warning (dashed amber chips, notes) everywhere with Don't show this again and Settings → General → Warnings; no matrix class; Lemma/Tag blank until configured; the tag conversion dialogue and saved conversions dropped; format 2 with an automatic upgrade.

**Settled on 17 October (bulk edit):** a separate window; Lemmas and Tokens tabs, with greyed lemma columns on Tokens; FLEx-style ticks and preview; Replace (with a regular expression option, one tab) and Shortcuts with a direction rather than stepped rule lists; Set value, Copy and Clear as options; diacritics kept, soundfiles renamed and comment dates left alone by default, each switchable, with warnings; pitch shifts that would leave the range cancel the whole operation; a placeholder for Stage 2 conditions; word class changes through a tag conversion dialogue (convert, new tag, delete) with saved conversions (dropped on 18 October).

**Settled on 16 October (evening):** lemma and All data column filters (Show all / Blanks / Non-blanks / Filter for… / Choose…), open and closed fields, Fields dialogue with XML preview, Configure columns, tabs All data / Lemma/Tag / Tag/Tag with All data as default, matrix class, Configure cell / Configure matrix / Save matrix, Citation / Exact / Loose columns, side-by-side tokens with chips, greyed contradictory cells, auto-play checkbox, one recording per token with speaker as metadata only, `{speaker}` out of the default file name, new pitch notation with colons, tag chips and icon buttons, deleting a token deletes its recording (setting to keep it).

**Settled earlier on 16 October:** pitch notation, comma as pause, pitch display range setting, drawn contours as default display; no repeated takes, with confirmation before overwriting (converted recordings included); texts, songs and paradigms left out of the reference categories; customisable file-name pattern with spaces kept (changed 19 October: written as Praat writes them, with underscores) and forbidden characters refused; file names stored per token, with automatic or button-based updating; the current-session panel, with the date resetting each run; "database", "lemma", "matrix view" and "variety" (not "dialect") as terms; one variety per database, in the metadata only, shown read-only in the session panel; no Dekereke import or export in the program; one token, one transcription, one soundfile, with speaker as metadata; main window layout as in the first mockup; three matrix modes (All data, Tag/Tag, Entry/Tag), with the switch button swapping rows and columns; single entry mode following the selected lemma; double-clicking an empty cell to create a token; saved views; Exactly/Includes matching; no group on both axes; a customisable tag hierarchy with nested groups, which also sets the tag order in file names; Play cell button plus a "Play cell when clicked" setting; separate search, filters and CV shape filters for the lemma list and the matrix view, sharing one analysis engine; program name Lemmatrix.

**Open questions**
1. **Adding entries:** how references are suggested from the category is built simply for now (next free number); a mockup may refine it.
2. **Tone letters** as an alternative pitch display, and "Insert character": later.
3. **Analyze → Valency (Stage 2):** work out each verb's valency from its tokens (A + O = transitive, S = intransitive, Antipassive/Passive stems), as a lemma property.
