# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright © 2026 Joshua A. G. Smolders. Additional terms: NOTICE.md
"""The ɛλicit web page's prompts, in English and the built-in second languages (IDEAS.md ideas 19, 92).

A request carries its prompts in English and in its second language (if one is built in), so the
web page itself knows no language. Placeholders: {name} the speaker, {researcher}, {language} the
language asked for, {n} and {total} (the progress line), {link} (the page's address, in the message),
{date}.

**The languages** (Josh, 28 October; idea 92): English, French, Arabic (Modern Standard) and Amharic.
The others (Danish, Italian, Spanish, Portuguese, German, Dutch, Swahili) were for testing and are
gone; a request already sent carries its own prompts, and a gloss language without prompts gets
English. Swahili and Portuguese come back in v1.x, reviewed the same way.

**Forms of address** (idea 92): each request addresses the speaker **respectfully** (gender-neutral,
the default), **as a man** or **as a woman** (``SPEAKER_FORMS``); some keys also take the researcher's
gender (``RESEARCHER_FORMS``), where a language marks {researcher} in the third person. A translation
is a string where every form reads the same, else a dict keyed by the speaker's form (``m``, ``f``,
``r``) or by speaker and researcher (``r.f``, ``m.m``…); ``prompts(lang, speaker, researcher)`` picks.

**The translations are written by ``tools/write_prompts.py``** from the review (the EACW engine:
round 1 from the English and each prompt's context, a blind back-translation, round 2, Josh's
workbook; the runs in Lemmatrix-evidence ``eacw-glosses/runs/PROMPTS-…``), never edited by hand.
``STATUS`` says how far each language is checked.
"""

from __future__ import annotations

KEYS = ('yes', 'no', 'ok', 'are_you', 'give_device', 'not_around', 'not_around_end', 'agreement', 'contact', 'speak', 'goodbye', 'wrong_language_end', 'opener', 'ready', 'mic_allow', 'new_card', 'say_repeat', 'rerecord', 'listen', 'record', 'stop', 'recording', 'its_good', 'try_again', 'cant_say', 'progress', 'finished', 'send_title', 'send', 'save', 'sent', 'closing', 'expired', 'mic_error', 'resume', 'message', 'message_link', 'sending', 'waiting_net', 'sent_done', 'keep_open', 'try_now', 'expired_keep', 'glitch', 'level_clipped', 'level_quiet', 'keep_anyway', 'cant_play', 'request_line')

SPEAKER_FORMS = {"r": "Respectful", "m": "To a man", "f": "To a woman"}
RESEARCHER_FORMS = {"m": "a man", "f": "a woman"}
DEFAULT_SPEAKER_FORM, DEFAULT_RESEARCHER_FORM = "r", "m"

ENGLISH: dict[str, str] = {
        "yes": "Yes", "no": "No", "ok": "OK",
    "are_you": "Are you {name}?",
    "give_device": "Please give your phone or device to {name}.",
    "not_around": "{name} is not around",
    "not_around_end": "Thank you. Please let {researcher} know that {name} was not around.",
    "agreement": "Have you signed a participation agreement with {researcher}?",
    "contact": "Please contact {researcher} about signing an agreement.",
    "speak": "Do you speak {language}?",
    "goodbye": "Goodbye",
    "wrong_language_end": "Thank you. Please let {researcher} know.",
    "opener": "Please find a quiet place. If you have a high-quality microphone, please make sure it is "
              "attached to your computer or phone. Let me know when you are ready.",
    "ready": "I'm ready",
    "mic_allow": "When your phone or browser asks, please allow the microphone.",
    "new_card": "How do you say this in {language}?",
    "say_repeat": "Please say it 2 or 3 times.",
    "rerecord": "Please repeat this exactly.",
    "listen": "Listen", "record": "Record", "stop": "Stop", "recording": "Recording…",
    "its_good": "It's good", "try_again": "Try again", "cant_say": "I can't say this one",
    "progress": "{n} of {total}",
    "finished": "Are you finished? Thank you very much!",
    "send_title": "Please send the recordings to {researcher}.",
    "send": "Send", "save": "Save the file", "sent": "I've sent it",
    "closing": "Thank you! You can close this page now.",
    "expired": "This request has expired. Please contact {researcher}.",
    "mic_error": "The microphone could not be used. Please allow it and try again.",
    "resume": "Carry on where you stopped",
    "message": "Hello {name}! {researcher} would like you to record some words. Please open {link} on your "
               "phone or computer, choose “Open the request file”, and pick the file sent with this message.",
    "message_link": 'Hello {name}! {researcher} would like you to record some words. Please open this link on your phone or computer:',
    "sending": 'Sending the recordings… {n} of {total}',
    "waiting_net": 'Waiting for the internet. Your recordings are safe on this device: keep this page open, or open the link again later.',
    "keep_open": "Please keep this page open until all your recordings are sent.",
    "try_now": "Try again now",
    "expired_keep": "This request has expired, but your recordings are safe on this device. Please send them to {researcher} as a file.",
    "glitch": "Some of the sound was lost while recording (the phone was busy). Please try again.",
    "level_clipped": "That was too loud. Please hold the phone a little further away and try again.",
    "level_quiet": "That was very quiet. Please hold the phone a little closer and try again.",
    "keep_anyway": "Keep it anyway",
    "cant_play": "It can't be played back here, but it has been recorded.",
    "request_line": "{researcher}'s request of {date}: {total} items",
    "sent_done": 'Your recordings have reached {researcher}. Thank you very much!',
}

# ---- translations: written by tools/write_prompts.py ----
TRANSLATIONS: dict[str, dict[str, str | dict[str, str]]] = {
    'fr': {
        'yes': "Oui",
        'no': "Non",
        'ok': "D'accord",
        'are_you': "Êtes-vous {name} ?",
        'give_device': "Veuillez donner votre téléphone ou votre appareil à {name}.",
        'not_around': "{name} n'est pas là",
        'not_around_end': "Merci. Veuillez dire à {researcher} que {name} n'était pas là.",
        'agreement': "Avez-vous signé un accord de participation avec {researcher} ?",
        'contact': "Veuillez contacter {researcher} pour signer un accord.",
        'speak': "Parlez-vous {language} ?",
        'goodbye': "Au revoir",
        'wrong_language_end': "Merci. Veuillez le dire à {researcher}.",
        'opener': {"m": "Veuillez trouver un endroit calme. Si vous avez un bon microphone, branchez-le à votre ordinateur ou à votre téléphone. Dites-moi quand vous êtes prêt.", "f": "Veuillez trouver un endroit calme. Si vous avez un bon microphone, branchez-le à votre ordinateur ou à votre téléphone. Dites-moi quand vous êtes prête.", "r": "Veuillez trouver un endroit calme. Si vous avez un bon microphone, branchez-le à votre ordinateur ou à votre téléphone. Dites-moi quand vous pouvez commencer."},
        'ready': {"m": "Je suis prêt", "f": "Je suis prête", "r": "C'est bon, je commence"},
        'mic_allow': "Quand votre téléphone ou votre navigateur vous le demande, veuillez autoriser le microphone.",
        'new_card': "Comment dit-on ceci en {language} ?",
        'say_repeat': "Veuillez le dire 2 ou 3 fois.",
        'rerecord': "Veuillez répéter exactement ceci.",
        'listen': "Écouter",
        'record': "Enregistrer",
        'stop': "Arrêter",
        'recording': "Enregistrement…",
        'its_good': "C'est bon",
        'try_again': "Réessayer",
        'cant_say': "Je ne peux pas dire ceci",
        'progress': "{n} sur {total}",
        'finished': "Avez-vous terminé ? Merci beaucoup !",
        'send_title': "Veuillez envoyer les enregistrements à {researcher}.",
        'send': "Envoyer",
        'save': "Sauvegarder le fichier",
        'sent': "Je l'ai envoyé",
        'closing': "Merci ! Vous pouvez maintenant fermer cette page.",
        'expired': "Cette demande a expiré. Veuillez contacter {researcher}.",
        'mic_error': "Le microphone n'a pas pu être utilisé. Veuillez l'autoriser et réessayer.",
        'resume': "Reprendre là où j'en étais",
        'message': "Bonjour {name} ! {researcher} aimerait que vous enregistriez quelques mots. Veuillez ouvrir {link} sur votre téléphone ou votre ordinateur, choisir « Ouvrir le fichier de demande » et sélectionner le fichier envoyé avec ce message.",
        'message_link': "Bonjour {name} ! {researcher} aimerait que vous enregistriez quelques mots. Veuillez ouvrir ce lien sur votre téléphone ou votre ordinateur :",
        'sending': "Envoi des enregistrements… {n} sur {total}",
        'waiting_net': "En attente d'Internet. Vos enregistrements sont en sécurité sur cet appareil : gardez cette page ouverte, ou rouvrez le lien plus tard.",
        'sent_done': "Vos enregistrements sont bien parvenus à {researcher}. Merci beaucoup !",
        'keep_open': "Veuillez garder cette page ouverte jusqu'à ce que tous vos enregistrements soient envoyés.",
        'try_now': "Réessayer maintenant",
        'expired_keep': "Cette demande a expiré, mais vos enregistrements sont en sécurité sur cet appareil. Veuillez les envoyer à {researcher} sous forme de fichier.",
        'glitch': "Une partie du son a été perdue pendant l'enregistrement (le téléphone était occupé). Veuillez réessayer.",
        'level_clipped': "C'était trop fort. Veuillez tenir le téléphone un peu plus loin et réessayer.",
        'level_quiet': "C'était très faible. Veuillez tenir le téléphone un peu plus près et réessayer.",
        'keep_anyway': "Le garder quand même",
        'cant_play': "Impossible de l'écouter ici, mais l'enregistrement a bien été fait.",
        'request_line': "Demande de {researcher} du {date} : {total} éléments",
    },
    'ar': {
        'yes': "نعم",
        'no': "لا",
        'ok': "حسنًا",
        'are_you': "هل أنت {name}؟",
        'give_device': "يُرجى تسليم هاتفك أو جهازك إلى {name}.",
        'not_around': {"m": "{name} غير موجود", "f": "{name} غير موجودة", "r": "لا يوجد {name} هنا الآن"},
        'not_around_end': {"m": "شكرًا. يُرجى إبلاغ {researcher} بأن {name} لم يكن موجودًا.", "f": "شكرًا. يُرجى إبلاغ {researcher} بأن {name} لم تكن موجودة.", "r": "شكرًا. يُرجى إبلاغ {researcher} بغياب {name}."},
        'agreement': "هل وقّعت اتفاقية مشاركة مع {researcher}؟",
        'contact': {"m": "من فضلك تواصل مع {researcher} بخصوص توقيع اتفاقية.", "f": "من فضلكِ تواصلي مع {researcher} بخصوص توقيع اتفاقية.", "r": "يُرجى التواصل مع {researcher} بخصوص توقيع اتفاقية."},
        'speak': {"m": "هل تتكلم {language}؟", "f": "هل تتكلمين {language}؟", "r": "هل يمكنك التحدث بلغة {language}؟"},
        'goodbye': "مع السلامة",
        'wrong_language_end': {"m": "شكرًا. من فضلك أخبر {researcher} بذلك.", "f": "شكرًا. من فضلكِ أخبري {researcher} بذلك.", "r": "شكرًا. يُرجى إبلاغ {researcher} بذلك."},
        'opener': {"m": "من فضلك ابحث عن مكان هادئ. إذا كان لديك ميكروفون عالي الجودة، فتأكد من توصيله بحاسوبك أو هاتفك. اضغط الزر في الأسفل عندما تكون جاهزًا.", "f": "من فضلكِ ابحثي عن مكان هادئ. إذا كان لديك ميكروفون عالي الجودة، فتأكدي من توصيله بحاسوبك أو هاتفك. اضغطي الزر في الأسفل عندما تكونين جاهزة.", "r": "يُرجى البحث عن مكان هادئ. إذا كان لديك ميكروفون عالي الجودة، فيُرجى التأكد من توصيله بحاسوبك أو هاتفك. عند الاستعداد، يُرجى الضغط على الزر في الأسفل."},
        'ready': {"m": "أنا جاهز", "f": "أنا جاهزة", "r": "لنبدأ"},
        'mic_allow': {"m": "عندما يطلب هاتفك أو متصفحك ذلك، اسمح باستخدام الميكروفون من فضلك.", "f": "عندما يطلب هاتفك أو متصفحك ذلك، اسمحي باستخدام الميكروفون من فضلكِ.", "r": "عندما يطلب هاتفك أو متصفحك ذلك، يُرجى السماح باستخدام الميكروفون."},
        'new_card': {"m": "كيف تقول هذا بلغة {language}؟", "f": "كيف تقولين هذا بلغة {language}؟", "r": "كيف يُقال هذا بلغة {language}؟"},
        'say_repeat': {"m": "من فضلك قُلها مرتين أو ثلاث مرات.", "f": "من فضلكِ قوليها مرتين أو ثلاث مرات.", "r": "يُرجى نطقها مرتين أو ثلاث مرات."},
        'rerecord': {"m": "من فضلك كرّر هذا تمامًا كما سمعته.", "f": "من فضلكِ كرّري هذا تمامًا كما سمعته.", "r": "يُرجى تكرار هذا تمامًا كما سمعته."},
        'listen': "استماع",
        'record': "تسجيل",
        'stop': "إيقاف",
        'recording': "جارٍ التسجيل…",
        'its_good': "جيد",
        'try_again': "إعادة المحاولة",
        'cant_say': "لا أستطيع قول هذه",
        'progress': "{n} من {total}",
        'finished': "هل انتهيت؟ شكرًا جزيلًا!",
        'send_title': {"m": "من فضلك أرسل التسجيلات إلى {researcher}.", "f": "من فضلكِ أرسلي التسجيلات إلى {researcher}.", "r": "يُرجى إرسال التسجيلات إلى {researcher}."},
        'send': "إرسال",
        'save': "حفظ الملف",
        'sent': "أرسلتُ التسجيلات",
        'closing': "شكرًا! يمكنك إغلاق هذه الصفحة الآن.",
        'expired': {"m": "انتهت صلاحية هذا الطلب. من فضلك تواصل مع {researcher}.", "f": "انتهت صلاحية هذا الطلب. من فضلكِ تواصلي مع {researcher}.", "r": "انتهت صلاحية هذا الطلب. يُرجى التواصل مع {researcher}."},
        'mic_error': {"m": "تعذّر استخدام الميكروفون. من فضلك اسمح به وحاول مرة أخرى.", "f": "تعذّر استخدام الميكروفون. من فضلكِ اسمحي به وحاولي مرة أخرى.", "r": "تعذّر استخدام الميكروفون. يُرجى السماح به والمحاولة مرة أخرى."},
        'resume': "المتابعة من حيث توقفت",
        'message': {"m.m": "مرحبًا {name}! يرجو منك {researcher} تسجيل بعض الكلمات. من فضلك افتح {link} على هاتفك أو حاسوبك، واختر “فتح ملف الطلب”، ثم اختر الملف المرسل مع هذه الرسالة.", "m.f": "مرحبًا {name}! ترجو منك {researcher} تسجيل بعض الكلمات. من فضلك افتح {link} على هاتفك أو حاسوبك، واختر “فتح ملف الطلب”، ثم اختر الملف المرسل مع هذه الرسالة.", "f.m": "مرحبًا {name}! يرجو منك {researcher} تسجيل بعض الكلمات. من فضلكِ افتحي {link} على هاتفك أو حاسوبك، واختاري “فتح ملف الطلب”، ثم اختاري الملف المرسل مع هذه الرسالة.", "f.f": "مرحبًا {name}! ترجو منك {researcher} تسجيل بعض الكلمات. من فضلكِ افتحي {link} على هاتفك أو حاسوبك، واختاري “فتح ملف الطلب”، ثم اختاري الملف المرسل مع هذه الرسالة.", "r.m": "مرحبًا {name}! يرجو منك {researcher} تسجيل بعض الكلمات. يُرجى فتح {link} على هاتفك أو حاسوبك، واختيار “فتح ملف الطلب”، ثم اختيار الملف المرسل مع هذه الرسالة.", "r.f": "مرحبًا {name}! ترجو منك {researcher} تسجيل بعض الكلمات. يُرجى فتح {link} على هاتفك أو حاسوبك، واختيار “فتح ملف الطلب”، ثم اختيار الملف المرسل مع هذه الرسالة."},
        'message_link': {"m.m": "مرحبًا {name}! يرجو منك {researcher} تسجيل بعض الكلمات. من فضلك افتح هذا الرابط على هاتفك أو حاسوبك:", "m.f": "مرحبًا {name}! ترجو منك {researcher} تسجيل بعض الكلمات. من فضلك افتح هذا الرابط على هاتفك أو حاسوبك:", "f.m": "مرحبًا {name}! يرجو منك {researcher} تسجيل بعض الكلمات. من فضلكِ افتحي هذا الرابط على هاتفك أو حاسوبك:", "f.f": "مرحبًا {name}! ترجو منك {researcher} تسجيل بعض الكلمات. من فضلكِ افتحي هذا الرابط على هاتفك أو حاسوبك:", "r.m": "مرحبًا {name}! يرجو منك {researcher} تسجيل بعض الكلمات. يُرجى فتح هذا الرابط على هاتفك أو حاسوبك:", "r.f": "مرحبًا {name}! ترجو منك {researcher} تسجيل بعض الكلمات. يُرجى فتح هذا الرابط على هاتفك أو حاسوبك:"},
        'sending': "جارٍ إرسال التسجيلات… {n} من {total}",
        'waiting_net': {"m": "في انتظار الإنترنت. تسجيلاتك محفوظة بأمان على هذا الجهاز: أبقِ هذه الصفحة مفتوحة، أو افتح الرابط مرة أخرى لاحقًا.", "f": "في انتظار الإنترنت. تسجيلاتك محفوظة بأمان على هذا الجهاز: أبقي هذه الصفحة مفتوحة، أو افتحي الرابط مرة أخرى لاحقًا.", "r": "في انتظار الإنترنت. تسجيلاتك محفوظة بأمان على هذا الجهاز: يُرجى إبقاء هذه الصفحة مفتوحة، أو فتح الرابط مرة أخرى لاحقًا."},
        'sent_done': "وصلت تسجيلاتك إلى {researcher}. شكرًا جزيلًا!",
        'keep_open': {"m": "من فضلك أبقِ هذه الصفحة مفتوحة حتى تُرسَل كل تسجيلاتك.", "f": "من فضلكِ أبقي هذه الصفحة مفتوحة حتى تُرسَل كل تسجيلاتك.", "r": "يُرجى إبقاء هذه الصفحة مفتوحة حتى تُرسَل كل تسجيلاتك."},
        'try_now': "إعادة المحاولة الآن",
        'expired_keep': {"m": "انتهت صلاحية هذا الطلب، لكن تسجيلاتك محفوظة بأمان على هذا الجهاز. من فضلك أرسلها إلى {researcher} كملف.", "f": "انتهت صلاحية هذا الطلب، لكن تسجيلاتك محفوظة بأمان على هذا الجهاز. من فضلكِ أرسليها إلى {researcher} كملف.", "r": "انتهت صلاحية هذا الطلب، لكن تسجيلاتك محفوظة بأمان على هذا الجهاز. يُرجى إرسالها إلى {researcher} كملف."},
        'glitch': {"m": "فُقد جزء من الصوت أثناء التسجيل (كان الهاتف مشغولًا). من فضلك حاول مرة أخرى.", "f": "فُقد جزء من الصوت أثناء التسجيل (كان الهاتف مشغولًا). من فضلكِ حاولي مرة أخرى.", "r": "فُقد جزء من الصوت أثناء التسجيل (كان الهاتف مشغولًا). يُرجى المحاولة مرة أخرى."},
        'level_clipped': {"m": "كان الصوت عاليًا جدًا. من فضلك أبعد الهاتف قليلًا وحاول مرة أخرى.", "f": "كان الصوت عاليًا جدًا. من فضلكِ أبعدي الهاتف قليلًا وحاولي مرة أخرى.", "r": "كان الصوت عاليًا جدًا. يُرجى إبعاد الهاتف قليلًا والمحاولة مرة أخرى."},
        'level_quiet': {"m": "كان الصوت منخفضًا جدًا. من فضلك قرّب الهاتف قليلًا وحاول مرة أخرى.", "f": "كان الصوت منخفضًا جدًا. من فضلكِ قرّبي الهاتف قليلًا وحاولي مرة أخرى.", "r": "كان الصوت منخفضًا جدًا. يُرجى تقريب الهاتف قليلًا والمحاولة مرة أخرى."},
        'keep_anyway': "الاحتفاظ به على أي حال",
        'cant_play': "لا يمكن تشغيله هنا، لكن تم تسجيله.",
        'request_line': "الطلب من {researcher} بتاريخ {date} — عدد العناصر: {total}",
    },
    'am': {
        'yes': "አዎ",
        'no': "አይ",
        'ok': "እሺ",
        'are_you': {"m": "አንተ {name} ነህ?", "f": "አንቺ {name} ነሽ?", "r": "እርስዎ {name} ነዎት?"},
        'give_device': "እባክዎ ስልክዎን ወይም መሣሪያዎን ለ{name} ይስጡ።",
        'not_around': {"m": "{name} እዚህ የለም", "f": "{name} እዚህ የለችም", "r": "{name} እዚህ የሉም"},
        'not_around_end': {"m": "እናመሰግናለን። እባክዎ {name} እዚህ እንዳልነበረ ለ{researcher} ይንገሩ።", "f": "እናመሰግናለን። እባክዎ {name} እዚህ እንዳልነበረች ለ{researcher} ይንገሩ።", "r": "እናመሰግናለን። እባክዎ {name} እዚህ እንዳልነበሩ ለ{researcher} ይንገሩ።"},
        'agreement': {"m": "ከ{researcher} ጋር የተሳትፎ ስምምነት ፈርመሃል?", "f": "ከ{researcher} ጋር የተሳትፎ ስምምነት ፈርመሻል?", "r": "ከ{researcher} ጋር የተሳትፎ ስምምነት ፈርመዋል?"},
        'contact': {"m": "እባክህ ስምምነት ስለመፈረም {researcher}ን አነጋግር።", "f": "እባክሽ ስምምነት ስለመፈረም {researcher}ን አነጋግሪ።", "r": "እባክዎ ስምምነት ስለመፈረም {researcher}ን ያነጋግሩ።"},
        'speak': {"m": "{language} ትናገራለህ?", "f": "{language} ትናገሪያለሽ?", "r": "{language} ይናገራሉ?"},
        'goodbye': "ደህና ሁኑ",
        'wrong_language_end': {"m": "እናመሰግናለን። እባክህ ለ{researcher} አሳውቅ።", "f": "እናመሰግናለን። እባክሽ ለ{researcher} አሳውቂ።", "r": "እናመሰግናለን። እባክዎ ለ{researcher} ያሳውቁ።"},
        'opener': {"m": "እባክህ ጸጥ ያለ ቦታ ፈልግ። ጥሩ ጥራት ያለው ማይክሮፎን ካለህ ከኮምፒውተርህ ወይም ከስልክህ ጋር መሰካቱን አረጋግጥ። ዝግጁ ስትሆን ንገረኝ።", "f": "እባክሽ ጸጥ ያለ ቦታ ፈልጊ። ጥሩ ጥራት ያለው ማይክሮፎን ካለሽ ከኮምፒውተርሽ ወይም ከስልክሽ ጋር መሰካቱን አረጋግጪ። ዝግጁ ስትሆኚ ንገሪኝ።", "r": "እባክዎ ጸጥ ያለ ቦታ ይፈልጉ። ጥሩ ጥራት ያለው ማይክሮፎን ካለዎት ከኮምፒውተርዎ ወይም ከስልክዎ ጋር መሰካቱን ያረጋግጡ። ዝግጁ ሲሆኑ ይንገሩኝ።"},
        'ready': "ዝግጁ ነኝ",
        'mic_allow': {"m": "ስልክህ ወይም ብራውዘርህ ሲጠይቅ እባክህ ማይክሮፎኑን ፍቀድ።", "f": "ስልክሽ ወይም ብራውዘርሽ ሲጠይቅ እባክሽ ማይክሮፎኑን ፍቀጂ።", "r": "ስልክዎ ወይም ብራውዘርዎ ሲጠይቅ እባክዎ ማይክሮፎኑን ይፍቀዱ።"},
        'new_card': {"m": "ይህንን በ{language} እንዴት ትለዋለህ?", "f": "ይህንን በ{language} እንዴት ትይዋለሽ?", "r": "ይህንን በ{language} እንዴት ይሉታል?"},
        'say_repeat': {"m": "እባክህ 2 ወይም 3 ጊዜ በለው።", "f": "እባክሽ 2 ወይም 3 ጊዜ በዪው።", "r": "እባክዎ 2 ወይም 3 ጊዜ ይበሉት።"},
        'rerecord': {"m": "እባክህ ይህንን ልክ እንደሰማኸው ድገመው።", "f": "እባክሽ ይህንን ልክ እንደሰማሽው ድገሚው።", "r": "እባክዎ ይህንን ልክ እንደሰሙት ይድገሙት።"},
        'listen': {"m": "አዳምጥ", "f": "አዳምጪ", "r": "ያዳምጡ"},
        'record': {"m": "ቅዳ", "f": "ቅጂ", "r": "ይቅዱ"},
        'stop': {"m": "አቁም", "f": "አቁሚ", "r": "ያቁሙ"},
        'recording': "እየተቀዳ ነው…",
        'its_good': "ጥሩ ነው",
        'try_again': {"m": "እንደገና ሞክር", "f": "እንደገና ሞክሪ", "r": "እንደገና ይሞክሩ"},
        'cant_say': "ይህንን ማለት አልችልም",
        'progress': "ከ{total} ውስጥ {n}",
        'finished': {"m": "ጨርሰሃል? በጣም እናመሰግናለን!", "f": "ጨርሰሻል? በጣም እናመሰግናለን!", "r": "ጨርሰዋል? በጣም እናመሰግናለን!"},
        'send_title': {"m": "እባክህ ቅጂዎቹን ለ{researcher} ላክ።", "f": "እባክሽ ቅጂዎቹን ለ{researcher} ላኪ።", "r": "እባክዎ ቅጂዎቹን ለ{researcher} ይላኩ።"},
        'send': {"m": "ላክ", "f": "ላኪ", "r": "ይላኩ"},
        'save': {"m": "ፋይሉን አስቀምጥ", "f": "ፋይሉን አስቀምጪ", "r": "ፋይሉን ያስቀምጡ"},
        'sent': "ልኬዋለሁ",
        'closing': {"m": "እናመሰግናለን! አሁን ይህንን ገጽ መዝጋት ትችላለህ።", "f": "እናመሰግናለን! አሁን ይህንን ገጽ መዝጋት ትችያለሽ።", "r": "እናመሰግናለን! አሁን ይህንን ገጽ መዝጋት ይችላሉ።"},
        'expired': {"m": "ይህ ጥያቄ ጊዜው አልፏል። እባክህ {researcher}ን አነጋግር።", "f": "ይህ ጥያቄ ጊዜው አልፏል። እባክሽ {researcher}ን አነጋግሪ።", "r": "ይህ ጥያቄ ጊዜው አልፏል። እባክዎ {researcher}ን ያነጋግሩ።"},
        'mic_error': {"m": "ማይክሮፎኑን መጠቀም አልተቻለም። እባክህ ፍቀድና እንደገና ሞክር።", "f": "ማይክሮፎኑን መጠቀም አልተቻለም። እባክሽ ፍቀጂና እንደገና ሞክሪ።", "r": "ማይክሮፎኑን መጠቀም አልተቻለም። እባክዎ ይፍቀዱና እንደገና ይሞክሩ።"},
        'resume': {"m": "ካቆምክበት ቀጥል", "f": "ካቆምሽበት ቀጥዪ", "r": "ካቆሙበት ይቀጥሉ"},
        'message': {"m.m": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንድትቀዳ ይፈልጋል። እባክህ በስልክህ ወይም በኮምፒውተርህ {link} ላይ ያለውን ገጽ ክፈት፣ “የጥያቄውን ፋይል ይክፈቱ” የሚለውን ምረጥ፣ ከዚያም ከዚህ መልእክት ጋር የተላከውን ፋይል ምረጥ።", "m.f": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንድትቀዳ ትፈልጋለች። እባክህ በስልክህ ወይም በኮምፒውተርህ {link} ላይ ያለውን ገጽ ክፈት፣ “የጥያቄውን ፋይል ይክፈቱ” የሚለውን ምረጥ፣ ከዚያም ከዚህ መልእክት ጋር የተላከውን ፋይል ምረጥ።", "f.m": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንድትቀጂ ይፈልጋል። እባክሽ በስልክሽ ወይም በኮምፒውተርሽ {link} ላይ ያለውን ገጽ ክፈቺ፣ “የጥያቄውን ፋይል ይክፈቱ” የሚለውን ምረጪ፣ ከዚያም ከዚህ መልእክት ጋር የተላከውን ፋይል ምረጪ።", "f.f": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንድትቀጂ ትፈልጋለች። እባክሽ በስልክሽ ወይም በኮምፒውተርሽ {link} ላይ ያለውን ገጽ ክፈቺ፣ “የጥያቄውን ፋይል ይክፈቱ” የሚለውን ምረጪ፣ ከዚያም ከዚህ መልእክት ጋር የተላከውን ፋይል ምረጪ።", "r.m": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንዲቀዱ ይፈልጋሉ። እባክዎ በስልክዎ ወይም በኮምፒውተርዎ {link} ላይ ያለውን ገጽ ይክፈቱ፣ “የጥያቄውን ፋይል ይክፈቱ” የሚለውን ይምረጡ፣ ከዚያም ከዚህ መልእክት ጋር የተላከውን ፋይል ይምረጡ።", "r.f": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንዲቀዱ ይፈልጋሉ። እባክዎ በስልክዎ ወይም በኮምፒውተርዎ {link} ላይ ያለውን ገጽ ይክፈቱ፣ “የጥያቄውን ፋይል ይክፈቱ” የሚለውን ይምረጡ፣ ከዚያም ከዚህ መልእክት ጋር የተላከውን ፋይል ይምረጡ።"},
        'message_link': {"m.m": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንድትቀዳ ይፈልጋል። እባክህ ይህንን ሊንክ በስልክህ ወይም በኮምፒውተርህ ክፈት፦", "m.f": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንድትቀዳ ትፈልጋለች። እባክህ ይህንን ሊንክ በስልክህ ወይም በኮምፒውተርህ ክፈት፦", "f.m": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንድትቀጂ ይፈልጋል። እባክሽ ይህንን ሊንክ በስልክሽ ወይም በኮምፒውተርሽ ክፈቺ፦", "f.f": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንድትቀጂ ትፈልጋለች። እባክሽ ይህንን ሊንክ በስልክሽ ወይም በኮምፒውተርሽ ክፈቺ፦", "r.m": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንዲቀዱ ይፈልጋሉ። እባክዎ ይህንን ሊንክ በስልክዎ ወይም በኮምፒውተርዎ ይክፈቱ፦", "r.f": "ሰላም {name}! {researcher} አንዳንድ ቃላትን እንዲቀዱ ይፈልጋሉ። እባክዎ ይህንን ሊንክ በስልክዎ ወይም በኮምፒውተርዎ ይክፈቱ፦"},
        'sending': "ቅጂዎቹ እየተላኩ ነው… ከ{total} ውስጥ {n}",
        'waiting_net': {"m": "ኢንተርኔት እስኪገኝ እየጠበቅን ነው። ቅጂዎችህ በዚህ መሣሪያ ላይ በሰላም ተቀምጠዋል፤ ይህንን ገጽ ክፍት አድርገህ ተወው፣ ወይም ሊንኩን በኋላ እንደገና ክፈት።", "f": "ኢንተርኔት እስኪገኝ እየጠበቅን ነው። ቅጂዎችሽ በዚህ መሣሪያ ላይ በሰላም ተቀምጠዋል፤ ይህንን ገጽ ክፍት አድርገሽ ተይው፣ ወይም ሊንኩን በኋላ እንደገና ክፈቺ።", "r": "ኢንተርኔት እስኪገኝ እየጠበቅን ነው። ቅጂዎችዎ በዚህ መሣሪያ ላይ በሰላም ተቀምጠዋል፤ ይህንን ገጽ ክፍት አድርገው ይተዉት፣ ወይም ሊንኩን በኋላ እንደገና ይክፈቱ።"},
        'sent_done': {"m": "ቅጂዎችህ {researcher} ዘንድ ደርሰዋል። በጣም እናመሰግናለን!", "f": "ቅጂዎችሽ {researcher} ዘንድ ደርሰዋል። በጣም እናመሰግናለን!", "r": "ቅጂዎችዎ {researcher} ዘንድ ደርሰዋል። በጣም እናመሰግናለን!"},
        'keep_open': {"m": "እባክህ ሁሉም ቅጂዎችህ እስኪላኩ ድረስ ይህንን ገጽ ክፍት አድርገህ ተወው።", "f": "እባክሽ ሁሉም ቅጂዎችሽ እስኪላኩ ድረስ ይህንን ገጽ ክፍት አድርገሽ ተይው።", "r": "እባክዎ ሁሉም ቅጂዎችዎ እስኪላኩ ድረስ ይህንን ገጽ ክፍት አድርገው ይተዉት።"},
        'try_now': {"m": "አሁን እንደገና ሞክር", "f": "አሁን እንደገና ሞክሪ", "r": "አሁን እንደገና ይሞክሩ"},
        'expired_keep': {"m": "ይህ ጥያቄ ጊዜው አልፏል፣ ግን ቅጂዎችህ በዚህ መሣሪያ ላይ በሰላም ተቀምጠዋል። እባክህ እንደ ፋይል አድርገህ ለ{researcher} ላካቸው።", "f": "ይህ ጥያቄ ጊዜው አልፏል፣ ግን ቅጂዎችሽ በዚህ መሣሪያ ላይ በሰላም ተቀምጠዋል። እባክሽ እንደ ፋይል አድርገሽ ለ{researcher} ላኪያቸው።", "r": "ይህ ጥያቄ ጊዜው አልፏል፣ ግን ቅጂዎችዎ በዚህ መሣሪያ ላይ በሰላም ተቀምጠዋል። እባክዎ እንደ ፋይል አድርገው ለ{researcher} ይላኳቸው።"},
        'glitch': {"m": "በሚቀዳበት ጊዜ ከድምፁ የተወሰነው ጠፍቷል (ስልኩ በሌላ ሥራ ተይዞ ነበር)። እባክህ እንደገና ሞክር።", "f": "በሚቀዳበት ጊዜ ከድምፁ የተወሰነው ጠፍቷል (ስልኩ በሌላ ሥራ ተይዞ ነበር)። እባክሽ እንደገና ሞክሪ።", "r": "በሚቀዳበት ጊዜ ከድምፁ የተወሰነው ጠፍቷል (ስልኩ በሌላ ሥራ ተይዞ ነበር)። እባክዎ እንደገና ይሞክሩ።"},
        'level_clipped': {"m": "ድምፁ በጣም ከፍ ያለ ነበር። እባክህ ስልኩን ትንሽ ራቅ አድርገህ ያዝና እንደገና ሞክር።", "f": "ድምፁ በጣም ከፍ ያለ ነበር። እባክሽ ስልኩን ትንሽ ራቅ አድርገሽ ያዢና እንደገና ሞክሪ።", "r": "ድምፁ በጣም ከፍ ያለ ነበር። እባክዎ ስልኩን ትንሽ ራቅ አድርገው ይያዙና እንደገና ይሞክሩ።"},
        'level_quiet': {"m": "ድምፁ በጣም ዝቅ ያለ ነበር። እባክህ ስልኩን ትንሽ ቀረብ አድርገህ ያዝና እንደገና ሞክር።", "f": "ድምፁ በጣም ዝቅ ያለ ነበር። እባክሽ ስልኩን ትንሽ ቀረብ አድርገሽ ያዢና እንደገና ሞክሪ።", "r": "ድምፁ በጣም ዝቅ ያለ ነበር። እባክዎ ስልኩን ትንሽ ቀረብ አድርገው ይያዙና እንደገና ይሞክሩ።"},
        'keep_anyway': {"m": "ቢሆንም አስቀምጠው", "f": "ቢሆንም አስቀምጪው", "r": "ቢሆንም ያስቀምጡት"},
        'cant_play': "እዚህ መልሶ ማዳመጥ አይቻልም፣ ግን ተቀድቷል።",
        'request_line': "የ{researcher} ጥያቄ ({date})፦ {total} ቃላት",
    },
}
STATUS: dict[str, str] = {"fr": "Machine reviewed (round 2), not yet checked", "ar": "Machine reviewed (round 2), not yet checked", "am": "Machine reviewed (round 2), not yet checked"}
# ---- end of translations ----

PROMPTS: dict[str, dict] = {"en": ENGLISH, **TRANSLATIONS}
LANGUAGE_NAMES = {"en": "English", "fr": "French", "ar": "Arabic", "am": "Amharic"}
RIGHT_TO_LEFT = {"ar", "he", "fa", "ur"}


def built_in(lang: str) -> bool:
    return lang in PROMPTS


def _code(lang: str) -> str:
    if not lang:
        return ""
    return lang if lang in PROMPTS else lang.split("-")[0].lower()


def has_forms(lang: str) -> bool:
    """The language's prompts differ by form of address (so the request asks for one)."""
    table = PROMPTS.get(_code(lang)) or {}
    return any(isinstance(v, dict) for v in table.values())


def has_researcher_forms(lang: str) -> bool:
    table = PROMPTS.get(_code(lang)) or {}
    return any(isinstance(v, dict) and any("." in k for k in v) for v in table.values())


def pick(value, speaker: str = DEFAULT_SPEAKER_FORM, researcher: str = DEFAULT_RESEARCHER_FORM) -> str:
    """One prompt's text for a speaker's form and the researcher's gender."""
    if isinstance(value, str):
        return value
    for k in (f"{speaker}.{researcher}", speaker, f"{DEFAULT_SPEAKER_FORM}.{researcher}",
              DEFAULT_SPEAKER_FORM, "all"):
        if k in value:
            return value[k]
    return next(iter(value.values()))


def prompts(lang: str, speaker: str = DEFAULT_SPEAKER_FORM,
            researcher: str = DEFAULT_RESEARCHER_FORM) -> dict[str, str] | None:
    """The prompts in a language (by its gloss-language code, e.g. "am", "ar-SD" → ar) in one form
    of address, or None when the language has none built in."""
    table = PROMPTS.get(_code(lang))
    if table is None:
        return None
    return {k: pick(v, speaker, researcher) for k, v in table.items()}
