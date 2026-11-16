#!/usr/bin/env python3
"""Plain-script tests for reply_ending.py. Run: python3 tests/test_reply_ending.py  (exit 1 on any failure)."""
import contextlib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)


def _blocked(*a, **k):
    raise OSError("network blocked in tests")


socket.socket.connect = _blocked

import reply_ending as R  # noqa: E402

PASSED = FAILED = 0


def check(name, cond, detail=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("PASS", name)
    else:
        FAILED += 1
        print("FAIL", name, detail)


def asks(text):
    return R.ending(text)["asks"]


def tail(text):
    return R.ending(text)["tail"]


# ---------------------------------------------------------------- questions
check("q: plain English question", asks("Which one should I use?"))
check("q: plain Russian question", asks("Какой вариант берём?"))
check("q: emoji after the question mark", asks("Which one should I use? 🙂"))
check("q: closing quote and bold", asks("**Shall I send it?**"))
check("q: guillemets", asks("Он спросил: «Отправить сейчас?»"))
check("q: remark after the question in the same paragraph", asks("Ready. Shall I send it? Otherwise I stop here."))
check("q: question in an earlier paragraph only", not asks("Should I push?\n\nPushed it anyway, tests are green."))
check("q: question mark inside a URL is not a question", not asks("Report: https://example.org/x?id=3 is up."))
check("q: courtesy question", not asks("All done. Anything else?"))
check("q: courtesy question, Russian", not asks("Готово. Чем ещё помочь?"))
check("q: kind is question", R.ending("Push now?")["kind"] == "question")

# ---------------------------------------------------------------- Russian requests
for text in [
    "Скажи «да», и я выложу.",
    "Если хочешь второй вариант, напиши «два».",
    "Нажми play и скажи, заиграло ли.",
    "Пришлите, пожалуйста, текст согласия.",
    "Нужно твоё «да» на перезапуск.",
    "Какой из двух вариантов брать, решение за тобой.",
    "Жду твоего ответа по ставке.",
    "Эту дыру закрою отдельно, если скажешь «чини».",
    "Осталось сделать тебе: обнови токен в настройках.",
    "Решить тебе одно: оставить старую версию или удалить.",
    "Около восьми утра проверь почту и перешли мне письмо.",
    "Начну по твоему слову.",
    "Можешь сразу писать «публикуй».",
]:
    check(f"ru ask: {text}", asks(text), str(R.ending(text)))
for text in [
    "Жду ответа от CI.",
    "Жду перезапуска сервера после обновления.",
    "От тебя ничего не нужно.",
    "Тебе ничего делать не нужно, бронь остаётся.",
    "Не трогай ничего, я закончу сама.",
    "Смотри: тесты зелёные, всё выложено.",
    "Учти, что ночью сервер перезагружается.",
    "Если будут вопросы, пиши.",
    "Могу ещё прогнать весь список.",
    "Дальше ход за дизайнером: он пришлёт макет.",
    "Push в календарь не прошёл: токен устарел.",
    "Цены и сроки решаешь ты, как и раньше.",
]:
    check(f"ru done: {text}", not asks(text), str(R.ending(text)))
check("ru: kind is request", R.ending("Скажи «да».")["kind"] == "request")
check("ru: imperative inside quotes does not count", not asks("Бот ответил «Нажмите старт» и замолчал."))

# ---------------------------------------------------------------- English requests
for text in [
    "Let me know which one you prefer.",
    "Let me know if it looks right.",
    "Run `npm test` and tell me what fails.",
    "Say the word and I'll push.",
    "Commit the changes when you are ready.",
    "Don't forget to run the migration before deploying.",
    "Waiting on your approval to deploy.",
    "Next, on your green light: commit items 1-3, then push the branch.",
    "To verify visually, run `npm run dev` and visit the page.",
    "Please confirm the threshold.",
    "Once the secret is in, say the word and I'll open the PR.",
    "Ready to commit when you are.",
    "Go ahead and run `fly deploy`.",
]:
    check(f"en ask: {text}", asks(text), str(R.ending(text)))
for text in [
    "Waiting on CI.",
    "No action needed.",
    "Hope this helps!",
    "Feel free to reach out.",
    "Let me know if you have any questions.",
    "You can now use Python and install packages in this environment.",
    "Commit `f479ad3` is now on main.",
    "Committed as `5866b2b`.",
    "Note that the cache resets nightly.",
    "See the table above for details.",
    "I'll check again at 8:25.",
    "If you want, I can also add a Dockerfile.",
    "Take a deep breath; the build is green.",
]:
    check(f"en done: {text}", not asks(text), str(R.ending(text)))

# ---------------------------------------------------------------- what is set aside (cases of the source's tests)
for text in [
    "Which date works?\n\n- Friday\n- Monday",
    "Which version?\n\n> Would you like a quote?",
]:
    check(f"source case asks: {text!r}", asks(text))
for text in [
    "- Is Friday okay?",
    "> Is Friday okay?",
    "“Can we book Friday?”",
    "Done.\n\n- Why not Friday?",
    "I found the date.\n\n**Draft:** Can we book Friday?",
]:
    check(f"source case done: {text!r}", not asks(text))

check("struct: Sources list after the ask", asks("Скажи, если подключать.\n\n**Sources:**\n- [Docs](https://a.example/x)\n- [Pricing](https://a.example/y)"))
check("struct: inline Sources line after the ask", asks("Say which repo to use.\n\nSources: [docs](https://a.example/x), [blog](https://b.example/y)"))
check("struct: bare URL line after the ask", asks("Open the link on your phone and scroll to the end:\nhttps://preview.example.org"))
check("struct: code block after the ask", asks("Run this and tell me the output:\n\n```bash\nuname -a\n```"))
check("struct: table after a report", not asks("Done.\n\n| Change | Rollback |\n|---|---|\n| config | git revert abc |"))
check("struct: question only inside a code block", not asks("Updated.\n\n```\nread -p 'Continue?'\n```"))
check("struct: last list item asks", asks("Status:\n\n- Tests green.\n- Nine stale tasks in Today. Say «clean up» and I'll sort them."))
check("struct: last list item reports", not asks("Status:\n\n- Tests green.\n- Deployed at 10:02."))
check("struct: announced questions", asks("Two questions before I start:\n\n1. Fixed enum or admin-editable?\n2. Does the homepage need a map?"))
check("struct: options list without a question", not asks("Options:\n\n1. Postgres\n2. SQLite"))
check("struct: html comment ignored", not asks("Done.<!-- Should I push? -->"))
check("struct: Russian draft in quotes", not asks("Нашла ответ клиенту.\n\n«Здравствуйте! Когда удобно созвониться?»"))
check("struct: empty", R.ending("") == {"asks": False, "kind": None, "tail": None})
check("struct: None", R.ending(None) == {"asks": False, "kind": None, "tail": None})
check("struct: only code", R.ending("```\nls\n```") == {"asks": False, "kind": None, "tail": None})
check("struct: status lines end in a report", not asks("Тесты: зелёные · Сборка: идёт · Релиз: завтра"))

# ---------------------------------------------------------------- cases from the independent review
for text in [
    "To finish setup: run `make install` and restart the app.",
    "Готово.\n\nСсылки тоже обновить?",
    "Done.\n\nLinks ok?",
    "Deployed.\n\nLinks to check:\n\n- Open https://x.example and tell me if the banner shows.",
    "Should I merge, or is there anything else you need?",
    "Feel free to say no, but should I deploy tonight?",
    "Run `make migrate` before deploying; anything else is handled by CI.",
    "Обращайся к логам, если что, а пока проверь конфиг.",
    "- Tests green.\n- Say «go» and I'll deploy.",
    "«Чини» или «оставь»?",
    '"Yes" or "no"?',
    "## Open questions\n\n- Postgres or SQLite?\n- Do we need auth?",
    "Не забудь перезапустить бота после правки.",
    "Скажи-ка, какой вариант оставить.",
    "Waiting on\nyour approval.",
    "````\n```\n````\n\nShould I merge?",
    "```npm test``` passes now. Should I merge?",
    "Check the build is green before you merge.",
    "Run this: `make test`",
    "Try running it yourself now to confirm it works.",
    "Rerun failed jobs and tell me what breaks.",
    "Check failed tests in the CI log.",
    "Then take another pass at the function.",
    "Check CI is green before merging.",
    "Make sure CI is green before you merge.",
    "Confirm staging looks right.",
    "Verify everything is committed.",
    "Check prod is up.",
    "Mark task done in Jira.",
    "Verify signed in users can post.",
    "Run: `npm test`",
    "Re-run it: `make test`",
    "Done.\n\n## Sources\n\n- [Docs](https://a.example/x)\n\nWhich option do you prefer?",
]:
    check(f"review ask: {text!r}", asks(text), str(R.ending(text)))
for text in [
    "Should I merge?\n\nLinks verified, all 200.",
    "Deploy succeeded at 10:02.",
    "Test coverage is now 94%.",
    "Review complete, no issues found.",
    "Push to main succeeded.",
    "Open issues: none.",
    "Update: the nightly job finished.",
    "Once CI is green, deploy starts automatically.",
    "I'll make sure to rerun the suite tonight.",
    "Нужно сказать тебе, что бот ночью упал.",
    "Подписка: вы платите 349 ₽ в месяц.",
    "Thanks! Any questions?",
    "Answer drafted.\n\n“Can we move the call to Friday?”",
    "«Почему бот молчал?» — фид упал в три ночи, я его подняла.",
    '"Why did the bot stop?" The feed died at 03:10 and I restarted it.',
    "Log in now works for all users.",
    "Осталось только показать тебе итог, он ниже.",
    "Push notifications now work.",
    "Test results look good.",
    "Review pending on GitHub.",
    "Status: deploy pending.",
    "Check passed.",
]:
    check(f"review done: {text!r}", not asks(text), str(R.ending(text)))
check("review: a control character after the question mark still leaves a question", asks("Ship it?\x00"))
check("review: control characters are dropped from the sentence", "\x1b" not in tail("Merge it?\x1b[31m now?") and
      "\x00" not in tail("Ready\x00. Merge?"))
check("review: sources heading is set aside", tail("Pushed. Merge it?\n\n## Sources\n\n- [a](https://a.example)") ==
      "Pushed. Merge it?")
import time  # noqa: E402
t0 = time.time()
for hostile in ["Run [" * 40000, ")" * 40000 + "?", "«" * 40000, "`" * 40000, "a. " * 100000]:
    R.ending(hostile)
check("review: hostile 200 KB inputs stay fast", time.time() - t0 < 5, time.time() - t0)
big = "Intro.\n\n```\n" + "x\n" * 30000 + "```\n\n" + "Filler sentence. " * 3000 + "\n\nShould I merge?"
check("review: a long message is read from its end", asks(big))

# ---------------------------------------------------------------- the tail
check("tail: the asking sentence, not the remark after it", tail("Push now? Otherwise I stop here.") == "Push now?")
check("tail: a short sentence keeps the one before it", tail("All tests pass. Merge it?") == "All tests pass. Merge it?")
check("tail: the last sentence when nothing asks", tail("Fixed the bug. All forty tests are green now.") == "All forty tests are green now.")
check("tail: markdown removed", tail("**Done.** Say «go» and I'll deploy the *new* build.") == "Say «go» and I'll deploy the new build.")
check("tail: snake_case kept", "chunks_prev" in tail("Run one dictation and check that `chunks_prev` appears."))
long = "Reply with " + "the full list of every server name " * 12 + "please."
check("tail: capped at 240 with an ellipsis", len(tail(long)) == 240 and tail(long).endswith("…"))
check("tail: link text kept", tail("Read [the guide](https://x.example/g) and tell me.") == "Read the guide and tell me.")

# ---------------------------------------------------------------- transcripts and hooks
def entry(kind, content, **extra):
    return json.dumps({"type": kind, "message": {"role": kind, "content": content}, **extra})


lines = [
    entry("user", "fix the bug"),
    entry("assistant", [{"type": "text", "text": "Looking."}, {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]),
    entry("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]),
    entry("assistant", [{"type": "text", "text": "Side note from a subagent?"}], isSidechain=True),
    entry("assistant", [{"type": "text", "text": "Fixed. Should I push?"}]),
    entry("assistant", [{"type": "text", "text": "API Error: 529 overloaded"}], isApiErrorMessage=True),
]
tmp = tempfile.mkdtemp()
tpath = os.path.join(tmp, "session.jsonl")
with open(tpath, "w") as fh:
    fh.write("\n".join(lines) + "\nnot json\n")
check("transcript: text after the last tool call", R.last_assistant_text(tpath) == "Fixed. Should I push?", R.last_assistant_text(tpath))
with open(tpath, "a") as fh:
    fh.write(entry("user", "and now the docs") + "\n")
check("transcript: a new prompt with no reply yet gives nothing", R.last_assistant_text(tpath) == "")
meta = os.path.join(tmp, "meta.jsonl")
with open(meta, "w") as fh:
    fh.write(entry("assistant", [{"type": "text", "text": "Deploy now?"}]) + "\n")
    fh.write(entry("user", "<command-name>/cost</command-name>") + "\n")
    fh.write(entry("user", "note", isMeta=True) + "\n")
check("transcript: slash-command and meta entries are not prompts", R.last_assistant_text(meta) == "Deploy now?")


def run(args, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = R.main(args)
    finally:
        sys.stdin = old_stdin
    return code, out.getvalue(), err.getvalue()


code, out, _ = run(["--hook"], json.dumps({"hook_event_name": "Stop", "last_assistant_message": "Ship it?"}))
check("hook: last_assistant_message is used", code == 0 and out == "asks\tShip it?\n", repr(out))
code, out, _ = run(["--hook"], json.dumps({"hook_event_name": "Stop", "transcript_path": meta}))
check("hook: falls back to the transcript", code == 0 and out.startswith("asks\t"), repr(out))
code, out, _ = run(["--hook"], json.dumps({"last_assistant_message": "Done, all green."}))
check("hook: a report exits 1", code == 1 and out == "done\tDone, all green.\n", repr(out))
code, _, err = run(["--hook"], "{not json")
check("hook: bad JSON exits 2", code == 2 and "reply-ending" in err)
code, _, _ = run(["--hook"], "[1, 2]")
check("hook: non-object JSON exits 2", code == 2)
code, out, _ = run(["--hook"], json.dumps({"transcript_path": os.path.join(tmp, "missing.jsonl")}))
check("hook: missing transcript exits 2", code == 2)
code, out, _ = run(["--hook"], json.dumps({"hook_event_name": "Stop"}))
check("hook: nothing to read is a report", code == 1 and out == "done\t\n", repr(out))

# ---------------------------------------------------------------- CLI
code, _, err = run(["--hook"], "[" * 200000 + "]" * 200000)
check("hook: deeply nested JSON exits 2, no traceback", code == 2 and "Traceback" not in err, err[:120])
odd = os.path.join(tmp, "odd.jsonl")
with open(odd, "w") as fh:
    fh.write("[" * 50000 + "]" * 50000 + "\n")
    for bad in ['{"type":"assistant","message":{"content":[{"type":"text","text":null}]}}',
                '{"type":"assistant","message":"hi"}', '{"type":"assistant","message":{"content":5}}',
                '{"type":"user","message":{"content":[{"type":"text","text":5}]}}', '7', '"str"']:
        fh.write(bad + "\n")
    fh.write(entry("assistant", [{"type": "text", "text": "Ship it?"}]) + "\n")
check("transcript: odd lines are skipped, the last reply is still found", R.last_assistant_text(odd) == "Ship it?")
sub = os.path.join(tmp, "agent.jsonl")
with open(sub, "w") as fh:
    fh.write(entry("assistant", [{"type": "text", "text": "Subagent: approve the plan?"}], isSidechain=True) + "\n")
code, out, _ = run(["--hook"], json.dumps({"hook_event_name": "SubagentStop", "agent_transcript_path": sub,
                                           "transcript_path": tpath}))
check("hook: a subagent transcript is read with its sidechain entries", code == 0 and "approve the plan" in out, out)
proc = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "reply_ending.py"), "--hook"],
                      input=json.dumps({"last_assistant_message": "Скажи «да», и я выложу."}, ensure_ascii=False).encode(),
                      capture_output=True, timeout=30, env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"})
check("cli: UTF-8 in and out under a C locale", proc.returncode == 0 and "Скажи".encode() in proc.stdout,
      (proc.returncode, proc.stdout[:80], proc.stderr[:120]))

code, out, _ = run(["--json"], "Push now?")
check("cli: --json", code == 0 and json.loads(out) == {"asks": True, "kind": "question", "tail": "Push now?"}, out)
code, out, _ = run(["-q"], "Push now?")
check("cli: --quiet prints nothing", code == 0 and out == "")
mpath = os.path.join(tmp, "msg.txt")
with open(mpath, "w") as fh:
    fh.write("Все тесты зелёные.")
code, out, _ = run([mpath])
check("cli: file argument", code == 1 and out == "done\tВсе тесты зелёные.\n", repr(out))
code, _, _ = run([os.path.join(tmp, "nope.txt")])
check("cli: missing file exits 2", code == 2)
code, out, _ = run(["--transcript", tpath])
check("cli: --transcript", code == 1 and out == "done\t\n", repr(out))

proc = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "reply_ending.py"), "-q"], input="Deploy?",
                      capture_output=True, text=True, timeout=30)
check("cli: runs as a script, exit 0 on a question", proc.returncode == 0 and proc.stdout == "", proc.stderr)

# ---------------------------------------------------------------- the example hook
hook = os.path.join(ROOT, "examples", "notify-on-ask.sh")
check("example hook exists and is executable", os.access(hook, os.X_OK))
fake_bin = os.path.join(tmp, "bin")
os.makedirs(fake_bin)
record = os.path.join(tmp, "notified.txt")
for name in ("osascript", "notify-send"):
    with open(os.path.join(fake_bin, name), "w") as fh:
        fh.write(f'#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done >> "{record}"\n')
    os.chmod(os.path.join(fake_bin, name), 0o755)
env = {"PATH": os.pathsep.join([fake_bin, os.path.dirname(sys.executable), "/usr/bin", "/bin"]), "HOME": tmp}
for payload, want in [
    ({"last_assistant_message": "Tests green. Merge it?"}, True),
    ({"last_assistant_message": "Merged and deployed."}, False),
    ({"last_assistant_message": "Say «go» and I'll push $(touch pwned) `id` \"quote\" now."}, True),
]:
    if os.path.exists(record):
        os.remove(record)
    proc = subprocess.run(["/bin/sh", hook], input=json.dumps(payload), capture_output=True, text=True,
                          env=env, timeout=30)
    notified = os.path.exists(record)
    check(f"example hook: exit 0, notify={want}: {payload['last_assistant_message'][:30]}",
          proc.returncode == 0 and proc.stdout == "" and notified == want, proc.stderr)
check("example hook: shell text in the reply is not executed", not os.path.exists(os.path.join(tmp, "pwned"))
      and not os.path.exists("pwned"))
recorded = open(record).read() if os.path.exists(record) else ""
check("example hook: the tail reaches the notifier as one argument", "$(touch pwned) `id`" in recorded, recorded)

print(f"\n{PASSED} checks passed, {FAILED} failed")
sys.exit(1 if FAILED else 0)
