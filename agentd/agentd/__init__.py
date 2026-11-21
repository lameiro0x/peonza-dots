"""agentd — what each Hyprland workspace is doing, and which AI session waits for you.

Successor of dotsArch's wsctx-daemon.py. Reads Hyprland (socket IPC), /proc and
Claude Code's session files and transcript tails; publishes pre-rendered Waybar
slots, roster.json for the Quickshell sidebar and lock.txt for hyprlock under
$XDG_RUNTIME_DIR/agentd, and keeps the `agentwait` tag on exactly the windows of
waiting sessions. While a session works it also holds a logind idle inhibitor, so
the screen neither locks nor turns off (awake.py). Python stdlib only; run as
`python3 -m agentd`.

Every side is a seam with a fake: hypr.Hypr (RealHypr / FakeHypr), procfs.Proc
(root), claude.ClaudeHome (root). model, render and the transcript parsers are
pure functions, which is what the tests lean on.
"""
