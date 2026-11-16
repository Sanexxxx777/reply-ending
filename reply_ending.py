#!/usr/bin/env python3
"""reply-ending: does a coding agent's last message end by asking you something?

Reads the final message of an agent turn (plain text, a Claude Code transcript, or a Claude Code
hook payload) and says whether its ending puts something to the reader: a question, or a request
to decide, approve, answer or do something. Prints the one sentence that is the next step.

    python3 reply_ending.py message.txt
    python3 reply_ending.py --transcript ~/.claude/projects/<project>/<session>.jsonl
    python3 reply_ending.py --hook < stop-hook-payload.json

Exit code: 0 = it asks, 1 = it only reports, 2 = usage or read error (grep-style, so a shell
`if` can branch on it). Standard library only. MIT, Aleksandr Shulgin.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys

TAIL_MAX = 240      # the next step is one line
SHORT = 20          # a closing sentence shorter than this keeps the one before it
MAX_CHARS = 50_000  # of a longer message only the end is read: the ending is what counts

# ---------------------------------------------------------------- line shapes
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
LIST_ITEM = re.compile(r"^\s*(?:[-*+•]|\d{1,3}[.)])\s+")
HEADING = re.compile(r"^\s*#{1,6}\s")
TABLE = re.compile(r"^\s*\|")
QUOTE = re.compile(r"^\s*>")
RULE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
# A paragraph the agent prepared for someone else: a letter header or a label naming a draft.
DRAFT_LABEL = re.compile(r"^\s*[*_]{0,2}(?:(?:draft|subject|черновик|тема письма)\b[^\n]{0,40}?:|"
                         r"(?:to|кому)\s*:|dear\b)", re.I)
QUOTE_PAIRS = {'"': '"', "“": "”", "«": "»", "'": "'", "‘": "’"}
SOURCES = re.compile(r"^\s*[*_]{0,2}(?:sources?|references?|links?|further reading|источники|ссылки|литература)"
                     r"[^\n:]{0,30}:[*_]{0,2}\s*$", re.I)
SOURCES_HEADING = re.compile(r"^[*_]{0,2}(?:sources?|references?|links?|further reading|источники|ссылки|"
                             r"литература)[*_]{0,2}:?$", re.I)
ANNOUNCE = re.compile(r"вопрос|question|решени|decide|выбер|choose", re.I)
LINK_ONLY = re.compile(r"^\s*(?:[-*+•]\s*)?(?:<?https?://\S+>?|\[[^\]\n]{0,300}\]\([^)\s]{0,500}\))[\s.,;]*$")

# ---------------------------------------------------------------- what asks
TRAIL_CHARS = set(" \t\n\"”'’)]}»*_`")
QUOTED = re.compile(r"«[^»\n]{0,400}»|“[^”\n]{0,400}”|\"[^\"\n]{0,400}\"|`[^`\n]{0,400}`")
URL = re.compile(r"https?://[^\s`'\"<>)\]]+")
MD_LINK = re.compile(r"\[([^\]\n]{0,300})\]\([^)\s]{0,500}\)")
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")

# Russian imperatives a reader is asked with (2nd person; the -те form is added below).
# Discourse words (смотри, учти, представь, считай, подожди, держи) are left out on purpose.
RU_IMP = set("""
скажи напиши пиши ответь отпиши отпишись подтверди одобри утверди разреши согласуй реши решай
выбери выбирай дай сообщи уточни назови подскажи пришли присылай кинь скинь перешли отправь вышли
передай верни напомни отметь укажи поставь ставь оцени глянь взгляни посмотри проверь перепроверь
сверь прочитай прочти почитай послушай прослушай полистай пролистай пройди открой закрой нажми
жми нажимай кликни тапни ткни зайди войди залогинься авторизуйся зарегистрируйся подключи включи
выключи отключи запусти перезапусти останови установи удали сотри добавь вставь скопируй сохрани
загрузи выгрузи скачай обнови перезагрузи повтори попробуй сделай создай заполни введи вбей
подпиши оплати переведи пополни забронируй бронируй закажи купи позвони свяжись запиши
разблокируй перенеси переименуй смерджи смёрджи залей запушь задеплой закоммить выложи опубликуй
публикуй отмени разгреби прокрути подумай прикинь определись найди поищи покажи расскажи объясни
предложи продиктуй сфоткай сфотографируй приложи прикрепи подними настрой поменяй смени замени
исправь поправь убедись убери пропусти прими отклони согласись откажись переключи переключись
перейди переходи маякни черкни направь направляй закрывай открывай отвечай проверяй запускай
бери возьми кидай звони заходи скачивай загружай удаляй добавляй выкладывай плати оплачивай
покупай заказывай вводи заполняй подписывай подтверждай отмечай отправляй пересылай передавай
помоги помогай разберись соглашайся включай выключай подключай перезапускай обновляй пробуй
повторяй делай создавай меняй правь почини чини загляни заглядывай
""".split())
RU_IMP |= {w + "те" for w in RU_IMP}
RU_WORD = re.compile(r"[а-яё]+(?:-[а-яё]+)?")
RU_TALK = "сказать|сообщить|напомнить|объяснить|признаться|рассказать|написать|показать|отправить|прислать|передать"  # «нужно сказать тебе, что…»

RU_REQUEST = [re.compile(p) for p in (
    r"\b(?:нужн[оаеы]|нужен|требуется|жду|ждём|ждем|ждёт|ждет|ожидаю|ждут)\b[^.!?\n]{0,40}?"
    r"(?:\bтво(?:[её]|й|ю|его|их|и)\b|\bваш(?:[её]|у|его|ей|и)\b|\bот (?:тебя|вас)\b)",
    r"\b(?:тво[её]|твой|твоя|ваш[ее])\s+(?:слово|решение|ок|окей|«да»|подтверждение|выбор|согласие|ответ)\b",
    r"(?:решени[ея]|выбор|слово|ход|очередь|вопрос[ы]?)\s+за\s+(?:тобой|вами)\b",
    r"\bот (?:тебя|вас)\s+(?:нужн|нужен|требуется|жду|ждём)",
    r"\bс тебя\s*:",
    r"\bвопрос[ыа]?\s+(?:к тебе|к вам|для тебя)\b",
    r"\b(?:если|когда|как только)\s+(?:ты\s+)?(?:скажешь|напишешь|ответишь|дашь)\b",
    r"\bпо (?:твоему|вашему) (?:слову|ответу|решению|команде|знаку|сигналу)\b",
    r"\b(?:осталось|остаётся|остается|нужно|надо)\s+(?:(?!(?:" + RU_TALK + r")\b)[а-яё]+\s+){0,2}(?:тебе|вам)\b",
    r"\b(?:тебе|вам)\s+(?:осталось|остаётся|остается)\b",
    r"\bреш(?:ать|ить)\s+(?:тебе|вам)\b|\b(?:тебе|вам)\s+реш(?:ать|ить)\b",
    r"\bможешь\s+(?:сразу\s+)?(?:сказать|написать|писать|прислать|присылать|ответить|отвечать|"
    r"подтвердить|проверить|посмотреть|открыть|нажать|жать|выбрать|решить|дать|переслать|запустить)\b",
    r"\bне забудь(?:те)?\b",
)]
RU_NOTHING = re.compile(
    r"\b(?:от (?:тебя|вас) ничего|ничего (?:от (?:тебя|вас) )?не (?:нужно|надо|требуется)|"
    r"(?:тебе|вам) ничего (?:делать )?не (?:нужно|надо))")
# Courtesy lines are cut out of a sentence before it is judged; what is left still counts.
RU_COURTESY = re.compile(
    r"если (?:будут|появятся|возникнут) вопросы[^.!?;]*|если что[- ]?(?:то)?(?: ещё)?[,—-]*\s*(?:пиши|обращайся)|"
    r"\bобращайся\b|чем ещё (?:могу )?помочь|что-нибудь ещё")

EN_IMP = set("""
approve confirm choose pick decide reply answer tell send run open click press tap check review
restart reload refresh install add paste copy try test merge push deploy sign pay visit enable
disable grant give share upload download rate update rename delete remove select accept reject
forward provide fill enter type start stop close read watch scroll attach rotate revoke set turn
switch move put create make book call email message ping remind mark verify retry rerun launch
unblock allow authorize connect log go look take reply respond recompile rebuild discard
implement come keep commit say remember edit re-run ensure
""".split())
EN_PHRASAL = {verb: re.compile(rx) for verb, rx in {
    "look": r" (?:at|into|over|through)\b", "go": r" (?:to|into|ahead|through|over)\b",
    "take": r" (?:a look|a peek|another (?:look|pass|stab)|a (?:second|closer) look)\b", "make": r" (?:sure|a call|the call)\b",
    "set": r" (?:up|it|the)\b", "turn": r" (?:on|off)\b", "log": r" (?:in|into|on)\b",
    "type": r" (?:in|the|your)\b", "start": r" (?:the|a|it|with|by)\b", "stop": r" (?:the|it)\b",
    "come": r" back\b", "keep": r" (?:an eye|me posted|this|the|it) ?", "remember": r" to\b",
    "commit": r" (?:the|it|this|that|these|those|all|everything|your|my|both|them|now|and|changes|to)\b",
    "call": r" (?:me|them|the|him|her|q)\b"}.items()}
# "Deploy succeeded", "Test coverage is 94%": the verb is a noun when a predicate follows it.
EN_PREDICATE = set("""
is are was were be been has have had passes starts runs goes looks returns takes will won't can cannot
should ok okay complete done ran went took work works go look seem seems
""".split())
EN_PREP = set("to in at on for by from with into via".split())
EN_STOP = set("the a an this that these those it them your my our their his her all any every some everything nothing".split())
# Verbs that take a whole clause ("check CI is green"): only a predicate right after them makes them nouns.
EN_CLAUSE_VERBS = set("check verify confirm ensure make mark see".split())
EN_PARTICIPLE = set("pending running ongoing underway".split())
EN_LEAD = re.compile(
    r"^(?:(?:please|now|then|next|so|just|also|first|finally|meanwhile|and|ok|okay)\b[,:]?\s+)*", re.I)
EN_SUBJECT = re.compile(r"^(?:you|we|i|it|this|that|these|those|they|he|she|there|the|a|an|my|your|our|its|"
                        r"their|all|both|each|every|nothing|everything)\b")
EN_PURPOSE = re.compile(r"^(?:to|for) [a-z]+(?: [a-z/]+){0,5},\s*")
EN_COND = re.compile(r"^(?:if|when|once|after|before|whenever|as soon as)\b[^,]{0,120},\s*", re.I)
EN_REQUEST = [re.compile(p, re.I) for p in (
    r"\b(?:need|needs|needed|waiting (?:on|for)|awaiting|pending|requires?)\b[^.!?\n]{0,30}\byour\s+"
    r"(?:approval|go-ahead|ok|okay|decision|input|answer|reply|confirmation|call|sign-off|choice|"
    r"review|word|permission)",
    r"\b(?:your (?:call|choice|decision|move)|up to you|over to you)\b",
    r"\blet me know\b",
    r"\bwhen(?:ever)? you(?:'re| are) ready\b|\bwhen you are\W*$",
    r"\btell me (?:which|what|whether|if|when)\b",
    r"\bsay (?:the word|yes|\"?go\"?)\b",
    r"\breply (?:with|yes)\b",
    r"\bgive me (?:the|a|your) (?:go-ahead|ok|okay|word)\b",
    r"\bquestions? (?:for you|to you)\b",
    r"\b(?:if|once|when) you (?:say|confirm|approve|reply|answer|give)\b",
    r"\b(?:on|with|after) your (?:word|go-ahead|green light|ok|okay|approval|signal)\b",
    r"\b(?:left|remaining) for you\b|\byour (?:turn|part)\b",
    r"\bplease\s+(?:" + "|".join(sorted(EN_IMP)) + r")\b",
)]
EN_NOTHING = re.compile(r"\b(?:no action (?:is )?(?:needed|required)|nothing (?:for you|needed from you))\b", re.I)
EN_COURTESY = re.compile(
    r"let me know if (?:you )?(?:have|need|want|'d like|would like|run into)?\s*(?:any|anything|more|"
    r"further|other)[^.!?;]*|feel free to [^.!?;,]*|\bfeel free\b|hope (?:this|that|it) helps|"
    r"don't hesitate to [^.!?;,]*|happy to help|(?:is there )?anything else(?: i can help with| i can do|"
    r" you need| you'd like)?|\bany (?:other |more )?questions\b", re.I)


def _plain(text: str) -> str:
    """Drop markdown that hides words: links keep their text, URLs become a word."""
    text = MD_LINK.sub(r"\1", text)
    text = URL.sub("URL", text)
    text = LIST_ITEM.sub("", text, count=1)
    text = re.sub(r"(?<!\w)(\*\*|__|\*|_|~~)(?=\S)|(?<=\S)(\*\*|__|\*|_|~~)(?!\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _sentences(block: str) -> list[str]:
    """Sentences of a paragraph. Lines stay apart (state lines, labels), except a hard wrap: a line
    that stops mid-sentence is joined to the next one when that one starts in lower case."""
    lines: list[str] = []
    for line in block.split("\n"):
        line = _plain(line)
        if lines and line[:1].islower() and lines[-1] and lines[-1][-1] not in ".!?:…;":
            lines[-1] += " " + line
        elif line:
            lines.append(line)
    out: list[str] = []
    for line in lines:
        for part in re.split(r"\s+·\s+", line):
            for s in re.split(r"(?:(?<=[.!?…])|(?<=[.!?…][\"”'’)\]»])|(?<=[.!?…][\"”'’)\]»]{2}))\s+(?=\S)", part):
                if re.search(r"\w", s):
                    out.append(s.strip())
    return out


def _is_emoji(ch: str) -> bool:
    o = ord(ch)
    return 0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or o in (0xFE0F, 0x200D)


def _strip_trailing(s: str) -> str:
    """Closing quotes, brackets, markdown and emoji after a sentence's last mark (linear time)."""
    i = len(s)
    while i and (s[i - 1] in TRAIL_CHARS or _is_emoji(s[i - 1]) or ord(s[i - 1]) < 32 or 0x7F <= ord(s[i - 1]) <= 0x9F):
        i -= 1
    return s[:i]


def _is_question(s: str) -> bool:
    """Ends with '?', is not wholly a quotation («Почему бот молчал?» — the reply then answers it), and is
    more than a courtesy line ('Anything else?')."""
    if not _strip_trailing(s).endswith("?"):
        return False
    t = s.strip()
    close = QUOTE_PAIRS.get(t[:1])
    if close and len(t) > 1 and t.find(close, 1) == len(_strip_trailing(t)) and t.endswith(close):
        return False
    rest = EN_COURTESY.sub(" ", RU_COURTESY.sub(" ", s.lower()))
    return re.search(r"\w", rest) is not None


def _noun_use(verb: str, after: list[str]) -> bool:
    """True when a predicate follows the would-be verb before any article or pronoun:
    'deploy succeeded', 'test coverage is', 'push to main succeeded'; not 'check the build is green'.
    After check/verify/confirm only a predicate right after the verb counts: 'check passed' is a noun,
    'check CI is green' is an order."""
    words = [w.strip(",.!:;") for w in after]
    if verb in EN_CLAUSE_VERBS:
        words = words[:1]
    for k, w in enumerate(words):
        last = k == len(words) - 1 and len(after) == len(words)
        if w in EN_STOP:
            return False
        if w in EN_PREDICATE:
            return True
        if (w.endswith("ed") or w in EN_PARTICIPLE) and (last or (k + 1 < len(words) and words[k + 1] in EN_PREP)):
            return True  # "Answer drafted.", "Push to main succeeded", not "Rerun failed jobs"
    return False


def _en_imperative(low: str) -> bool:
    """An English clause that opens with a verb from EN_IMP: 'Run…', 'If it fails, open…', 'Run X and visit Y'."""
    clauses = [c.strip(" -–—*") for c in re.split(r"[;:]\s+|\s+[-–—]\s+", low)]
    for k, clause in enumerate(clauses):
        nxt = clauses[k + 1] if k + 1 < len(clauses) else None
        if nxt is not None and len(clause.split()) <= 3 and len(nxt.split()) <= 2 and nxt.strip(" .") != "q":
            continue  # "Open issues: none." is a label and its value
        if nxt is not None and len(clause.split()) == 1 and nxt.strip(" .") != "q":
            continue  # "Update: the job finished.", but "Run: `npm test`" is an order
        head = EN_PURPOSE.sub("", EN_COND.sub("", EN_LEAD.sub("", clause)))
        if re.match(r"(?:don'?t|do not) forget\b", head):
            return True
        # "run X and visit Y": the second verb counts only when the clause has no subject
        parts = [head] if EN_SUBJECT.match(head) else re.split(r",?\s+(?:and|then|and then)\s+", head)
        for part in parts:
            m = re.match(r"([a-z]+(?:-[a-z]+)?)\b(.*)", EN_LEAD.sub("", part))
            if not m or m.group(1) not in EN_IMP:
                continue
            if m.group(1) in EN_PHRASAL and not EN_PHRASAL[m.group(1)].match(m.group(2)):
                continue  # "look", "go", "take" count only as "look at", "go to", "take a look"
            if _noun_use(m.group(1), m.group(2).split()[:3]):
                continue  # "Deploy succeeded", "Review complete": a noun, not an order
            return True
    return False


def _is_request(s: str) -> bool:
    low = QUOTED.sub(" Q ", s).lower()
    if RU_NOTHING.search(low) or EN_NOTHING.search(low):
        return False
    low = EN_COURTESY.sub(" ", RU_COURTESY.sub(" ", low))
    words = RU_WORD.findall(low)
    for i, w in enumerate(words):
        if w.endswith("-ка"):
            w = w[:-3]  # «скажи-ка»
        before = words[i - 1] if i else ""
        if w in RU_IMP and before not in ("не", "ни") and not (w.endswith("те") and before == "вы"):
            return True  # «вы платите…» is a statement, «платите…» is not
    if any(p.search(low) for p in RU_REQUEST) or any(p.search(low) for p in EN_REQUEST):
        return True
    if len(re.findall(r"[а-яё]", low)) > 3:
        return False  # a Russian sentence that opens with an English word ("Push не ушёл")
    return _en_imperative(low)


def _is_draft(body: str) -> bool:
    """A paragraph wholly inside one quotation, or one that opens a letter ('To:', 'Draft:', 'Dear …').
    «Чини» или «оставь»? opens with a quote mark but is not a quotation."""
    if DRAFT_LABEL.match(body):
        return True
    text = body.strip()
    close = QUOTE_PAIRS.get(text[:1])
    if not close:
        return False
    end = text.rstrip(" \t\n.,;:!?…")
    return len(end) > 1 and text.find(close, 1) == len(end) - 1


def _is_sources(body: str) -> bool:
    """'Sources: [a](..), [b](..)': a label followed by nothing but links."""
    m = re.match(r"\s*[*_]{0,2}(?:sources?|references?|links?|источники|ссылки|литература)"
                 r"[^:\n]{0,30}:[*_]{0,2}", body, re.I)
    if not m:
        return False
    raw = body[m.end():]
    if not (URL.search(raw) or MD_LINK.search(raw)):
        return False  # "Links to check:" alone is a label for what follows, not a list of sources
    rest = URL.sub("", MD_LINK.sub("", raw))
    return re.fullmatch(r"[\s·,;•\-–—|.()]*", rest) is not None


def _is_link_item(body: str) -> bool:
    """A list item that is a link with at most a short title, and asks nothing."""
    if not (URL.search(body) or MD_LINK.search(body)):
        return False
    rest = URL.sub(" ", MD_LINK.sub(r" \1 ", LIST_ITEM.sub("", body, count=1)))
    return len(re.findall(r"\w+", rest)) <= 12 and not _is_request(_plain(body))


def _units(text: str) -> list[tuple[str, str]]:
    """Split a message into ('prose', paragraph), ('item', list item) and ('heading', text) units, in
    order. Code, tables, quotes and rules are prepared material and are dropped."""
    units: list[tuple[str, str]] = []
    para: list[str] = []
    fence: tuple[str, int] | None = None
    in_item = False

    def close() -> None:
        if para:
            units.append(("prose", "\n".join(para)))
            para.clear()

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        f = FENCE.match(line)
        if fence:
            if f and f.group(1)[0] == fence[0] and len(f.group(1)) >= fence[1] and not f.group(2).strip():
                fence = None
            continue
        if f and not (f.group(1)[0] == "`" and "`" in f.group(2)):
            close()
            fence, in_item = (f.group(1)[0], len(f.group(1))), False
            continue
        if not line.strip() or RULE.match(line) or TABLE.match(line) or QUOTE.match(line):
            close()
            in_item = False
        elif HEADING.match(line):
            close()
            units.append(("heading", line.strip().lstrip("#").strip()))
            in_item = False
        elif LIST_ITEM.match(line):
            close()
            units.append(("item", line.strip()))
            in_item = True
        elif in_item and not para:
            units[-1] = ("item", units[-1][1] + " " + line.strip())  # a continuation line of the item
        else:
            para.append(line.rstrip())
    close()
    return units


def _strip_references(units: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Drop a closing 'Sources:' section and bare link lines: references, not speech."""
    for i in range(len(units) - 1, -1, -1):
        kind, body = units[i]
        if kind not in ("prose", "heading"):
            continue
        label, _, rest = body.partition("\n")
        tail = units[i + 1:]
        if ((SOURCES.match(label) or (kind == "heading" and SOURCES_HEADING.match(label))) and all(LINK_ONLY.match(r) for r in rest.split("\n") if r.strip())
                and tail and all(k == "item" and _is_link_item(b) for k, b in tail)) or _is_sources(body):
            units = units[:i]
        break
    while units and units[-1][0] != "heading" and LINK_ONLY.match(units[-1][1]):
        units.pop()
    return units


def ending(text: str | None) -> dict:
    """How a message ends: {'asks': bool, 'kind': 'question' | 'request' | None, 'tail': str | None}.

    The ending is the last paragraph the agent says to the reader. Code, tables, quotes, drafts
    and a closing list of sources are set aside. A list after that paragraph counts only when its
    last item asks the reader to act, or when the paragraph or a heading announces questions.
    """
    text = re.sub(r"<!--.*?-->", "", text or "", flags=re.S)
    if len(text) > MAX_CHARS:
        cut = len(text) - MAX_CHARS
        cut = text.find("\n", cut) + 1 or cut
        opened = 0
        for line in text[:cut].split("\n"):
            if FENCE.match(line):
                opened ^= 1  # approximate: enough to know whether the cut lands inside a code block
        text = ("```\n" if opened else "") + text[cut:]
    units = _strip_references([u for u in _units(text) if re.search(r"\w", u[1])])
    content = [u for u in units if u[0] != "heading"]
    if not content:
        return {"asks": False, "kind": None, "tail": None}
    spoken = [i for i, (k, b) in enumerate(units) if k == "prose" and not _is_draft(b)]
    last = spoken[-1] if spoken else -1
    sents = _sentences(units[last][1]) if spoken else []
    items = [b for k, b in units[last + 1:] if k == "item"]
    if items:
        heads = [b for k, b in units[last + 1:] if k == "heading"]
        announces = (bool(sents) and sents[-1].endswith(":") and ANNOUNCE.search(sents[-1]) is not None) or \
            any(ANNOUNCE.search(h) for h in heads)
        lead = sents[-1:] if announces and sents else heads[-1:]
        item = _sentences(items[-1]) or [_plain(items[-1])]
        for j in range(len(item) - 1, -1, -1):
            if _is_request(item[j]):
                return _result(True, "request", item[j], item[:j] or lead)
        if announces and _is_question(item[-1]):
            return _result(True, "question", item[-1], item[:-1] or lead)
    if not spoken:  # only lists or drafts: nothing is said to the reader
        last_body = content[-1][1]
        sents = _sentences(last_body) or [_plain(last_body)]
        return _result(False, None, sents[-1], sents[:-1])
    for j in range(len(sents) - 1, -1, -1):
        if _is_question(sents[j]):
            return _result(True, "question", sents[j], sents[:j])
        if _is_request(sents[j]):
            return _result(True, "request", sents[j], sents[:j])
    sents = sents or [_plain(units[last][1])]
    return _result(False, None, sents[-1], sents[:-1])


def _result(asks: bool, kind: str | None, sentence: str, before: list[str]) -> dict:
    if len(sentence) < SHORT and before:
        sentence = f"{before[-1]} {sentence}"
    sentence = CONTROL.sub("", sentence)
    if len(sentence) > TAIL_MAX:
        sentence = sentence[:TAIL_MAX - 1].rstrip() + "…"
    return {"asks": asks, "kind": kind, "tail": sentence or None}


# ---------------------------------------------------------------- inputs
def _blocks(message) -> list:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _is_prompt(entry: dict) -> bool:
    """A user entry a human typed, not a tool result or an injected note."""
    if entry.get("isMeta"):
        return False
    blocks = _blocks(entry.get("message"))
    if any(b.get("type") == "tool_result" for b in blocks):
        return False
    text = " ".join(b["text"] for b in blocks if isinstance(b.get("text"), str))
    return bool(text.strip()) and not text.lstrip().startswith(
        ("<command-", "<local-command", "Caveat:", "[Request interrupted"))


def last_assistant_text(path: str, sidechain: bool = False) -> str:
    """The text the assistant wrote after its last tool call in the last turn of a transcript.
    Lines that are not the shape Claude Code writes are skipped, not fatal."""
    pending: list[str] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if not isinstance(entry, dict) or (entry.get("isSidechain") and not sidechain):
                continue
            message = entry.get("message")
            if entry.get("type") == "assistant":
                if entry.get("isApiErrorMessage") or (isinstance(message, dict) and message.get("model") == "<synthetic>"):
                    continue
                for block in _blocks(message):
                    if block.get("type") == "text" and isinstance(block.get("text"), str) and block["text"].strip():
                        pending.append(block["text"])
                    elif block.get("type") == "tool_use":
                        pending = []
            elif entry.get("type") == "user":
                if _is_prompt(entry) or any(b.get("type") == "tool_result" for b in _blocks(message)):
                    pending = []
    return "\n\n".join(pending)


def _read_stdin() -> str:
    data = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read()
    return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Does an agent's last message end by asking you something?")
    ap.add_argument("file", nargs="?", help="message text file (default: stdin)")
    ap.add_argument("--transcript", metavar="JSONL", help="Claude Code transcript: read its last reply")
    ap.add_argument("--hook", action="store_true", help="stdin is a Claude Code Stop hook payload")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    ap.add_argument("-q", "--quiet", action="store_true", help="print nothing, only set the exit code")
    args = ap.parse_args(argv)
    try:
        if args.hook:
            payload = json.loads(_read_stdin())
            if not isinstance(payload, dict):
                raise ValueError("hook payload is not a JSON object")
            text = payload.get("last_assistant_message")
            if not isinstance(text, str) or not text.strip():
                agent = payload.get("agent_transcript_path")
                path = agent if isinstance(agent, str) and agent else payload.get("transcript_path")
                text = last_assistant_text(path, sidechain=path is agent) if isinstance(path, str) and path else ""
        elif args.transcript:
            text = last_assistant_text(args.transcript)
        elif args.file:
            with open(args.file, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        else:
            text = _read_stdin()
        result = ending(text)
    except Exception as exc:  # anything unreadable is exit 2, never a silent "it only reports"
        print(f"reply-ending: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not args.quiet:
        line = json.dumps(result, ensure_ascii=False) if args.json else \
            ("asks" if result["asks"] else "done") + "\t" + (result["tail"] or "")
        out = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else None
        if out is not None:
            out.write((line + "\n").encode("utf-8"))
            out.flush()
        else:
            print(line)
    return 0 if result["asks"] else 1


if __name__ == "__main__":
    sys.exit(main())
