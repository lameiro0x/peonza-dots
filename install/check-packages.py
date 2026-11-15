#!/usr/bin/env python3
"""Check install/packages/*.txt against the official Arch repos and the hypr pin.

    python3 install/check-packages.py     exit 0 ok · 1 something to fix · 2 archlinux.org unreachable

1. Every listed package exists, by exact name, in core or extra (never the AUR, never testing).
2. HYPR_PIN in install/system-setup.sh (written to IgnorePkg) covers every official package of
   our install closure that belongs to the hypr family: it provides or links one of the hypr
   libraries, or depends by name on a package that provides one. Otherwise -Syu could upgrade
   one half of the family against the other half.
3. Every pinned name exists (a typo would silently pin nothing).

Queries https://archlinux.org/packages/search/json/?name=<pkg>, one at a time, spaced and
retried on transient errors. Answers are cached for a day in $TMPDIR/ryce-check-packages.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

HERE = pathlib.Path(__file__).resolve().parent
API = "https://archlinux.org/packages/search/json/?name="
REPOS = ("core", "extra")
SONAMES = frozenset({"libhyprutils.so", "libaquamarine.so", "libhyprlang.so", "libhyprgraphics.so",
                     "libhyprwire.so", "libhyprcursor.so", "libhyprtoolkit.so"})
NAME_RE = re.compile(r"^[a-z0-9@_+][a-z0-9@._+-]*$")
CACHE = pathlib.Path(tempfile.gettempdir()) / "ryce-check-packages"
CACHE_TTL = 24 * 3600
SPACING = 0.35      # seconds between requests to archlinux.org
TIMEOUT = 15
RETRIES = 3

Pkg = dict          # one search result: pkgname, repo, depends, provides, ...
Fetch = Callable[[str], "Pkg | None"]


class Unreachable(Exception):
    pass


def read_lists(folder: pathlib.Path) -> dict[str, str]:
    """{package: list file} from every *.txt (comments and blank lines skipped)."""
    out: dict[str, str] = {}
    for f in sorted(folder.glob("*.txt")):
        for line in f.read_text().splitlines():
            name = line.split("#", 1)[0].strip()
            if name:
                out.setdefault(name, f.name)
    return out


def read_pin(script: pathlib.Path) -> list[str]:
    """The words of the HYPR_PIN=( … ) array in system-setup.sh."""
    m = re.search(r"^HYPR_PIN=\(([^)]*)\)", script.read_text(), re.M)
    if not m:
        raise SystemExit(f"{script}: no encuentro el array HYPR_PIN=( … )")
    return [w for line in m.group(1).splitlines() for w in line.split("#", 1)[0].split()]


def dep_name(dep: str) -> str:
    return re.split(r"[<>=]", dep, maxsplit=1)[0]


def is_soname(name: str) -> bool:
    return ".so" in name


def family(pkgs: dict[str, Pkg]) -> set[str]:
    """Names among pkgs that provide or link a hypr library, directly or by package name."""
    providers = {n for n, p in pkgs.items() if SONAMES & {dep_name(x) for x in p.get("provides", [])}}
    out = set(providers)
    for n, p in pkgs.items():
        deps = {dep_name(d) for d in p.get("depends", [])}
        if deps & SONAMES or deps & providers:
            out.add(n)
    return out


def closure(roots: list[str], fetch: Fetch) -> tuple[dict[str, Pkg], set[str]]:
    """Fetch roots, then the dependencies of every family member, until nothing new appears.

    Returns (found packages, names not found in core/extra)."""
    found: dict[str, Pkg] = {}
    missing: set[str] = set()
    queue = list(dict.fromkeys(roots))
    while queue:
        for name in queue:
            pkg = fetch(name)
            if pkg is None:
                missing.add(name)
            else:
                found[name] = pkg
        seen = set(found) | missing
        queue = sorted({dep_name(d) for n in family(found) for d in found[n].get("depends", [])
                        if not is_soname(dep_name(d))} - seen)
    return found, missing


def http_fetch(name: str) -> Pkg | None:
    """The core/extra entry for exactly `name`, or None. Cached; raises Unreachable."""
    if not NAME_RE.match(name):
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{name}.json"
    if cached.exists() and time.time() - cached.stat().st_mtime < CACHE_TTL:
        results = json.loads(cached.read_text())
    else:
        results = _get(API + urllib.parse.quote(name))["results"]
        cached.write_text(json.dumps(results))
    for r in results:
        if r.get("pkgname") == name and r.get("repo") in REPOS:
            return r
    return None


_last = 0.0


def _get(url: str) -> dict:
    global _last
    for attempt in range(RETRIES + 1):
        time.sleep(max(0.0, _last + SPACING - time.monotonic()))
        _last = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ryce-pc check-packages"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == RETRIES:
                raise Unreachable(f"{url}: HTTP {e.code}") from e
            wait = float(e.headers.get("Retry-After") or 2 ** attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == RETRIES:
                raise Unreachable(f"{url}: {e}") from e
            wait = 2 ** attempt
        time.sleep(min(wait, 30))
    raise AssertionError("unreachable")


def check(lists: dict[str, str], pin: list[str], fetch: Fetch) -> list[str]:
    """Every problem as one Spanish line; empty means all good."""
    found, missing = closure(list(lists) + pin, fetch)
    problems = [f"no está en core/extra: {n} ({lists[n]})" for n in sorted(missing & set(lists))]
    problems += [f"está en HYPR_PIN pero no existe en core/extra: {n}"
                 for n in sorted(missing & set(pin) - set(lists))]
    problems += [f"enlaza la familia hypr y falta en HYPR_PIN (install/system-setup.sh): {n}"
                 for n in sorted(family(found) - set(pin))]
    return problems


def main() -> int:
    lists = read_lists(HERE / "packages")
    pin = read_pin(HERE / "system-setup.sh")
    print(f"Comprobando {len(lists)} paquetes y {len(pin)} fijados contra archlinux.org "
          f"(caché: {CACHE})…", flush=True)
    try:
        problems = check(lists, pin, http_fetch)
    except Unreachable as e:
        print(f"✗ no pude consultar archlinux.org: {e}\n  ¿Hay red? Vuelve a probar en un rato.",
              file=sys.stderr)
        return 2
    if problems:
        for p in problems:
            print(f"✗ {p}")
        return 1
    print(f"✓ los {len(lists)} paquetes están en core/extra")
    print(f"✓ HYPR_PIN cubre toda la familia hypr de la instalación ({len(pin)} paquetes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
