#!/usr/bin/env python3
"""One fake for every system command the install scripts call, dispatched on argv[0].

Tests symlink it under each command name into a directory placed first on PATH. Every call
is appended to $FAKE_STATE/calls.log; the little state each command needs (installed
packages, enabled units, subvolumes, group members) lives in $FAKE_STATE as one JSON file,
so a second run of a script sees what the first one did.

Knobs: FAKE_CRYPT=1 (/ on dm-crypt), FAKE_HOME (home of every user), FAKE_FSTYPE (default
btrfs), FAKE_INSTALLED (space-separated packages already installed).
"""
import json
import os
import pathlib
import sys

STATE = pathlib.Path(os.environ["FAKE_STATE"])
DB = STATE / "state.json"


def load():
    if DB.exists():
        return json.loads(DB.read_text())
    return {"installed": os.environ.get("FAKE_INSTALLED", "").split(), "enabled": [],
            "active": [], "subvols": [], "groups": {}}


def save(st):
    DB.write_text(json.dumps(st))


def pacman(args, st):
    if args[:1] == ["-T"]:
        missing = [a for a in args[1:] if a != "--" and a not in st["installed"]]
        print("\n".join(missing))
        return 127 if missing else 0
    if args[:1] == ["-Q"]:
        return 0 if all(a in st["installed"] for a in args[1:]) else 1
    if args and args[0].startswith("-S"):
        st["installed"] += [a for a in args if not a.startswith("-")]
        return 0
    return 0


def systemctl(args, st):
    args = [a for a in args if a not in ("--quiet", "--user")]
    verb, units = args[0], args[1:]
    if verb == "is-enabled":
        on = units[0] in st["enabled"]
        print("enabled" if on else "disabled")
        return 0 if on else 1
    if verb == "is-active":
        return 0 if units[0] in st["active"] else 3
    if verb == "enable":
        now = "--now" in units
        for u in (u for u in units if u != "--now"):
            st["enabled"].append(u)
            if now:
                st["active"].append(u)
    if verb == "start":
        st["active"] += units
    return 0


def btrfs(args, st):
    if args[:2] == ["subvolume", "show"]:
        return 0 if args[2] in st["subvols"] else 1
    if args[:2] == ["subvolume", "create"]:
        os.mkdir(args[2])
        st["subvols"].append(args[2])
    return 0


def findmnt(args, st):
    if "SOURCE" in args:
        print("/dev/mapper/root[/@]" if os.environ.get("FAKE_CRYPT") == "1" else "/dev/nvme0n1p2[/@]")
    else:
        print(os.environ.get("FAKE_FSTYPE", "btrfs"))
    return 0


def lsblk(args, st):
    print("crypt\npart\ndisk" if os.environ.get("FAKE_CRYPT") == "1" else "part\ndisk")
    return 0


def getent(args, st):
    db, key = args[0], args[1]
    if db == "passwd":
        print(f"{key}:x:1000:1000::{os.environ['FAKE_HOME']}:/bin/bash")
        return 0
    members = st["groups"].get(key, [])
    print(f"{key}:x:900:{','.join(members)}")
    return 0


def usermod(args, st):
    groups, user = args[args.index("-aG") + 1], args[-1]
    for g in groups.split(","):
        st["groups"].setdefault(g, []).append(user)
    return 0


def runuser(args, st):
    if any(a.endswith("xdg-user-dirs-update") for a in args):
        home = next(a.split("=", 1)[1] for a in args if a.startswith("HOME="))
        cfg = pathlib.Path(home, ".config")
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "user-dirs.dirs").write_text('XDG_PICTURES_DIR="$HOME/Pictures"\n')
    return 0


def virsh(args, st):
    if "net-autostart" in args:
        root = os.environ.get("RYCE_ROOT", "")
        d = pathlib.Path(root + "/etc/libvirt/qemu/networks/autostart")
        d.mkdir(parents=True, exist_ok=True)
        (d / "default.xml").write_text("")
    return 0


def nft(args, st):
    if args[:1] == ["list"]:
        return 0 if st.get("nft") else 1
    if args[:1] == ["-f"]:
        st["nft"] = True
    return 0


def systemd_run(args, st):
    cmd = args[args.index("--") + 1:]
    os.execvp(cmd[0], cmd)


def silent(args, st):
    return 0


def main():
    name = os.path.basename(sys.argv[0]).replace("-", "_")
    args = sys.argv[1:]
    STATE.mkdir(parents=True, exist_ok=True)
    with open(STATE / "calls.log", "a") as log:
        log.write(" ".join([os.path.basename(sys.argv[0])] + args) + "\n")
    st = load()
    rc = globals().get(name, silent)(args, st)
    save(st)
    sys.exit(rc)


if __name__ == "__main__":
    main()
