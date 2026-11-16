# reply-ending

**Tell whether a coding agent's last message asks you for something or only reports, and get the one sentence that is the next step.**

A Claude Code turn ends one of two ways. The work is done, or the agent is waiting on you: a yes, a choice, a
click in a browser, a command only you can run. A notification on every stop gets ignored by the second day, so I
wanted one only for the second kind.

The obvious test is a question mark. A hook in [iMUngHee's dotfiles](https://github.com/iMUngHee/dotfiles) uses it
to title its notification "Review needed" when the reply's last line ends with "?". In my own sessions that test
almost never fires, because the request has no question mark: «Скажи «да», и я выложу», "Run `npm test` and tell
me what fails", "Waiting on your approval to deploy". Of 35 asks in the first sample I read, zero ended with "?".

I labelled final messages by hand and ran three rules on them: "ends with ?", the rule from OpenDuet that this tool
grew out of (a question anywhere in the last paragraph, lists and drafts set aside), and reply-ending.

| asks found | Russian, my sessions | English, public sessions |
|---|---|---|
| messages, of them asking | 100, 42 | 59, 32 |
| ends with "?" | 3 | 8 |
| OpenDuet's rule | 3 | 10 |
| reply-ending, blind run | 35, no false alarms | 27, 1 false alarm |
| reply-ending, current | 38, no false alarms | 30, no false alarms |

The blind row is the only out-of-sample number here. I labelled those messages before the tool ever ran on them;
the rules had been written on a different 230 Russian and 59 English messages. The false alarm was "Commit
`f479ad3` is now on main", with "Commit" read as a verb. After that I fixed what the misses had in common and what
an independent review found, so the current row, like every other number below, is on messages I had already seen.
Over all 448 labelled messages the current version finds 167 of 181 asks and raises no false alarm; "ends with ?"
finds 23.

The Russian messages are a random sample of 5,941 turn endings from three months of my own Claude Code sessions,
one per session, and the Russian sets share no session. The English ones are 118 messages from 34 public
repositories that commit their Claude Code sessions to `.specstory/history`. The English blind set is blind per
message only: its messages come from the same repositories, mostly the same session files, as the English messages
I developed on. About a third of the turns I labelled end with a request. An independent reviewer, a separate AI agent that
never saw my labels, re-labelled 30 of the blind messages and agreed on all 30.

What counts as asking: the ending puts something to the reader. A question, or a request to decide, approve,
answer, check or do something, including conditional ones ("if you want the second variant, say «two»") and
"I'll push once you say the word". A usage hint ("run `npm start` to try it") counts too, because it hands you
the next step. Reports, the agent's own next steps, "I can also add a Dockerfile" and a courtesy line at the end
(`let me know if you have any questions`) do not.

## Usage

```bash
python3 reply_ending.py message.txt          # or the text on stdin
python3 reply_ending.py --transcript ~/.claude/projects/<project>/<session>.jsonl
python3 reply_ending.py --hook < payload.json # a Claude Code Stop hook payload
```

Python 3.8+, one file, standard library only. It prints `asks` or `done`, a tab and the sentence:

```
asks	Tests are green. Merge it?
done	Deployed at 10:02, the health check passes.
```

`--json` prints `{"asks": true, "kind": "question", "tail": "..."}`, `-q` prints nothing. The exit code is 0 when
the message asks, 1 when it only reports and 2 when the input can't be read, the way `grep` does it, so a shell
`if` can branch on it. Input and output are UTF-8 whatever the locale says.

With `--hook` it reads `last_assistant_message` from the payload and falls back to the transcript only when that
field is missing. Claude Code's documentation says the transcript file may not hold the final message yet when the
Stop hook fires.

## A notification only when it asks

[`examples/notify-on-ask.sh`](examples/notify-on-ask.sh) is a Stop hook. Add it to `.claude/settings.json` in a
project or to `~/.claude/settings.json`:

```json
{"hooks": {"Stop": [{"hooks": [{"type": "command",
  "command": "/absolute/path/to/reply-ending/examples/notify-on-ask.sh"}]}]}}
```

It shows a desktop notification with the asking sentence through `osascript` on macOS or `notify-send` on Linux,
and stays silent when the reply only reports. It prints nothing to stdout and always exits 0, so it can't block
Claude or loop. The sentence goes to the notifier as a separate argument, never inside a shell or AppleScript
string, so a reply with `$(...)` in it is shown and not run. It needs `python3` on the PATH; on a Mac without the
Command Line Tools, Apple's `python3` stub would offer to install them on every stop.

## How it decides

1. It sets aside what the agent prepared rather than said: code blocks, tables, block quotes, a paragraph that is
   one quotation or opens a letter ("To:", "Draft:", "Dear"), a closing "Sources:" list, bare links.
2. It takes the last paragraph left. A list after that paragraph counts only when its last item asks you to do
   something, or when the paragraph or a heading above the list announces questions ("Two questions:", "## Open
   questions"). A message that is only a list is judged by its last item.
3. In that paragraph the last sentence that is a question or a request wins. A question ends with "?" once quotes,
   brackets, markdown and emoji are set aside, and is more than a courtesy line ("Anything else?"). A request is a
   Russian imperative from a list of 196 verbs (скажи, напиши, нажми, пришли...), an English clause that opens with
   one of 99 verbs ("Run...", "Confirm..."; not "You can run...", and not "Deploy succeeded", where the verb is a
   noun), or a phrase that hands the decision over: «жду твоего ответа», «решение за тобой», «если скажешь «чини»»,
   "waiting on your approval", "your call", "let me know which". «От тебя ничего не нужно» and "no action needed"
   cancel it; courtesy phrases are cut out first, so "feel free to say no, but should I deploy?" still asks.
4. The printed sentence is that one. A sentence shorter than 20 characters keeps the one before it, so "Merge it?"
   comes with its reason. It's cut at 240 characters, with control characters removed. Of a message over 50,000
   characters only the end is read.

## What it does not catch

- **Asks written as plain facts.** «Осталось одно: проверить, что строка дошла», "Worth doing one real test
  dictation", "the app has to be open by 2:15". Eight of the 14 asks it still misses are like this, and I had
  marked all eight as borderline while labelling.
- **An ask above the last paragraph.** "Want me to push?" followed by a paragraph of notes reads as a report. So
  does a list of questions with a remark under it, or a last line that only points back at a question asked
  earlier. Three misses.
- **Asks without a verb**, such as an answer template («Ответ: «да» или «нет»»), and usage hints in odd shapes
  ("Just include the header and call `begin()`").
- **«Решаешь ты».** It is a request in «Решаешь ты: архивировать или нет», and a statement in «цены решаешь ты, как
  и раньше». The tool leaves both alone.
- **False alarms are possible**, though none happened in the labelled sets after the fixes. A report line that
  opens with a word that is also a verb ("Open issues: three", "Review: posted") is read with a few rules (a
  following "is", "succeeded", "complete", a label with a short value) and those rules don't cover every phrasing.
- **Verbs outside its lists** and languages other than Russian and English.
- **A draft for someone else that isn't marked as one.** A reply to a client written as plain paragraphs, with its
  own question at the end, reads as a question to you.
- **The labels are mine.** Another reader would mark some of the borderline endings the other way.

## Prior art

Notification hooks for Claude Code are everywhere: [claude-code-ntfy](https://github.com/joshsymonds/claude-code-ntfy),
[claude-code-notify-powershell](https://github.com/soulee-dev/claude-code-notify-powershell),
[Claude-Code-Notify-Hub](https://github.com/knightnemo/Claude-Code-Notify-Hub) and dozens more. The ones I read
fire on every Stop, on Claude Code's own Notification event (a permission prompt, or a minute of silence after a
reply), or when Claude calls its question tool. Some put the reply's text into the notification. The only one I
found that reads the text is the dotfiles hook above: it notifies on every stop and uses the question mark to pick
the title, which is the "ends with ?" row in the table.

The idea comes from `replyEnding()` in [CopilotKit/OpenDuet](https://github.com/CopilotKit/OpenDuet) (MIT,
`openbot/server/src/proactive/engine.ts`): set lists and drafts aside, take the last paragraph, find its question,
keep a short closing sentence together with the one before it. The cases from its tests pass here too. This code is
written from scratch; Russian, requests without a question mark and the measurement are mine.

## Tests

```bash
python3 tests/test_reply_ending.py
```

180 checks on made-up messages, with the network blocked; they also run the example hook against a fake notifier
and feed the tool hostile inputs (200 KB of brackets, deeply nested JSON). The labelled messages are not in this
repository, only the counts above.

MIT. Aleksandr Shulgin ([@Aleksandr_NFA](https://t.me/Aleksandr_NFA)).
