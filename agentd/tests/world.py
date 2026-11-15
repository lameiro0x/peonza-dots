"""Synthetic worlds for the agentd tests: a fake Hyprland, /proc and ~/.claude.

Everything here is invented. The shapes follow Hyprland 0.57.1 JSON and Claude
Code 2.1.319 session files and transcripts (field names checked against a live
machine); the strings, ids and paths do not come from any real session.

    python3 agentd/tests/world.py --write-stage   regenerate fixtures/stage and stage8
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

NOW = 1794220000.0
# Lives only where agentd must never look: last-prompt, queue-operation, user
# records that are not prompts, a prompt past its first sentence, notification
# summaries and results, tool output, history.jsonl. It must appear in no output, ever.
MARKER = "PRIVACY-MARKER-7f3a-never-render-me"
STAGE = Path(__file__).resolve().parent / "fixtures" / "stage"
STAGE8 = STAGE.with_name("stage8")
HOME = "/home/lameiro0x"


def sid(n: int) -> str:
    return f"0b6f3f7e-{n:04d}-4c1a-9a51-0f7a9e1c{n:04d}"


def slug(cwd: str) -> str:
    return "".join(c if c.isalnum() and c.isascii() else "-" for c in cwd)


# ── transcript records ──────────────────────────────────────────────────────

def _base(kind: str, side: bool = False) -> dict:
    return {"parentUuid": "00000000-0000-0000-0000-000000000000", "isSidechain": side,
            "type": kind, "uuid": "11111111-1111-1111-1111-111111111111",
            "timestamp": "2026-11-09T10:00:00.000Z", "userType": "external",
            "entrypoint": "cli", "version": "2.1.319", "gitBranch": "main"}


def ai_title(t: str) -> dict:
    return {"type": "ai-title", "aiTitle": t, "sessionId": "x"}


def text(t: str, side: bool = False) -> dict:
    r = _base("assistant", side)
    r["message"] = {"role": "assistant", "model": "claude-opus-5-5",
                    "content": [{"type": "text", "text": t}]}
    return r


def tool(name: str, desc: str | None = None, side: bool = False, tid: str = "toolu_01",
         at: str | None = None, **inp) -> dict:
    """A tool_use; extra keywords go into its input (run_in_background=True)."""
    r = _base("assistant", side)
    inp = {"command": "true", **inp}
    if desc is not None:
        inp["description"] = desc
    if at:
        r["timestamp"] = at
    r["message"] = {"role": "assistant", "model": "claude-opus-5-5",
                    "content": [{"type": "tool_use", "id": tid, "name": name,
                                 "input": inp, "caller": {"type": "direct"}}]}
    return r


def human(content, side: bool = False) -> dict:
    """A prompt the user typed (2.1.325: origin.kind == "human")."""
    r = _base("user", side)
    r.update(origin={"kind": "human"}, promptId="p1")
    r["message"] = {"role": "user", "content": content}
    return r


def note(tool_use: str, status: str | None, task: str = "b0000001") -> dict:
    """A task notification; its summary and result carry the privacy marker."""
    r = _base("user")
    r["origin"] = {"kind": "task-notification", "producer": "session-task", "runId": "r1"}
    body = (f"<task-notification>\n<task-id>{task}</task-id>\n<tool-use-id>{tool_use}</tool-use-id>\n"
            f"<output-file>/tmp/x/{task}.output</output-file>\n"
            + (f"<status>{status}</status>\n" if status else "")
            + f"<summary>{MARKER}</summary>\n<result>{MARKER}</result>\n</task-notification>")
    r["message"] = {"role": "user", "content": body}
    return r


def queued(tool_use: str, status: str | None, task: str = "b0000001") -> dict:
    """The same notification queued as an attachment (2.1.316+: about half of them)."""
    r = _base("attachment")
    r["attachment"] = {"type": "queued_command", "commandMode": "task-notification",
                       "prompt": note(tool_use, status, task)["message"]["content"],
                       "origin": {"kind": "task-notification"}, "delivery_id": "d1",
                       "source_uuid": "s1", "timestamp": "2026-11-09T10:00:00.000Z"}
    return r


def ack(tool_use: str, **result) -> dict:
    """The tool_result of a background launch (backgroundTaskId=… or agentId=…, isAsync=True)."""
    r = _base("user")
    r["message"] = {"role": "user", "content": [
        {"tool_use_id": tool_use, "type": "tool_result", "content": f"launched {MARKER}"}]}
    r["toolUseResult"] = {"stdout": MARKER, **result}
    return r


def turn_end() -> dict:
    r = _base("system")
    r.update(subtype="turn_duration", durationMs=104000, messageCount=12,
             pendingBackgroundAgentCount=0, isMeta=False)
    return r


def away(t: str) -> dict:
    r = _base("system")
    r.update(subtype="away_summary", content=t, isMeta=False)
    return r


def secrets() -> list[dict]:
    """The three record kinds that carry the user's own words."""
    user = _base("user")
    user["message"] = {"role": "user", "content": MARKER}
    return [{"type": "last-prompt", "lastPrompt": MARKER, "leafUuid": "x", "sessionId": "x"},
            {"type": "queue-operation", "operation": "enqueue", "content": MARKER,
             "timestamp": "2026-11-09T10:00:00.000Z", "sessionId": "x"},
            user]


def blob(nbytes: int) -> dict:
    """An api-request-blob padded to about nbytes on one line."""
    return {"type": "api-request-blob", "sessionId": "x", "hash": "h",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "x" * nbytes}]}}


# ── the builder ─────────────────────────────────────────────────────────────

class World:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.clients: list[dict] = []
        self.monitors: list[dict] = []
        self.workspaces: list[dict] = []
        self.rules: list[dict] = []
        for d in ("hypr", "proc", "claude/sessions", "claude/projects", "fs"):
            (self.root / d).mkdir(parents=True, exist_ok=True)

    # /proc
    def proc(self, pid: int, comm: str, ppid: int = 1, children=(), pgrp: int | None = None,
             tpgid: int = -1, start: int | None = None, cwd: str | None = None, argv=()) -> int:
        d = self.root / "proc" / str(pid)
        (d / "task" / str(pid)).mkdir(parents=True, exist_ok=True)
        pgrp = pid if pgrp is None else pgrp
        start = 4000 + pid if start is None else start
        # fields 1..22: pid (comm) state ppid pgrp session tty_nr tpgid flags
        # minflt cminflt majflt cmajflt utime stime cutime cstime priority nice
        # num_threads itrealvalue starttime, then the tail of the real line.
        (d / "stat").write_text(
            f"{pid} ({comm}) S {ppid} {pgrp} {pgrp} 34816 {tpgid} 4194304 "
            f"100 0 0 0 5 2 0 0 20 0 1 0 {start} 10000 200 18446744073709551615\n")
        (d / "comm").write_text(comm + "\n")
        if argv:
            (d / "cmdline").write_text("".join(f"{a}\0" for a in argv))
        (d / "task" / str(pid) / "children").write_text("".join(f"{c} " for c in children))
        if cwd:
            os.symlink(cwd, d / "cwd")
        return pid

    def terminal(self, base: int, cwd: str, fg: str | None = None, bg: str | None = None,
                 cls: str = "kitty") -> int:
        """kitty(base) → kitten(base+1) → fish(base+2) → fg(base+3) / bg(base+4)."""
        kids = [k for k, c in ((base + 3, fg), (base + 4, bg)) if c]
        self.proc(base, cls, children=[base + 1], cwd=HOME)
        self.proc(base + 1, "kitten", base, children=[base + 2], cwd=HOME)
        fish_tpgid = base + 3 if fg else base + 2
        self.proc(base + 2, "fish", base + 1, children=kids, tpgid=fish_tpgid, cwd=cwd)
        if fg:
            self.proc(base + 3, fg, base + 2, tpgid=base + 3, cwd=cwd)
        if bg:
            self.proc(base + 4, bg, base + 2, tpgid=base + 2, cwd=cwd)
        return base

    # ~/.claude
    def session(self, pid: int, n: int, cwd: str, status: str | None, ago: float | None = 100,
                raw: str | None = None, start: int | None = None, **extra) -> None:
        f = self.root / "claude" / "sessions" / f"{pid}.json"
        if raw is not None:
            f.write_text(raw)
            return
        d = {"pid": pid, "sessionId": sid(n), "cwd": cwd, "startedAt": int((NOW - 9000) * 1000),
             "procStart": str(4000 + pid if start is None else start), "version": "2.1.319",
             "peerProtocol": 1, "peerFeatures": ["notify_idle"], "kind": "interactive",
             "entrypoint": "cli", "pidDomain": "linux", "messagingSocketPath": f"/run/user/1000/cc-socks/{pid}.sock",
             "name": "auto-derived-slug", "nameSource": "derived", "nameSince": 0,
             "status": status, "updatedAt": int(NOW * 1000)}
        if ago is not None:
            d["statusUpdatedAt"] = int((NOW - ago) * 1000)
        d.update(extra)
        d = {k: v for k, v in d.items() if v is not ...}
        f.write_text(json.dumps(d))

    def transcript(self, n: int, cwd: str, records: list) -> Path:
        d = self.root / "claude" / "projects" / slug(cwd)
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{sid(n)}.jsonl"
        with f.open("w") as fh:
            for r in records:
                fh.write((r if isinstance(r, str) else json.dumps(r, ensure_ascii=False, separators=(",", ":"))) + "\n")
        return f

    def subagent(self, n: int, cwd: str, name: str, mtime: float, finished: bool = False,
                 kind: str = "Explore", desc: str = "Buscar el código", tool_use: str = "toolu_09") -> None:
        """A subagent transcript and its meta (2.1.325 keys); `finished` is absent while live."""
        d = self.root / "claude" / "projects" / slug(cwd) / sid(n) / "subagents"
        d.mkdir(parents=True, exist_ok=True)
        meta = {"agentType": kind, "description": desc, "toolUseId": tool_use, "spawnDepth": 1,
                "requestShape": "background", "isBuiltIn": False}
        if finished:
            meta["finished"] = True
        for f, body in ((d / f"agent-{name}.jsonl", "{}\n"), (d / f"agent-{name}.meta.json", json.dumps(meta))):
            f.write_text(body)
            os.utime(f, (mtime, mtime))

    def repo(self, path: str) -> None:
        (self.root / "fs" / path.lstrip("/") / ".git").mkdir(parents=True, exist_ok=True)

    # Hyprland
    def client(self, addr: str, ws: int, cls: str, title: str, pid: int, focus: int, **extra) -> None:
        c = {"address": addr, "mapped": True, "hidden": False, "at": [0, 0], "size": [800, 600],
             "workspace": {"id": ws, "name": str(ws)}, "floating": False, "monitor": 0,
             "class": cls, "title": title, "initialClass": cls, "initialTitle": cls, "pid": pid,
             "xwayland": False, "pinned": False, "fullscreen": 0, "fullscreenClient": 0,
             "grouped": [], "tags": [], "swallowing": "0x0", "focusHistoryID": focus,
             "inhibitingIdle": False, "xdgTag": "", "xdgDescription": "", "contentType": "none"}
        c.update(extra)
        self.clients.append(c)

    def monitor(self, mid: int, name: str, active: int, focused: bool) -> None:
        self.monitors.append({"id": mid, "name": name, "description": "synthetic", "width": 1920,
                              "height": 1080, "refreshRate": 144.0, "x": 1920 * mid, "y": 0,
                              "activeWorkspace": {"id": active, "name": str(active)},
                              "specialWorkspace": {"id": 0, "name": ""}, "focused": focused,
                              "dpmsStatus": True, "disabled": False})

    def workspace(self, wid: int, monitor: str) -> None:
        self.workspaces.append({"id": wid, "name": str(wid), "monitor": monitor, "windows": 1})

    def rule(self, wid: int, monitor: str) -> None:
        self.rules.append({"workspaceString": str(wid), "monitor": monitor})

    def save(self) -> "World":
        for name, data in (("clients", self.clients), ("monitors", self.monitors),
                           ("workspaces", self.workspaces), ("workspacerules", self.rules)):
            (self.root / "hypr" / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
        return self


# ── the main test world ─────────────────────────────────────────────────────

R = f"{HOME}/Repos"


def main_world(root: Path) -> World:
    """Two outputs, 11 workspace slots, a rule naming an unplugged monitor,
    sessions in every state, and every trap the parser has to survive."""
    w = World(root)
    w.monitor(0, "DP-1", active=2, focused=True)
    w.monitor(1, "HDMI-A-1", active=9, focused=False)
    for i in range(1, 9):
        w.rule(i, "DP-1")
    w.rule(9, "HDMI-A-1")
    w.rule(10, "HDMI-A-1")
    w.rule(11, "DP-2")                      # unplugged
    for i in (1, 2, 3, 4, 5, 6):
        w.workspace(i, "DP-1")
    w.workspace(9, "HDMI-A-1")
    w.workspace(11, "HDMI-A-1")             # lives here while DP-2 is away

    w.proc(500, "firefox")
    w.client("0x5500000001", 1, "firefox", "Pull request #12 · lameiro0x/peonza-dots — Mozilla Firefox", 500, 3)

    # ws2: busy, Ahora in the current turn, a 1.5 MB line, two live subagents.
    w.terminal(1000, f"{R}/ryce-pc", fg="claude")
    w.client("0x5500000002", 2, "kitty", "⠂ Montar el rice", 1000, 0)
    w.session(1003, 1, f"{R}/ryce-pc", "busy", ago=200)
    w.transcript(1, f"{R}/ryce-pc", [
        text("**Hecho:**\n- Turno viejo que no debe salir"), turn_end(),
        blob(1_500_000),
        ai_title("Montar el rice del PC nuevo"), *secrets(),
        human(f"Haz el fondo de pantalla de la peonza para cada tema. {MARKER}"),
        text("**Ahora:**\n- Generar el fondo de pantalla\n- Validar la barra en el escenario\n\nEmpiezo por el fondo."),
        tool("Bash", "Generar el fondo"),
    ])
    w.subagent(1, f"{R}/ryce-pc", "a1", NOW - 10, kind="forge-scout", desc="Medir el contraste de cada tema")
    w.subagent(1, f"{R}/ryce-pc", "a2", NOW - 90, desc="Buscar dónde se pinta la barra")
    w.subagent(1, f"{R}/ryce-pc", "a3", NOW - 7200, finished=True, desc="Leer la guía")

    # ws3: waiting; the only Ahora is from the previous turn, so the tool wins.
    w.terminal(1100, f"{R}/brujula", fg="claude")
    w.client("0x5500000003", 3, "kitty", "✳ brujula", 1100, 2)
    w.session(1103, 2, f"{R}/brujula", "waiting", ago=60, waitingFor="permission prompt")
    w.transcript(2, f"{R}/brujula", [
        ai_title("Arreglar el login con passkeys"),
        text("**Ahora:**\n- Leer el código viejo"), turn_end(), *secrets(),
        tool("Bash", "Probar el login en el navegador"),
        tool("Agent", "Ruido de un subagente", side=True),
    ])

    # ws4: idle with Hecho, started in a subdirectory, user-given name; still
    # carries a stale agentwait tag. Plus an nvim window that is focused less.
    w.repo(f"{R}/web-de-ejemplo")
    w.terminal(1200, f"{R}/web-de-ejemplo/src", fg="claude")
    w.client("0x5500000004", 4, "kitty", "blog", 1200, 4, tags=["agentwait"])
    w.session(1203, 3, f"{R}/web-de-ejemplo/src", "idle", ago=1000, name="blog", nameSource="user")
    w.transcript(3, f"{R}/web-de-ejemplo/src", [
        ai_title("Nueva entrada del blog"), *secrets(),
        text("Listo.\n\n**Hecho:**\n- Entrada publicada en `borrador`\n"
             "- Imágenes **optimizadas** con [sharp](https://sharp.pixelplumbing.com)\n\n"
             "**Falta:**\n- Revisar el texto"),
        turn_end(),
    ])
    w.terminal(1300, f"{HOME}/notes", fg="nvim")
    w.client("0x5500000005", 4, "kitty", "nvim", 1300, 5)

    # ws5: fish at the prompt, claude in the background with a live Bash (shell).
    w.terminal(1400, f"{R}/teclados", bg="claude")
    w.client("0x5500000006", 5, "kitty", "fish", 1400, 6)
    w.session(1404, 4, f"{R}/teclados", "shell", ago=500)
    w.transcript(4, f"{R}/teclados", [
        away("Estabas revisando los atajos de teclado. Siguiente paso: probarlos. (disable recaps in /config)"),
    ])

    w.client("0x5500000007", 6, "kitty", "hidden", 1600, 8, hidden=True)
    w.proc(700, "code")
    w.client("0x5500000008", 9, "code", "main.py - agentd - Visual Studio Code", 700, 1)
    w.terminal(1500, f"{HOME}/Downloads")
    w.client("0x5500000009", 11, "kitty", "fish", 1500, 7)
    w.client("0x550000000a", -98, "thunar", "scratch", 1700, 9,
             workspace={"id": -98, "name": "special:scratch"})

    # Sessions with no window, and the ones that must not show at all.
    w.proc(1900, "claude", children=[2000])
    w.proc(2000, "claude", 1900, cwd=f"{R}/cuadernillo")
    w.session(2000, 5, f"{R}/cuadernillo", "busy", ago=300, kind="bg")
    w.transcript(5, f"{R}/cuadernillo", [away("Ordenando la bandeja de entrada del vault.")])
    w.proc(2100, "claude")
    w.session(2100, 6, f"{HOME}/.claude/plugins", None, ago=None, entrypoint="sdk-py")
    w.proc(2200, "claude", start=1)          # pid reused: procStart no longer matches
    w.session(2200, 7, f"{R}/old", "waiting", waitingFor="input needed")
    w.proc(2300, "claude")
    w.session(2300, 8, "", None, raw='{"pid": 2300, "sessionId": "0b6f3f7e-00')
    w.proc(2400, "claude")
    w.session(2400, 9, HOME, None, ago=None)
    w.proc(2500, "claude")
    w.session(2500, 10, f"{R}/nostart", "waiting", procStart=...)

    (w.root / "claude" / "history.jsonl").write_text(json.dumps({"display": MARKER}) + "\n")
    return w.save()


def stage_world(root: Path) -> World:
    """What `tools/stage/scene.sh` feeds Waybar: one output, HEADLESS-1."""
    w = World(root)
    w.monitor(0, "HEADLESS-1", active=2, focused=True)
    for i in (1, 2, 3, 4):
        w.workspace(i, "HEADLESS-1")
    w.proc(500, "firefox")
    w.client("0x5500000001", 1, "firefox", "github.com — lameiro0x/peonza-dots — Mozilla Firefox", 500, 3)
    w.terminal(1000, f"{R}/ryce-pc", fg="claude")
    w.client("0x5500000002", 2, "kitty", "⠂ ryce-pc", 1000, 0)
    w.session(1003, 1, f"{R}/ryce-pc", "busy", ago=200)
    w.transcript(1, f"{R}/ryce-pc", [
        ai_title("Montar el rice del PC nuevo"),
        text("**Ahora:**\n- Generar el fondo de pantalla\n- Validar la barra en el escenario"),
    ])
    w.terminal(1100, f"{R}/brujula", fg="claude")
    w.client("0x5500000003", 3, "kitty", "✳ brujula", 1100, 2)
    w.session(1103, 2, f"{R}/brujula", "waiting", ago=60, waitingFor="permission prompt")
    w.transcript(2, f"{R}/brujula", [
        ai_title("Arreglar el login con passkeys"), tool("Bash", "Probar el login en el navegador"),
    ])
    w.terminal(1200, f"{R}/web-de-ejemplo", fg="claude")
    w.client("0x5500000004", 4, "kitty", "blog", 1200, 4)
    w.session(1203, 3, f"{R}/web-de-ejemplo", "idle", ago=1000)
    w.transcript(3, f"{R}/web-de-ejemplo", [
        ai_title("Nueva entrada del blog"),
        text("**Hecho:**\n- Entrada publicada en borrador\n- Imágenes optimizadas"), turn_end(),
    ])
    w.proc(2000, "claude", cwd=f"{R}/cuadernillo")
    w.session(2000, 5, f"{R}/cuadernillo", "busy", ago=300, kind="bg")
    w.transcript(5, f"{R}/cuadernillo", [away("Ordenando la bandeja de entrada del vault.")])
    return w.save()


def stage8_world(root: Path) -> World:
    """The bar's worst case on one 1920 px output: eight occupied slots, long
    repo names, long titles, a long doing line in the focused window."""
    w = World(root)
    w.monitor(0, "HEADLESS-1", active=2, focused=True)
    rows = [
        ("inventario-de-subredes", "Enumerar subdominios del objetivo autorizado", "busy"),
        ("generador-central-de-informes", "Exportar el informe final en PDF con anexos", "waiting"),
        ("radio-web.github.io", "Reescribir la portada con el nuevo diseño", "idle"),
        ("cuentasCaseras", "Conciliar los movimientos del mes pasado", "busy"),
        ("cuadernillo", "Ordenar la bandeja de entrada del vault", "idle"),
        ("ajustes-shell", "Afinar los permisos del sandbox por proyecto", "busy"),
        ("medidorCoste", "Medir el coste por sesión y por modelo", "idle"),
        ("teclados", "Portar los atajos de teclado a Hyprland Lua", "busy"),
    ]
    for i, (repo, title, state) in enumerate(rows, start=1):
        base = 1000 + 100 * i
        w.workspace(i, "HEADLESS-1")
        w.terminal(base, f"{R}/{repo}", fg="claude")
        w.client(f"0x55000000{i:02x}", i, "kitty", "✳ x", base, 0 if i == 2 else i + 2)
        extra = {"waitingFor": "permission prompt"} if state == "waiting" else {}
        w.session(base + 3, i, f"{R}/{repo}", state, ago=60 * i, **extra)
        w.transcript(i, f"{R}/{repo}", [
            ai_title(title),
            text("**Ahora:**\n- Comprobar que la exportación conserva las tablas y las imágenes"),
        ])
    return w.save()


if __name__ == "__main__":
    if sys.argv[1:] != ["--write-stage"]:
        sys.exit(__doc__.split("\n\n")[-1].rstrip())
    for path, build in ((STAGE, stage_world), (STAGE8, stage8_world)):
        shutil.rmtree(path, ignore_errors=True)
        build(path)
        print(f"wrote {path}")
