#!/usr/bin/env python3
"""Root's private copy of repo files for install/boot-setup.sh and install/system-setup.sh:
the only copy they install. Run as root with python3 -I.

    stage.py REPO DEST SPEC...

    REPO   the repo's physical path (pwd -P)
    DEST   a new folder (made here, mode 0700) inside the caller's own temp folder
    SPEC   repo-relative, or absolute under REPO:
             dir/file        -> DEST/file
             dir/*.ext       -> DEST/<each match> (only the last part may hold * ? [ ];
                                dot files only when the pattern starts with a dot)
             dir/folder/     -> DEST/folder/<each file in it> (not recursive)

The agents' sandbox can write parts of the repo, and a path is only a name: between a check and
a copy, any folder on the way can become a link (to /etc, to ~/.ssh). So nothing is opened by
path. The repo is opened once; every further part is opened relative to the folder before it
with O_NOFOLLOW, and each file is copied from the descriptor that was checked: a regular file
(no link, FIFO, device or socket), one name only (no hard link to a file elsewhere), owned by
the repo's owner, at most 64 MiB (512 MiB in all). Run as root on a repo that is not root's,
every open happens with the repo owner's uid and gid, so even a hole in this walk could not
read what only root can. Anything refused stops the whole copy: exit 1 with the reason in
Spanish on stderr, DEST left behind for the caller's temp cleanup. Exit 2: usage.
"""
from __future__ import annotations

import contextlib
import fnmatch
import os
import stat
import sys
from collections.abc import Iterator

MAX_FILE = 64 << 20
MAX_TOTAL = 512 << 20
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY | os.O_CLOEXEC
FIX = "como root no lo copio (quítalo y repite)"


class Refused(Exception):
    pass


@contextlib.contextmanager
def as_owner(uid: int, gid: int) -> Iterator[None]:
    """The repo owner's rights for the opens; root's back for the writes into DEST."""
    if os.geteuid() != 0 or uid == 0:
        yield
        return
    os.setgroups([])   # root's own groups (root, wheel…) would still open their files
    os.setegid(gid)
    os.seteuid(uid)
    try:
        yield
    finally:
        os.seteuid(0)
        os.setegid(0)


def parts_of(repo: str, spec: str) -> list[str]:
    if spec.startswith("/"):
        if not spec.startswith(repo + "/"):
            raise Refused(f"{spec}: fuera del repo {repo}")
        spec = spec[len(repo) + 1:]
    parts = spec.rstrip("/").split("/")
    if not spec or any(p in ("", ".", "..") for p in parts):
        raise Refused(f"{spec}: ruta no válida (sin '.', '..' ni '//')")
    return parts


def open_dir(top: int, parts: list[str], spec: str) -> int:
    """The folder PARTS below TOP, every step without following a link."""
    fd = os.dup(top)
    try:
        for part in parts:
            try:
                nxt = os.open(part, DIR_FLAGS, dir_fd=fd)
            except OSError as e:
                raise Refused(f"{spec}: «{part}» no es una carpeta normal del repo ({e.strerror}): {FIX}") from None
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_file(dfd: int, name: str, spec: str, owner: int) -> tuple[int, os.stat_result]:
    try:
        fd = os.open(name, FILE_FLAGS, dir_fd=dfd)
    except OSError as e:
        raise Refused(f"{spec}: «{name}» no se puede abrir sin seguir enlaces ({e.strerror}): {FIX}") from None
    st = os.fstat(fd)
    why = None
    if not stat.S_ISREG(st.st_mode):
        why = "no es un fichero normal"
    elif st.st_nlink != 1:
        why = f"tiene {st.st_nlink} nombres (un enlace duro a otro fichero)"
    elif st.st_uid != owner:
        why = f"es del usuario {st.st_uid}, no del dueño del repo ({owner})"
    elif st.st_size > MAX_FILE:
        why = f"pasa de {MAX_FILE >> 20} MiB"
    if why:
        os.close(fd)
        raise Refused(f"{spec}: «{name}» {why}: {FIX}")
    return fd, st


def collect(top: int, spec: str, parts: list[str], owner: int) -> tuple[str, list[tuple[str, int]]]:
    """(subfolder of DEST or "", [(name, open fd)]) for one SPEC."""
    folder = spec.endswith("/")
    leaf = parts[-1]
    pattern = not folder and any(c in leaf for c in "*?[")
    dfd = open_dir(top, parts if folder else parts[:-1], spec)
    opened: list[tuple[str, int]] = []
    try:
        if folder or pattern:
            names = sorted(os.listdir(dfd))
            if pattern:
                names = [n for n in names if fnmatch.fnmatchcase(n, leaf)
                         and (leaf.startswith(".") or not n.startswith("."))]
            if not names:
                raise Refused(f"{spec}: no hay ningún fichero así en el repo")
        else:
            names = [leaf]
        for name in names:
            fd, _ = open_file(dfd, name, spec, owner)
            opened.append((name, fd))
        return (leaf if folder else ""), opened
    except BaseException:
        for _, fd in opened:
            os.close(fd)
        raise
    finally:
        os.close(dfd)


def copy(src: int, dst: int, budget: int, label: str) -> int:
    """Copy SRC into DST from the open descriptors; the bytes copied."""
    done = 0
    while chunk := os.read(src, 1 << 20):
        done += len(chunk)
        if done > MAX_FILE or done > budget:
            raise Refused(f"{label}: pasa del tamaño máximo mientras se copia (¿crece?): {FIX}")
        view = memoryview(chunk)
        while view:
            view = view[os.write(dst, view):]
    return done


def stage(repo: str, dest: str, specs: list[str]) -> None:
    if os.path.realpath(repo) != repo:
        raise Refused(f"{repo}: no es la ruta física del repo (usa pwd -P)")
    top = os.open(repo, DIR_FLAGS)
    try:
        st = os.fstat(top)
        owner, group = st.st_uid, st.st_gid
        os.mkdir(dest, 0o700)
        os.chmod(dest, 0o700)
        out = os.open(dest, DIR_FLAGS)
        try:
            seen: set[str] = set()
            budget = MAX_TOTAL
            for spec in specs:
                parts = parts_of(repo, spec)
                rel = "/".join(parts) + ("/" if spec.endswith("/") else "")
                with as_owner(owner, group):
                    sub, files = collect(top, rel, parts, owner)
                try:
                    target = out
                    if sub:
                        os.mkdir(sub, 0o700, dir_fd=out)
                        target = os.open(sub, DIR_FLAGS, dir_fd=out)
                    try:
                        for name, fd in files:
                            key = f"{sub}/{name}"
                            if key in seen:
                                raise Refused(f"{rel}: «{name}» ya está en la copia (dos fuentes con el mismo nombre)")
                            seen.add(key)
                            dst = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                          0o644, dir_fd=target)
                            try:
                                budget -= copy(fd, dst, budget, f"{rel}: «{name}»")
                            finally:
                                os.close(dst)
                    finally:
                        if target != out:
                            os.close(target)
                finally:
                    for _, fd in files:
                        os.close(fd)
        finally:
            os.close(out)
    finally:
        os.close(top)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        stage(argv[0], argv[1], argv[2:])
    except Refused as e:
        print(f"stage.py: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"stage.py: {e.filename or argv[1]}: {e.strerror}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
