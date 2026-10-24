# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""Download the IPA soundfiles from Wikimedia Commons' General phonetics page.

Each soundfile is fetched at a pinned version (checked by its SHA-1), not at
whatever Commons serves today, since many of these files are edited back and
forth. The credits below are for the person who actually recorded the pinned
version, worked out from each file's upload history on 24 October 2026 (the
description pages are out of date for several files).

This is how lemmatrix/ipa/ was made (Josh ran it on 24 October 2026; IDEAS.md idea 46): the
soundfiles there are these, unchanged. Run it with Python 3 (certifi helps on Windows):

    python fetch_commons_soundfiles.py
    python fetch_commons_soundfiles.py "D:\\some\\other\\folder"

It writes, into "Commons IPA soundfiles" beside this script (or the folder
given):
    the 126 soundfiles, named as on Commons with underscores for spaces;
    CREDITS.md, the attribution table (for THIRD-PARTY.md and the program);
    credits.tsv, the same table for the program to read.

Running it again skips soundfiles that are already there and correct.
"""

import csv
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = ("Lemmatrix-soundfile-fetch/1.0 "
              "(https://github.com/smojos/Lemmatrix; lemmatrix.support@gmail.com)")
PAUSE = 0.5  # seconds between requests, to be polite to Commons

LICENCES = {
    "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "CC0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "Public domain": "",
}

P = "Pulmonic consonants"
N = "Non-pulmonic consonants"
V = "Vowels"
O = "Other symbols"
ISO = "Peter Isotalo"
DEN = "Denelson83"
BY3 = "CC BY-SA 3.0"
BY4 = "CC BY-SA 4.0"

# (section, IPA, Commons file name, recorded by, licence, pinned version's date, SHA-1)
SOUNDFILES = [
    (P, "ʀ", "Uvular trill.ogg", ISO, BY3, "2005-05-02", "ef4a3e09e1b261e0093cb0e4353bb6c861dfeee4"),
    (P, "r", "Alveolar trill.ogg", ISO, BY3, "2005-05-02", "3bce8f650d55733a8b4513847742fe5309f6a59b"),
    (P, "β", "Voiced bilabial fricative.ogg", ISO, BY3, "2006-01-08", "8b94c8ebd36d6301f1eb26a8699cce0c6f082283"),
    (P, "ð", "Voiced dental fricative.ogg", ISO, BY3, "2006-01-08", "7c897f55a3b92c8fb4edcc7946c51c7f5ae787e9"),
    (P, "ʝ", "Voiced palatal fricative.ogg", ISO, BY3, "2005-05-02", "f665881d5d1f2c45e052e57dcd614f04733fc384"),
    (P, "ɸ", "Voiceless bilabial fricative.ogg", ISO, BY3, "2005-05-02", "26e5276c065347f5e4d84df6e3f5fd896636426d"),
    (P, "f", "Voiceless labiodental fricative.ogg", ISO, BY3, "2005-04-15", "ee060dc62b68ac348f87ab6afb511460855226b3"),
    (P, "ç", "Voiceless palatal fricative.ogg", ISO, BY3, "2012-11-30", "a02ccfcd373caf0f5e41595e8d7c2c73cae84e26"),
    (P, "x", "Voiceless velar fricative.ogg", ISO, BY3, "2005-05-01", "b03bd6116613b536f386fb53d51491a72d38db28"),
    (P, "ɹ", "Alveolar approximant.ogg", "Erutuon", BY3, "2015-02-27", "32a0dff953ab25959354dc97a853b4fe359fb905"),
    (P, "ʙ", "Bilabial trill.ogg", ISO, BY3, "2005-05-02", "61e8fa3c191b8a8e4c45c8841d8ee26b6714033b"),
    (P, "ʔ", "Glottal stop.ogg", ISO, BY3, "2005-05-02", "7bbefb6081d43fae430bf932419a72d10b96f172"),
    (P, "j", "Palatal approximant.ogg", ISO, BY3, "2005-05-02", "f9a1154118babeb39f1bd63785b5259a11431b0b"),
    (P, "ɻ", "Retroflex approximant.ogg", ISO, BY3, "2005-05-02", "ff5a3ac7231aa747f8f880ced074b4abf7f5a84d"),
    (P, "d", "Voiced alveolar plosive.ogg", ISO, BY3, "2005-05-02", "1064d586cd6b2cba715833eabf933784e8e7b668"),
    (P, "t", "Voiceless alveolar plosive.ogg", ISO, BY3, "2005-05-02", "1c4c92df805583d5584ac4b92ace40f32cca675b"),
    (P, "ɡ", "Voiced velar plosive.ogg", ISO, BY3, "2005-04-17", "a030ea93a7bfa5ad56226c52390a0b0cf1b34d9d"),
    (P, "v", "Voiced labiodental fricative.ogg", ISO, BY3, "2005-04-17", "317301036b1d806633252ca25045dcb201409c98"),
    (P, "k", "Voiceless velar plosive.ogg", ISO, BY3, "2005-05-02", "7bf30f4f53de17f555289d4d099fcc7b7da71392"),
    (P, "ɦ", "Voiced glottal fricative.ogg", ISO, BY3, "2005-05-02", "26c650a7dd4835d4912cf54efc03299f326e224b"),
    (P, "ʁ", "Voiced uvular fricative.ogg", ISO, BY3, "2005-05-02", "31d014e861e78c2c7b95352c15ef6b877d49dfda"),
    (P, "ɣ", "Voiced velar fricative.ogg", ISO, BY3, "2005-05-01", "9627b26b9b1df9705c33124f803b337d8864ec3f"),
    (P, "θ", "Voiceless dental fricative.ogg", ISO, BY3, "2006-01-08", "e051a6c6a050e6a1b9741f1e53ea92a421d0374a"),
    (P, "χ", "Voiceless uvular fricative.ogg", ISO, BY3, "2005-05-02", "0f215661b3f08c4836a872ab93386c292f2f10d8"),
    (P, "q", "Voiceless uvular plosive.ogg", ISO, BY3, "2005-05-02", "ba4efa2b876b27bd27ff24d07a4e17b1d0a66890"),
    (P, "h", "Voiceless glottal fricative.ogg", ISO, BY3, "2005-05-02", "82a56b02f8411629dcee4a61b5b2fb88cf41dc75"),
    (P, "m", "Bilabial nasal.ogg", ISO, BY3, "2005-05-02", "9aa284e454f590dd1cce25dbd4da61faef2f1af7"),
    (P, "ʋ", "Labiodental approximant.ogg", ISO, BY3, "2005-05-02", "e9b7f26732d223d619d3d2576cb9ca6ee51f16b9"),
    (P, "ɱ", "Labiodental nasal.ogg", ISO, BY3, "2005-05-02", "6cd702f3b58ca12d68dd1eb2351221caf845a6ec"),
    (P, "ɲ", "Palatal nasal.ogg", ISO, BY3, "2005-05-02", "53434daa0dbf23cb2fa830c058bfa7270be41e52"),
    (P, "ɳ", "Retroflex nasal.ogg", ISO, BY3, "2005-05-02", "d5ac1bf4c0d168904f524902ee8641dffc6b0ae6"),
    (P, "ɴ", "Uvular nasal.ogg", ISO, BY3, "2005-05-02", "d64f2d10263f05a8a9804ec3ccc5896e4f35cdef"),
    (P, "ŋ", "Velar nasal.ogg", ISO, BY3, "2005-05-02", "2a61afbbfddff3ee4c9caf9827bd0829dd7b44de"),
    (P, "b", "Voiced bilabial plosive.ogg", ISO, BY3, "2005-05-02", "67978441b5165b5ea3663d0090822509c8399489"),
    (P, "ɟ", "Voiced palatal plosive.ogg", ISO, BY3, "2005-05-02", "d9b1f8901da98f6c210733cef9de3febc12df3db"),
    (P, "p", "Voiceless bilabial plosive.ogg", ISO, BY3, "2005-05-09", "d130da4673b9eca7f038cdb43ea9db83145a08e9"),
    (P, "c", "Voiceless palatal plosive.ogg", ISO, BY3, "2005-05-02", "e392811ad55db4dc20960432822f5619c4204a99"),
    (P, "ɰ", "Voiced velar approximant.ogg", ISO, BY3, "2005-05-09", "aded63a4e18cd9de3c302a456ab7fca999cb12ed"),
    (P, "n", "Alveolar nasal.ogg", ISO, BY3, "2006-01-08", "086d166308ec025f1c92de3021f54bc2d80562fc"),
    (P, "s", "Voiceless alveolar sibilant.ogg", ISO, BY3, "2024-03-30", "92d215b4003a0184eded8b5ce8b96083a546386d"),
    (P, "z", "Voiced alveolar sibilant.ogg", ISO, BY3, "2005-05-02", "aa501c317e153a943b6bba1c41e3e7fd92edc956"),
    (P, "ʒ", "Voiced palato-alveolar sibilant.ogg", ISO, BY3, "2024-03-30", "090fe11e36c6d1380d8a7fb5d88c2df4c4af708c"),
    (P, "ʐ", "Voiced retroflex sibilant.ogg", ISO, BY3, "2024-03-30", "700a92685e0987f31485411e5781da0e23172e77"),
    (P, "ʃ", "Voiceless palato-alveolar sibilant.ogg", ISO, BY3, "2024-03-30", "5c23db9bb769b91ba24fb952bbbb01bc338ac206"),
    (P, "ʂ", "Voiceless retroflex sibilant.ogg", ISO, BY3, "2024-03-30", "8b775fdd4978f26e7432967796470ab5d18867ed"),
    (P, "ɖ", "Voiced retroflex stop.oga", ISO, BY3, "2005-05-02", "5022e0247faaef007f059435379cc53cdb47c854"),
    (P, "ɢ", "Voiced uvular stop.oga", ISO, BY3, "2005-05-02", "e553b15c3bbeb7f94dc25dd878f3335123126704"),
    (P, "ʈ", "Voiceless retroflex stop.oga", ISO, BY3, "2005-05-09", "a8435c4df6ca0cde15dd724e2df78402f6f2dc38"),
    (P, "ħ", "Voiceless pharyngeal fricative.ogg", ISO, BY3, "2005-05-09", "beecd2cce4cfe6bb06fa2e7250c3d37282c8800e"),
    (P, "ʕ", "Voiced pharyngeal fricative.ogg", ISO, BY3, "2005-05-09", "745ae737c9a8adb95d9f7386e181f6cd12e44328"),
    (N, "sʼ", "Alveolar ejective fricative.ogg", ISO, BY3, "2005-05-09", "bebbff4937cb83d47e7e8e035e8d8dc9534eda53"),
    (P, "ɭ", "Retroflex lateral approximant.ogg", ISO, BY3, "2005-05-02", "6f3fb60a4161d7b0c7e25edb6d85aa18174e6725"),
    (P, "l", "Alveolar lateral approximant.ogg", ISO, BY3, "2005-05-02", "c72c45678fbca0aca52b98fed9b1977b648de3b9"),
    (P, "ɮ", "Voiced alveolar lateral fricative.ogg", "TFighterPilot", BY3, "2011-10-06", "5eae05c4aec3753fe9fa78ccdffdcf6aa9e2765b"),
    (P, "ʎ", "Palatal lateral approximant.ogg", ISO, BY3, "2021-09-14", "ba5194757af3b2ebf8878a8acbf9e94e73a04d36"),
    (P, "ɽ", "Retroflex flap.ogg", ISO, BY3, "2005-05-02", "614f67d88605c9de1a15627eed039ee6cb653c5f"),
    (P, "ɾ", "Alveolar tap.ogg", ISO, BY3, "2005-05-02", "b53f766d393be631c431af64aef226a2fce6209e"),
    (N, "pʼ", "Bilabial ejective plosive.ogg", ISO, BY3, "2005-05-02", "a1625e208a38653f420becf8869f24efdcade5f2"),
    (N, "ǀ", "Dental click.ogg", ISO, BY3, "2005-05-02", "ece79dd87966fa4900e44c8e0aad553e341bf870"),
    (N, "qʼ", "Uvular ejective plosive.ogg", ISO, BY3, "2005-05-02", "c105cf658063ebd2966321496da57cc3b7f22514"),
    (N, "kʼ", "Velar ejective plosive.ogg", ISO, BY3, "2005-05-09", "b7df79e14daae1070c049b5602dc1b4046ed858d"),
    (N, "ǃ", "Postalveolar click.ogg", ISO, BY3, "2005-05-09", "85603065465595f8f3d98abfe80d1d02e8620b5b"),
    (N, "tʼ", "Alveolar ejective plosive.ogg", ISO, BY3, "2005-05-09", "9538cb87ea8778f821271a50817e86262d291630"),
    (N, "ǁ", "Alveolar lateral click.ogg", ISO, BY3, "2005-05-09", "d33059f37959f0cc1b6a285838b56cdf8ff0526f"),
    (N, "ǂ", "Palatoalveolar click.ogg", ISO, BY3, "2005-05-09", "0da4aab0de56e18c90bb10dab87538693e6d7b1d"),
    (N, "ɓ", "Voiced bilabial implosive.ogg", ISO, BY3, "2005-06-06", "c40f1e92f9afc03f5e0564699789ae546387fe9d"),
    (N, "ɗ", "Voiced alveolar implosive.ogg", ISO, BY3, "2005-06-06", "5174bd72514197d4763139776c555ce0b614c322"),
    (N, "ʄ", "Voiced palatal implosive.ogg", ISO, BY3, "2005-06-06", "10620d97d6d83183fbda8333a3186ebca25ebf1f"),
    (N, "ɠ", "Voiced velar implosive.ogg", ISO, BY3, "2005-06-06", "1e4eacc88462a2437b13ba966e68539f4d329be8"),
    (N, "ʛ", "Voiced uvular implosive.ogg", ISO, BY3, "2005-06-06", "f34b2f87eaaf8e916102a2269424bfb0ed16850f"),
    (V, "y", "Close front rounded vowel.ogg", DEN, BY3, "2005-07-20", "1be48b361894a9e7a5524c8d25102dc26468ff3e"),
    (V, "ɪ", "Near-close near-front unrounded vowel.ogg", DEN, BY3, "2005-07-20", "90b0522dcb269043398b5c841cad38cc83083621"),
    (V, "ʏ", "Near-close near-front rounded vowel.ogg", DEN, BY3, "2005-08-22", "1083060fc3433784c18c3b9a8a8553ca6dd40d7a"),
    (V, "e", "Close-mid front unrounded vowel.ogg", DEN, BY3, "2005-07-20", "a7d6ea1cac2b7886ea2b4f103cb5ba1833df940c"),
    (V, "ø", "Close-mid front rounded vowel.ogg", DEN, BY3, "2005-07-20", "6fc5342f0de9e3458d1ee777396c47e5f7d92cba"),
    (V, "ɛ", "Open-mid front unrounded vowel.ogg", "Terfili", BY3, "2011-05-14", "53f71cb41cf50e44ad49db15c5eca23b7ffac6e2"),
    (V, "u", "Close back rounded vowel.ogg", DEN, BY3, "2005-07-20", "ec885fb9088c69e0ceed6c41cec7deb86dce4275"),
    (V, "ʊ", "Near-close near-back rounded vowel.ogg", DEN, BY3, "2005-08-10", "a13e1766302a657f906d31104975c87e0b5a3587"),
    (V, "i", "Close front unrounded vowel.ogg", DEN, BY3, "2005-07-20", "b474c0a364f4d3f7830df7cab1887ef3b9205d6e"),
    (V, "œ", "Open-mid front rounded vowel.ogg", "JøMa", BY3, "2011-03-27", "2ec2bb7ad1e0d1f7ef41cc383ae0c346f1e84de3"),
    (V, "ɨ", "Close central unrounded vowel.ogg", DEN, BY3, "2005-07-20", "5e23853e720b111185a855b5a72275e97144986d"),
    (V, "ʉ", "Close central rounded vowel.ogg", DEN, BY3, "2005-07-20", "5f7d757b2f35cbd1fef91c75faf69e7a722c2650"),
    (V, "ɯ", "Close back unrounded vowel.ogg", DEN, BY3, "2005-08-10", "fd21d4e105075953cd5e897f38152753cfd47d70"),
    (V, "ɤ", "Close-mid back unrounded vowel.ogg", DEN, BY3, "2005-07-26", "aba8561b2e66e357f8a7e6c323b73eed2014ce2d"),
    (V, "o", "Close-mid back rounded vowel.ogg", DEN, BY3, "2005-08-10", "6e648d7e4aaa94eb9332d5b92e2e9f802213c494"),
    (V, "ɘ", "Close-mid central unrounded vowel.ogg", DEN, BY3, "2005-07-26", "a549ba0654ef652d89628be190d073eaa42a7acc"),
    (V, "ɵ", "Close-mid central rounded vowel.ogg", DEN, BY3, "2005-07-26", "c1e29f357588c5b8619c01e7ff53490837ba373d"),
    (P, "ʟ", "Velar lateral approximant.ogg", ISO, BY3, "2006-01-08", "ce820cfce278444c6a9f16ae59c3c51899059b5b"),
    (N, "ʘ", "Bilabial click.ogg", ISO, BY3, "2006-01-08", "fb6dccbb5bcae8a24f5747a1f3ccd9e3311fd59b"),
    (N, "ʈʼ", "Retroflex ejective plosive.ogg", "Pmx", BY3, "2006-06-04", "66a70bd527b1b42c06a0d8697ecf034c30cafb65"),
    (N, "fʼ", "Labiodental ejective fricative.ogg", "Adamsa123", BY3, "2015-08-23", "0b39031fdf1ff67f7909298d22ae9e5b6d1243f2"),
    (V, "ə", "Mid-central vowel.ogg", "Denelson83, edited by Trlkly", BY3, "2021-09-22", "b46666835bad941e68d73fbf59a6134f9bf1a244"),
    (P, "ɬ", "Voiceless alveolar lateral fricative.ogg", "TFighterPilot", BY3, "2011-10-05", "83553af9fb3a06b60e985c9144e691497cf9c69b"),
    (N, "xʼ", "Velar ejective fricative.ogg", "Adamsa123", BY3, "2015-12-30", "a4d325c97e9f1fd5343d0341a4766b317cca6d75"),
    (N, "χʼ", "Uvular ejective fricative.ogg", "Adamsa123", BY3, "2016-01-02", "6db05c2f3a6d5d533ddd0994389981a134bb81a2"),
    (N, "θʼ", "Dental ejective fricative.ogg", "Adamsa123", BY3, "2017-09-06", "9c6f65a61337029793f60906960ed4c51e88fb9d"),
    (N, "ʂʼ", "Retroflex ejective fricative.ogg", "Adamsa123", BY3, "2016-06-12", "d22e44c971d0886722aaaaa30f5dab739f4475ea"),
    (N, "çʼ", "Palatal ejective fricative.ogg", "Adamsa123", BY4, "2015-10-09", "f20efab6c9e1bd5f1d35daf3f75ad94a6e42bd1e"),
    (N, "ʄ̊", "Voiceless palatal implosive.ogg", "PharyngealImplosive7", BY4, "2024-02-24", "034f70e714c1e1cb8ac20aeea1ced127c24b8063"),
    (N, "ɸʼ", "Bilabial ejective fricative.ogg", "UzbekistanQoppa", "CC0", "2025-05-09", "80b2d0bfc570507beac62d0c9d06edf6686319c2"),
    (O, "ɧ", "Voiceless dorso-palatal velar fricative.ogg", ISO, BY3, "2024-03-30", "86404227b62593aa4b58bcf154172629fffbb5d7"),
    (O, "ɫ", "Velarized alveolar lateral approximant.ogg", ISO, BY3, "2006-01-08", "9c2a533f6c2a77856efcd5ebf4648e3183dd3a63"),
    (O, "w", "Voiced labio-velar approximant.ogg", ISO, BY3, "2005-05-02", "fc084012c3a164140f17149502fde6badc2a026c"),
    (O, "ʍ", "Voiceless labio-velar fricative.ogg", ISO, BY3, "2005-05-02", "e70bde490086e553921c9afa19e05932fd7a5356"),
    (V, "æ", "Near-open front unrounded vowel.ogg", DEN, BY3, "2005-07-16", "2c06253db9212940ea231f4f7fd135e3c551f02f"),
    (V, "a", "Open front unrounded vowel.ogg", DEN, BY3, "2005-07-20", "ee33026172662d8e770c2965cc0958938cbec25e"),
    (V, "ɶ", "Open front rounded vowel.ogg", DEN, BY3, "2005-08-10", "626eb2ffb8250241a5da43fae0aa532883bc8fce"),
    (V, "ʌ", "Open-mid back unrounded vowel.ogg", DEN, BY3, "2005-07-16", "68c363004297b56414c91cc6421345c98d981ffb"),
    (V, "ɐ", "Near-open central unrounded vowel.ogg", DEN, BY3, "2005-07-20", "22ba4684bc7974a6d8249ca64c20747c5d4b642e"),
    (V, "ɑ", "Open back unrounded vowel.ogg", DEN, BY3, "2005-07-20", "2092f4fb872817eaa00a6df73cb0828038dd5462"),
    (V, "ɔ", "Open-mid back rounded vowel.ogg", "Denelson83, edited by Fête and Marlin Setia1", BY3, "2019-03-07", "65ccf8f231e7d05a8a06b7522b7b24e040d1d0dc"),
    (V, "ɒ", "Open back rounded vowel.ogg", DEN, BY3, "2005-07-16", "d63fba79b14b773c8b156a309dfff2241f0b6109"),
    (V, "ɜ", "Open-mid central unrounded vowel.ogg", DEN, BY3, "2005-07-20", "05536b10548e13bca862e9789380ed9cc439a16b"),
    (V, "ɞ", "Open-mid central rounded vowel.ogg", "Fête", BY3, "2012-09-21", "f3dc150417b217d92989d310948d9b551bc489d4"),
    (O, "ʈ͡ʂ", "Voiceless retroflex affricate.ogg", "Halibutt", BY3, "2009-05-31", "c48c97321b16f296f407f771fdaf94f74230e1ae"),
    (O, "t͡ɕ", "Voiceless alveolo-palatal affricate.ogg", "Halibutt", BY3, "2009-05-31", "63a07df892f0520319bee431676b699dc530afc9"),
    (O, "d͡ʑ", "Voiced alveolo-palatal affricate.ogg", "Halibutt", BY3, "2009-05-31", "8e97474c1ba7dfbcbed3d649e11569225c1d0afa"),
    (O, "ɖ͡ʐ", "Voiced retroflex affricate.ogg", "Halibutt", BY3, "2009-05-31", "c4adef3719a9276c8ad5ec26c1c6fe7cdb128a04"),
    (O, "t͡ʃ", "Voiceless palato-alveolar affricate.ogg", ISO, BY3, "2010-02-26", "d6d7ff4b51d6de90994dd1fe0e50c6af7c7e7c54"),
    (O, "ʑ", "Voiced alveolo-palatal sibilant.ogg", ISO, BY3, "2005-05-02", "ab81bd8286426d585689bff63ce674ce4ff7f1fb"),
    (O, "d͡ʒ", "Voiced palato-alveolar affricate.ogg", "Octane (English Wikipedia)", "Public domain", "2008-06-24", "d2e571840ad18da9f297915a2de9dc26c4d4da56"),
    (O, "ɕ", "Voiceless alveolo-palatal sibilant.ogg", ISO, BY3, "2005-05-02", "db0e8775424140acdaf201ff5553c0288b44c5d0"),
    (O, "d͡z", "Voiced alveolar sibilant affricate.oga", ISO, BY3, "2006-01-08", "0fd1e73033eb7fa0a271dec28e4c1406ca331bf4"),
    (O, "t͡s", "Voiceless alveolar sibilant affricate.oga", ISO, BY3, "2005-04-17", "a68c6f601d29c736f010acb187643e23758b2eb2"),
    (O, "ʜ", "Voiceless epiglottal trill.ogg", "Adamsa123", BY4, "2015-09-15", "c7ce08928da85f574c60b97de73700cad0c1ea58"),
    (O, "ʢ", "Voiced epiglottal trill 2.ogg", "Adamsa123", BY4, "2015-09-27", "826b9a084429c9c9c6fee973ba6b8e9d3500fbf8"),
]


def ssl_context():
    """Certificates to check Commons against.

    Python on Windows sometimes can't use Windows' own certificate store
    (CERTIFICATE_VERIFY_FAILED), so use the certifi package's list when it
    is installed: python -m pip install certifi
    """
    import ssl
    try:
        import truststore  # Windows' own store, if this package is installed
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        pass
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


CONTEXT = ssl_context()


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60, context=CONTEXT) as response:
        return response.read()


def versions(title):
    """Every uploaded version of a file: sha1, url, timestamp, user."""
    query = urllib.parse.urlencode({
        "action": "query", "format": "json", "redirects": "1",
        "prop": "imageinfo", "iiprop": "sha1|url|timestamp|user",
        "iilimit": "50", "titles": "File:" + title,
    })
    data = json.loads(get(API + "?" + query))
    page = next(iter(data["query"]["pages"].values()))
    return page.get("imageinfo", [])


def page_url(title):
    return "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(title.replace(" ", "_"))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "Commons IPA soundfiles")
    os.makedirs(folder, exist_ok=True)

    done, skipped, problems = 0, 0, []
    for number, (section, ipa, title, credit, licence, date, sha1) in enumerate(SOUNDFILES, 1):
        name = title.replace(" ", "_")
        path = os.path.join(folder, name)
        label = f"[{number:3}/{len(SOUNDFILES)}] [{ipa}] {title}"

        if os.path.exists(path):
            with open(path, "rb") as f:
                if hashlib.sha1(f.read()).hexdigest() == sha1:
                    print(label, "- already there")
                    skipped += 1
                    continue

        try:
            match = [v for v in versions(title) if v.get("sha1") == sha1]
            time.sleep(PAUSE)
            if not match:
                problems.append(f"{title}: the pinned version ({date}) is no longer on Commons")
                print(label, "- PINNED VERSION NOT FOUND")
                continue
            # Several versions can share the pinned checksum (a revert); Commons
            # sometimes serves stale bytes at one of their addresses, so try each.
            for version in match:
                data = get(version["url"])
                time.sleep(PAUSE)
                if hashlib.sha1(data).hexdigest() == sha1:
                    break
        except Exception as error:  # network trouble: report and carry on
            if "CERTIFICATE_VERIFY_FAILED" in str(error):
                print()
                print("Python can't check Commons' security certificate on this computer.")
                print("Install the certificate list, then run this script again:")
                print("    python -m pip install certifi")
                sys.exit(1)
            problems.append(f"{title}: {error}")
            print(label, "- FAILED:", error)
            continue

        if hashlib.sha1(data).hexdigest() != sha1:
            problems.append(f"{title}: the downloaded soundfile doesn't match its pinned checksum")
            print(label, "- CHECKSUM MISMATCH, not saved")
            continue
        with open(path, "wb") as f:
            f.write(data)
        print(label, "- saved")
        done += 1

    write_credits(folder)

    print()
    print(f"Saved {done}, already there {skipped}, problems {len(problems)}.")
    for problem in problems:
        print("  -", problem)
    print("Folder:", folder)


def write_credits(folder):
    with open(os.path.join(folder, "credits.tsv"), "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["section", "ipa", "soundfile", "commons_title", "recorded_by",
                         "licence", "licence_url", "source", "version_date", "sha1"])
        for section, ipa, title, credit, licence, date, sha1 in SOUNDFILES:
            writer.writerow([section, ipa, title.replace(" ", "_"), title, credit,
                             licence, LICENCES[licence], page_url(title), date, sha1])

    lines = [
        "# IPA soundfiles from Wikimedia Commons",
        "",
        "These soundfiles come from Wikimedia Commons "
        "(https://commons.wikimedia.org/wiki/General_phonetics). They are not covered by "
        "Lemmatrix's own licence: each keeps the licence shown here. Each is the version "
        "uploaded on the date given (checked by its SHA-1 in credits.tsv); the person "
        "credited recorded that version. Unchanged from Commons.",
        "",
        "| IPA | Sound | Recorded by | Licence | Source |",
        "|---|---|---|---|---|",
    ]
    for section in (P, N, O, V):
        for s, ipa, title, credit, licence, date, sha1 in SOUNDFILES:
            if s != section:
                continue
            sound = title.rsplit(".", 1)[0]
            licence_text = f"[{licence}]({LICENCES[licence]})" if LICENCES[licence] else licence
            lines.append(f"| [{ipa}] | {sound} | {credit} | {licence_text} | "
                         f"[Commons]({page_url(title)}), {date} |")
    with open(os.path.join(folder, "CREDITS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
