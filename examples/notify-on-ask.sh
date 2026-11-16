#!/bin/sh
# Claude Code Stop hook: a desktop notification only when the reply ends by asking you something.
#
# Add to .claude/settings.json (one project) or ~/.claude/settings.json (everywhere):
#   {"hooks": {"Stop": [{"hooks": [{"type": "command",
#       "command": "/absolute/path/to/reply-ending/examples/notify-on-ask.sh"}]}]}}
#
# It never blocks Claude: it prints nothing to stdout and always exits 0.
# The reply's last sentence goes to the notifier as one argument, never through a shell or AppleScript string.

here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
line=$(python3 "$here/reply_ending.py" --hook) || exit 0   # 1 = it only reports, 2 = unreadable input
tail=$(printf '%s' "$line" | cut -f2-)
title="Claude is waiting for you"

if command -v osascript >/dev/null 2>&1; then
  osascript -e 'on run argv' -e "display notification (item 2 of argv) with title (item 1 of argv)" \
    -e 'end run' "$title" "$tail" >/dev/null 2>&1
elif command -v notify-send >/dev/null 2>&1; then
  notify-send -- "$title" "$tail" >/dev/null 2>&1
fi
exit 0
