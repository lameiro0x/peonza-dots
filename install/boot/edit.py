#!/usr/bin/env python3
"""Line edits of the boot configs for install/boot-setup.sh. Each prints the whole new file on
stdout and leaves every other line byte for byte; a shape it does not recognise is an error
(exit 2, Spanish message on stderr) so the caller stops before writing anything.

    edit.py hooks FILE add|drop      mkinitcpio.conf: plymouth into HOOKS right after kms, or out
    edit.py resume FILE add|drop     mkinitcpio.conf: resume into HOOKS right before filesystems
                                    (so after encrypt), or out (install/power-setup.sh)
    edit.py kv FILE KEY VALUE        shell-style KEY=VALUE (default/grub): set, or add after #KEY=
    edit.py word FILE KEY WORD       KEY="a b" gains WORD once (the kernel command line)
    edit.py preset FILE CONFIG       mkinitcpio preset: every image built from CONFIG
    edit.py greeter FILE COMMAND     greetd config.toml: [default_session] command, and no
                                    [initial_session] (with the comments just above it)
"""
from __future__ import annotations

import json
import re
import sys

HOOKS = re.compile(r"^(\s*HOOKS=\()([^)]*)(\).*)$")


class Shape(Exception):
    pass


def hooks(lines: list[str], mode: str) -> list[str]:
    found = [i for i, line in enumerate(lines) if HOOKS.match(line)]
    if len(found) != 1:
        if any(re.match(r"^\s*HOOKS=\([^)]*$", line) for line in lines):
            raise Shape("HOOKS ocupa varias líneas: déjalo en una sola, HOOKS=(...)")
        raise Shape(f"espero una sola línea HOOKS=(...) sin comentar y hay {len(found)}")
    i = found[0]
    head, body, tail = HOOKS.match(lines[i]).groups()
    names = body.split()
    if mode == "drop":
        names = [n for n in names if n != "plymouth"]
    elif "plymouth" not in names:
        # ArchWiki, Plymouth: after kms (the GPU driver is in the image) and before the encrypt
        # hook, which then asks for the passphrase through plymouth itself.
        anchor = next((a for a in ("kms", "udev", "systemd") if a in names), None)
        if anchor is None:
            raise Shape("HOOKS no tiene kms, udev ni systemd: no sé dónde poner plymouth")
        at = names.index(anchor) + 1
        for crypt in ("encrypt", "sd-encrypt"):
            if crypt in names and names.index(crypt) < at:
                raise Shape(f"{crypt} va antes que {anchor} en HOOKS: plymouth no puede pedir la contraseña")
        names.insert(at, "plymouth")
    lines[i] = head + " ".join(names) + tail
    return lines


def resume(lines: list[str], mode: str) -> list[str]:
    """The busybox `resume` hook: it reads resume= and resume_offset= and must run once the
    swap's device exists, i.e. after encrypt (and lvm2), before filesystems mounts root."""
    found = [(i, m) for i, line in enumerate(lines) if (m := HOOKS.match(line))]
    if len(found) != 1:
        raise Shape(f"espero una sola línea HOOKS=(...) sin comentar y hay {len(found)}")
    i, m = found[0]
    head, body, tail = m.groups()
    names = [n for n in body.split() if n != "resume"]
    if mode == "add":
        if "systemd" in names:
            raise Shape("initramfs con systemd: reanuda solo, el hook resume no va ahí")
        if "filesystems" not in names:
            raise Shape("HOOKS no tiene filesystems: no sé dónde poner resume")
        at = names.index("filesystems")
        for need in ("encrypt", "lvm2", "block"):
            if need in names and names.index(need) > at:
                raise Shape(f"{need} va después de filesystems en HOOKS: arréglalo antes")
        names.insert(at, "resume")
    elif mode != "drop":
        raise Shape(f"resume: add o drop, no {mode}")
    lines[i] = head + " ".join(names) + tail
    return lines


def kv(lines: list[str], key: str, value: str) -> list[str]:
    active = re.compile(rf"^\s*{re.escape(key)}=")
    commented = re.compile(rf"^\s*#\s*{re.escape(key)}=")
    out, done = [], False
    for line in lines:
        if active.match(line):
            if not done:
                out.append(f"{key}={value}")
                done = True
            continue  # a later duplicate would win in the shell: drop it
        out.append(line)
    if not done:
        at = next((i + 1 for i, line in enumerate(out) if commented.match(line)), None)
        if at is None:
            at = len(out) - 1 if out and out[-1] == "" else len(out)
        out.insert(at, f"{key}={value}")
    return out


def word(lines: list[str], key: str, w: str) -> list[str]:
    pat = re.compile(rf'^(\s*{re.escape(key)}=)(["\'])(.*)\2\s*$')
    for i, line in enumerate(lines):
        if re.match(rf"^\s*{re.escape(key)}=", line):
            m = pat.match(line)
            if not m:
                raise Shape(f"{key} no está entre comillas: edítalo a mano")
            if w not in m.group(3).split():
                value = f"{m.group(3)} {w}".strip()
                lines[i] = f"{m.group(1)}{m.group(2)}{value}{m.group(2)}"
            return lines
    return kv(lines, key, f'"{w}"')


def preset(lines: list[str], config: str) -> list[str]:
    # <preset>_config= overrides ALL_config for that image: comment it out.
    lines = [("#" + line) if re.match(r"^\s*(?!ALL_)\w+_config=", line) else line for line in lines]
    return kv(lines, "ALL_config", f'"{config}"')


def greeter(lines: list[str], command: str) -> list[str]:
    section, done, out = None, False, []
    for line in lines:
        m = re.match(r"^\s*\[([^\]]+)\]\s*$", line)
        if m:
            if section == "initial_session" and out and out[-1] != "":
                out.append("")   # the section after the dropped one keeps its blank line
            section = m.group(1).strip()
            if section == "initial_session":
                # An autologin would skip the login page: the section goes, and so do the
                # comment and blank lines that introduce it.
                while out and (out[-1].strip() == "" or out[-1].lstrip().startswith("#")):
                    out.pop()
                continue
        if section == "initial_session":
            continue
        if section == "default_session" and not done and re.match(r"^\s*command\s*=", line):
            line, done = f"command = {json.dumps(command)}", True
        out.append(line)
    if not done:
        raise Shape("config.toml no tiene [default_session] con command: ejecuta antes install/system-setup.sh")
    if lines and lines[-1] == "" and (not out or out[-1] != ""):
        out.append("")   # the file still ends with its newline
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        sys.exit(__doc__)
    verb, path, rest = argv[0], argv[1], argv[2:]
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    edits = {"hooks": hooks, "resume": resume, "kv": kv, "word": word, "preset": preset,
             "greeter": greeter}
    if verb not in edits:
        sys.exit(f"edit.py: orden desconocida {verb}")
    try:
        lines = edits[verb](lines, *rest)
    except Shape as e:
        print(f"{path}: {e}", file=sys.stderr)
        return 2
    sys.stdout.write("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
