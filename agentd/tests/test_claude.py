import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from agentd import claude
from agentd.claude import ClaudeHome, Digest, clean, digest, doing, parse_tail, project_of
import world
from world import MARKER, NOW, World, ack, ai_title, away, blob, human, note, queued, secrets, text, tool, turn_end


def lines(*records) -> bytes:
    return b"".join(json.dumps(r).encode() + b"\n" for r in records)


class ParseTailTest(unittest.TestCase):
    def test_partial_first_line_is_dropped_only_when_asked(self):
        data = b'tle","aiTitle":"cut"}\n' + lines(ai_title("whole"))
        self.assertEqual([r["aiTitle"] for r in parse_tail(data, partial=True)], ["whole"])

    def test_unfinished_last_line_and_garbage_are_skipped(self):
        data = lines(ai_title("a")) + b"not json\n" + b'{"type":"ai-title","aiTi'
        self.assertEqual([r["aiTitle"] for r in parse_tail(data, partial=False)], ["a"])

    def test_user_text_records_never_survive_parsing(self):
        recs = parse_tail(lines(*secrets(), ai_title("t")), partial=False)
        self.assertNotIn(MARKER, json.dumps(recs))


class CleanTest(unittest.TestCase):
    def test_markdown_is_stripped_to_raw_text(self):
        self.assertEqual(clean("Imágenes **optimizadas** con [sharp](https://x.y) y `npm`"),
                         "Imágenes optimizadas con sharp y npm")

    def test_angle_bracket_and_controls_cannot_reach_a_consumer(self):
        self.assertEqual(clean("a <b>\tc\x07"), "a ‹b> c")

    def test_bracket_floods_stay_linear(self):
        t = time.monotonic()
        clean("[" * 80_000 + "](" * 20_000)
        self.assertLess(time.monotonic() - t, 0.5)

    def test_long_line_is_clipped_at_a_word_to_90(self):
        out = clean("palabra " * 30)
        self.assertLessEqual(len(out), 90)
        self.assertTrue(out.endswith("palabra…"))


class DigestTest(unittest.TestCase):
    def test_ahora_counts_only_in_the_current_turn(self):
        d = digest([text("**Ahora:**\n- viejo"), turn_end(), tool("Bash", "Compilar")])
        self.assertEqual(d.ahora, ())
        self.assertEqual(d.tool, ("Compilar",))

    def test_latest_ahora_bullets_up_to_three(self):
        d = digest([text("**Ahora:**\n- a"),
                    text("intro\n\n**Ahora:**\n\n- uno\n* dos\n1. tres\n- cuatro\n\nresto")])
        self.assertEqual(d.ahora, ("uno", "dos", "tres"))

    def test_inline_ahora_text_is_a_line(self):
        self.assertEqual(digest([text("**Ahora:** Arreglar el favicon")]).ahora, ("Arreglar el favicon",))

    def test_sidechain_records_are_ignored(self):
        d = digest([tool("Bash", "principal"), tool("Agent", "hijo", side=True),
                    text("**Ahora:**\n- del hijo", side=True)])
        self.assertEqual((d.tool, d.ahora), (("principal",), ()))

    def test_tool_without_description_falls_back_to_its_name(self):
        self.assertEqual(digest([tool("Read")]).tool, ("Read",))

    def test_hecho_comes_from_the_last_closed_turn(self):
        d = digest([text("**Hecho:**\n- antiguo"), turn_end(),
                    text("**Hecho:**\n- reciente\n\n**Falta:**\n- otra cosa"), turn_end()])
        self.assertEqual(d.hecho, ("reciente",))

    def test_did_is_the_first_bullet_of_the_latest_hecho_anywhere(self):
        d = digest([text("**Hecho:**\n- antiguo"), turn_end(),
                    text("**Hecho:**\n- Arreglé la barra\n- Probé el login"), turn_end(),
                    text("sin resumen"), turn_end(),                   # a turn without Hecho keeps it
                    text("**Hecho:**\n- del hijo", side=True)])
        self.assertEqual((d.did, d.hecho), ("Arreglé la barra", ()))
        self.assertEqual(digest([text("**Hecho:** Todo `listo` en **una** línea")]).did, "Todo listo en una línea")
        self.assertEqual(digest([text("nada")]).did, "")

    def test_did_is_one_redacted_line_of_at_most_ask_max(self):
        d = digest([text("**Hecho:**\n- Guardé password: hunter2hunter2 y " + "palabra " * 20)])
        self.assertNotIn("hunter2", d.did)
        self.assertLessEqual(len(d.did), claude.ASK_MAX)
        self.assertTrue(d.did.endswith("…"))
        self.assertNotIn("\n", d.did)

    def test_away_summary_loses_the_recap_suffix_and_wraps(self):
        d = digest([away("Hiciste X. " * 40 + "(disable recaps in /config)")])
        self.assertEqual(len(d.away), 3)
        self.assertTrue(all(len(x) <= 90 for x in d.away))
        d = digest([away("Siguiente paso: probarlos. (disable recaps in /config)")])
        self.assertEqual(d.away, ("Siguiente paso: probarlos.",))

    def test_title_is_the_last_ai_title(self):
        self.assertEqual(digest([ai_title("a"), ai_title("b")]).title, "b")


class DoingTest(unittest.TestCase):
    D = Digest(title=None, ahora=("a",), tool=("t",), away=("w",), hecho=("h",))

    def test_busy_and_waiting_prefer_ahora_then_tool_then_away(self):
        self.assertEqual(doing(self.D, "busy"), ("ahora", ["a"]))
        self.assertEqual(doing(self.D._replace(ahora=()), "waiting"), ("tool", ["t"]))
        self.assertEqual(doing(self.D._replace(ahora=(), tool=()), "busy"), ("away", ["w"]))
        self.assertEqual(doing(Digest(None, (), (), (), ("h",)), "busy"), ("none", []))

    def test_idle_and_shell_prefer_hecho(self):
        self.assertEqual(doing(self.D, "idle"), ("hecho", ["h"]))
        self.assertEqual(doing(self.D._replace(hecho=()), "shell"), ("ahora", ["a"]))


def bg(name, tid, desc="Correr los tests", **kw):
    flag = {} if name == "Monitor" else {"run_in_background": "true" if name == "Agent" else True}
    return tool(name, desc, tid=tid, **flag, **kw)


class BackgroundTest(unittest.TestCase):
    """Measured on 2.1.325: launch = tool_use with run_in_background (Agent sends the
    string "true") or a Monitor; end = a task-notification with a <status>."""

    def pending(self, *records):
        return [(p.id, p.kind) for p in digest(parse_tail(lines(*records), partial=False)).pending]

    def test_a_background_shell_is_pending_across_the_turn_end_until_its_status(self):
        recs = [bg("Bash", "t1"), ack("t1", backgroundTaskId="b1"), turn_end()]
        self.assertEqual(self.pending(*recs), [("t1", "shell")])
        self.assertEqual(self.pending(*recs, note("t1", "completed", "b1")), [])
        self.assertEqual(self.pending(*recs, note("t1", "failed", "b1")), [])

    def test_agents_and_monitors_are_pending_with_their_kind(self):
        self.assertEqual(self.pending(bg("Agent", "t1"), bg("Monitor", "t2"), bg("Bash", "t3")),
                         [("t1", "agent"), ("t2", "monitor"), ("t3", "shell")])

    def test_a_foreground_tool_is_not_pending(self):
        self.assertEqual(self.pending(tool("Bash", "x", tid="t1", run_in_background=False),
                                      tool("Agent", "y", tid="t2")), [])

    def test_a_notification_without_status_is_an_event_not_the_end(self):
        self.assertEqual(self.pending(bg("Monitor", "t1"), note("t1", None)), [("t1", "monitor")])

    def test_matched_by_the_acknowledged_task_id_when_the_tool_use_id_differs(self):
        self.assertEqual(self.pending(bg("Agent", "t1"), ack("t1", agentId="a9", isAsync=True,
                                                             status="async_launched"),
                                      note("other", "completed", "a9")), [])

    def test_task_stop_ends_it(self):
        self.assertEqual(self.pending(bg("Bash", "t1"), ack("t1", backgroundTaskId="b1"),
                                      tool("TaskStop", None, tid="t2", task_id="b1")), [])

    def test_a_subagents_own_launches_are_not_the_sessions(self):
        self.assertEqual(self.pending(tool("Bash", "x", side=True, tid="t1", run_in_background=True)), [])

    def test_unanswered_launches_are_capped(self):
        recs = [bg("Bash", f"t{i}") for i in range(claude.PENDING_MAX + 5)]
        got = self.pending(*recs)
        self.assertEqual((len(got), got[0][0]), (claude.PENDING_MAX, "t5"))

    def test_launch_time_comes_from_the_record(self):
        d = digest(parse_tail(lines(bg("Bash", "t1", at="2026-11-09T10:00:00.000Z")), partial=False))
        self.assertEqual(d.pending[0].at, NOW - 1600)

    def test_a_notification_queued_as_an_attachment_ends_it_too(self):
        # Measured 2026-11-14 over 400 transcripts: ~45 % of notifications arrive this way.
        self.assertEqual(self.pending(bg("Bash", "t1"), turn_end(), queued("t1", "completed")), [])
        self.assertEqual(self.pending(bg("Monitor", "t1"), queued("t1", None)), [("t1", "monitor")])
        self.assertEqual(self.pending(bg("Monitor", "t1"), queued("t1", None), queued("t1", "stopped")), [])
        self.assertEqual(self.pending(bg("Agent", "t1"), ack("t1", agentId="a9", isAsync=True,
                                                             status="async_launched"),
                                      queued("other", "failed", "a9")), [])

    def test_a_queued_prompt_that_is_not_a_notification_is_ignored(self):
        r = queued("t1", "completed")
        r["attachment"]["commandMode"] = "prompt"
        self.assertEqual(self.pending(bg("Bash", "t1"), r), [("t1", "shell")])
        self.assertNotIn(MARKER, json.dumps(parse_tail(lines(r, queued("t1", "completed")), partial=False)))

    def test_notification_and_tool_output_never_survive_parsing(self):
        recs = parse_tail(lines(bg("Bash", "t1"), ack("t1", backgroundTaskId="b1"),
                                note("t1", "completed", "b1")), partial=False)
        self.assertNotIn(MARKER, json.dumps(recs))


class AskedTest(unittest.TestCase):
    def asked(self, *records):
        return digest(parse_tail(lines(*records), partial=False)).asked

    def test_first_sentence_of_the_last_human_prompt(self):
        self.assertEqual(self.asked(human("Uno. Dos."), text("ok"), human("Arregla la luz nocturna. Y luego más.")),
                         "Arregla la luz nocturna.")

    def test_clipped_to_sixty_at_a_word_boundary(self):
        out = self.asked(human("quiero que la barra marque como trabajando a los agentes que esperan un shell"))
        self.assertLessEqual(len(out), claude.ASK_MAX)
        self.assertEqual(out, "quiero que la barra marque como trabajando a los agentes…")

    def test_code_pastes_quotes_and_tags_are_skipped(self):
        body = ("```\nTraceback (most recent call last):\n```\n    indented = code()\n"
                "<system-reminder>no</system-reminder>\n> citado\n[Pasted text #1 +40 lines]\n"
                "0x55d0 /tmp/a.py:12 {}\n¿Por qué falla el **login**? Mira el log.")
        self.assertEqual(self.asked(human(body)), "¿Por qué falla el login?")

    def test_image_and_text_blocks(self):
        self.assertEqual(self.asked(human([{"type": "image", "source": {"type": "base64", "data": "AAAA"}},
                                           {"type": "text", "text": "Mira la captura"}])), "Mira la captura")

    def test_only_human_prompts_count(self):
        meta = dict(human("Texto inyectado"), origin=None, isMeta=True)
        self.assertEqual(self.asked(human("La de verdad"), meta, *secrets(), note("t1", "completed"),
                                    human("Del subagente", side=True)), "La de verdad")

    def test_credentials_in_a_prompt_never_reach_the_line(self):
        # Synthetic values, assembled at run time: no credential-shaped literal sits
        # in the repo (the secret-guard hook rightly refuses one).
        body = "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3z"
        gh, sk, aws, slack = "gh" + "p_" + body, "sk" + "-proj-" + body[:20], "AK" + "IA" + "IOSFODNN7EXAMPLE", "xo" + "xb-" + "1234567890-" + body[:12]
        jwt = "ey" + "JhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc"
        cases = {
            f"usa este token {gh} para el push": gh[:8],
            f"OPENAI_API_KEY={sk} en el env": sk[:8],
            f"prueba {jwt} en la API": jwt[:8],
            "clona https://yo:Hunter2pass@git.example.com/repo ya": "Hunter2",
            "la contraseña es Hunter2pass y entra": "Hunter2",
            f"mira {aws} en la cuenta": aws[:8],
            "revisa por qué el commit 9f86d081884c7d659a2feaa0c55ad015 no cuadra con la rama principal": "9f86d08",
            f"canal {slack} y nada más": slack[:8],
        }
        for prompt, secret in cases.items():
            out = self.asked(human(prompt))
            self.assertNotIn(secret, out, prompt)
            self.assertIn("…", out, prompt)

    def test_ordinary_words_are_not_redacted(self):
        for prompt in ("Arregla la luz nocturna del panel lateral.",
                       "Internacionalización de la barra en Hyprland 0.57 y Qt 6.12.",
                       "Revisa el tokenizador y la palabra clave del índice."):
            self.assertEqual(self.asked(human(prompt)), claude.clean(prompt.split(". ")[0], claude.ASK_MAX))
            self.assertNotIn("…", self.asked(human(prompt)).rstrip("…"), prompt)

    def test_nothing_past_the_first_sentence_survives_parsing(self):
        recs = parse_tail(lines(human(f"Haz esto. {MARKER}"), human(f"```\n{MARKER}\n```")), partial=False)
        self.assertNotIn(MARKER, json.dumps(recs))
        self.assertEqual(recs, [{"type": "user", "asked": "Haz esto."}])


class DoingLineTest(unittest.TestCase):
    def test_ahora_bullets_then_tool_then_background_work(self):
        d = Digest(None, ("Arreglar el favicon", "Hacer la web"), ("t",), (), ())
        p = (claude.Pending("t1", "shell", "Correr los tests", None),)
        self.assertEqual(claude.doing_line(d, p), "Arreglar el favicon · Hacer la web")
        self.assertEqual(claude.doing_line(d._replace(ahora=()), p), "t")
        self.assertEqual(claude.doing_line(Digest.EMPTY, p), "Correr los tests")
        self.assertEqual(claude.doing_line(Digest.EMPTY), "")

    def test_only_whole_bullets_join_and_never_past_sixty(self):
        d = Digest(None, ("Generar el fondo de pantalla", "Validar la barra en el escenario"), (), (), ())
        self.assertEqual(claude.doing_line(d), "Generar el fondo de pantalla")
        d = Digest(None, ("palabra " * 10, "otra"), (), (), ())
        self.assertLessEqual(len(claude.doing_line(d)), claude.ASK_MAX)


class HomeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(Path(self.tmp.name))
        self.now = NOW
        self.home = ClaudeHome(self.w.root / "claude", clock=lambda: self.now)

    def tearDown(self):
        self.tmp.cleanup()

    def sfile(self, pid):
        return self.w.root / "claude" / "sessions" / f"{pid}.json"

    def test_truncated_session_read_keeps_the_last_good_one(self):
        self.w.session(10, 1, "/r/a", "busy")
        self.assertEqual(self.home.sessions()[10]["status"], "busy")
        self.sfile(10).write_text('{"pid": 10, "sta')   # read mid-rewrite (O_TRUNC, no rename)
        self.assertEqual(self.home.sessions()[10]["status"], "busy")

    def test_truncated_session_never_seen_whole_is_absent(self):
        self.w.session(10, 1, "", None, raw='{"pid": 1')
        self.assertEqual(self.home.sessions(), {})

    def test_removed_session_file_is_gone_and_other_files_are_ignored(self):
        self.w.session(10, 1, "/r/a", "idle")
        (self.w.root / "claude" / "sessions" / "10.abc.key").write_text("k")
        self.assertEqual(list(self.home.sessions()), [10])
        self.sfile(10).unlink()
        self.assertEqual(self.home.sessions(), {})

    def test_signature_changes_when_a_session_file_changes(self):
        self.w.session(10, 1, "/r/a", "idle")
        a = self.home.signature()
        self.w.session(10, 1, "/r/a", "waiting", waitingFor="input needed")
        os.utime(self.sfile(10), ns=(1, 2))
        self.assertNotEqual(a, self.home.signature())

    def test_transcript_reread_only_on_growth_and_at_most_every_two_seconds(self):
        f = self.w.transcript(1, "/r/a", [ai_title("uno")])
        self.assertEqual(self.home.transcript(world.sid(1), "/r/a").title, "uno")
        with f.open("a") as fh:
            fh.write(json.dumps(ai_title("dos")) + "\n")
        self.now += 1
        self.assertEqual(self.home.transcript(world.sid(1), "/r/a").title, "uno")
        self.now += 1.5
        self.assertEqual(self.home.transcript(world.sid(1), "/r/a").title, "dos")

    def test_a_status_change_forces_a_reread_inside_the_throttle(self):
        f = self.w.transcript(1, "/r/a", [text("**Ahora:**\n- algo")])
        self.assertEqual(self.home.transcript(world.sid(1), "/r/a", stamp=("busy", 1)).ahora, ("algo",))
        with f.open("a") as fh:
            fh.write(json.dumps(text("**Hecho:**\n- terminado")) + "\n" + json.dumps(turn_end()) + "\n")
        self.now += 0.5
        self.assertEqual(self.home.transcript(world.sid(1), "/r/a", stamp=("busy", 1)).hecho, ())
        self.assertEqual(self.home.transcript(world.sid(1), "/r/a", stamp=("idle", 2)).hecho, ("terminado",))

    def test_huge_last_line_keeps_what_was_known(self):
        f = self.w.transcript(1, "/r/a", [ai_title("t"), text("**Ahora:**\n- algo")])
        self.assertEqual(self.home.transcript(world.sid(1), "/r/a").ahora, ("algo",))
        with f.open("a") as fh:
            fh.write(json.dumps(blob(1_500_000)) + "\n")
        self.now += 5
        d = self.home.transcript(world.sid(1), "/r/a")
        self.assertEqual((d.title, d.ahora), ("t", ("algo",)))

    def test_tail_starting_inside_a_huge_line_still_parses_what_follows(self):
        self.w.transcript(1, "/r/a", [blob(claude.TAIL_BYTES + 500_000), ai_title("tras la línea gorda")])
        self.assertEqual(self.home.transcript(world.sid(1), "/r/a").title, "tras la línea gorda")

    # A real turn writes its Ahora first and then megabytes of tool results, request
    # blobs and attachments (one screenshot is 1.4 MB). Measured 2026-11-09 on 2.1.319:
    # a fixed 256 KB tail lost the Ahora after three or four tool calls.

    def append(self, f, *records):
        with f.open("a") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")

    def read(self):
        self.now += 5
        return self.home.transcript(world.sid(1), "/r/a")

    def test_ahora_outlives_a_turn_longer_than_any_tail(self):
        f = self.w.transcript(1, "/r/a", [ai_title("t"), text("**Ahora:**\n- algo")])
        self.assertEqual(self.read().ahora, ("algo",))
        for i in range(3):
            self.append(f, blob(claude.TAIL_BYTES // 2), tool("Bash", f"paso {i}"))
            self.read()
        self.append(f, blob(claude.TAIL_BYTES + 10), tool("Bash", "último"))
        d = self.read()
        self.assertEqual((d.title, d.ahora, d.tool), ("t", ("algo",), ("último",)))

    def test_a_turn_that_closes_far_from_its_ahora_still_yields_its_hecho(self):
        f = self.w.transcript(1, "/r/a", [text("**Ahora:**\n- viejo")])
        self.assertEqual(self.read().ahora, ("viejo",))
        self.append(f, blob(claude.TAIL_BYTES + 10), text("**Hecho:**\n- listo"), turn_end(),
                    blob(claude.TAIL_BYTES + 10), tool("Bash", "nuevo"))
        d = self.read()
        self.assertEqual((d.ahora, d.hecho, d.tool), ((), ("listo",), ("nuevo",)))

    def test_first_read_reaches_an_ahora_megabytes_back(self):
        # agentd (re)started in the middle of a long turn.
        self.w.transcript(1, "/r/a", [text("**Ahora:**\n- desde antes"), blob(2_000_000), tool("Bash", "x")])
        self.assertEqual(self.read().ahora, ("desde antes",))

    def test_a_line_still_being_written_is_read_once_it_ends(self):
        f = self.w.transcript(1, "/r/a", [ai_title("t")])
        line = json.dumps(text("**Ahora:**\n- a medias")) + "\n"
        with f.open("a") as fh:
            fh.write(line[:40])
        self.assertEqual(self.read().ahora, ())
        with f.open("a") as fh:
            fh.write(line[40:])
        self.assertEqual(self.read().ahora, ("a medias",))

    def test_a_huge_line_being_written_is_not_mistaken_for_records(self):
        f = self.w.transcript(1, "/r/a", [blob(claude.TAIL_BYTES + 10)])
        with f.open("a") as fh:   # still inside the first window's huge line, no newline yet
            fh.write('{"type":"api-request-blob","x":"' + "y" * 1000)
        self.read()
        with f.open("a") as fh:
            fh.write('"}\n' + json.dumps(text("**Ahora:**\n- después")) + "\n")
        self.assertEqual(self.read().ahora, ("después",))

    def test_a_replaced_or_truncated_transcript_is_read_from_scratch(self):
        f = self.w.transcript(1, "/r/a", [ai_title("t"), text("**Ahora:**\n- viejo")])
        self.assertEqual(self.read().ahora, ("viejo",))
        new = f.with_suffix(".new")
        new.write_text(json.dumps(text("**Ahora:**\n- nuevo")) + "\n" + json.dumps(blob(5000)) + "\n")
        os.replace(new, f)
        d = self.read()
        self.assertEqual((d.title, d.ahora), ("t", ("nuevo",)))
        f.write_text(json.dumps(tool("Bash", "corto")) + "\n")   # same inode, shorter
        self.assertLess(f.stat().st_size, 5000)
        d = self.read()
        self.assertEqual((d.ahora, d.tool), ((), ("corto",)))

    def test_falling_too_far_behind_restarts_from_a_tail(self):
        f = self.w.transcript(1, "/r/a", [text("**Ahora:**\n- algo")])
        self.assertEqual(self.read().ahora, ("algo",))
        self.append(f, blob(5000), tool("Bash", "tras el salto"))
        with mock.patch.object(claude, "CATCHUP_BYTES", 1000), mock.patch.object(claude, "TAIL_BYTES", 2000):
            d = self.read()
        self.assertEqual((d.ahora, d.tool), ((), ("tras el salto",)))

    def test_transcript_found_when_the_slug_does_not_match(self):
        d = self.w.root / "claude" / "projects" / "-truncated-slug-1a2b"
        d.mkdir(parents=True)
        (d / f"{world.sid(1)}.jsonl").write_text(json.dumps(ai_title("x")) + "\n")
        self.assertEqual(self.home.transcript(world.sid(1), "/very/long/path").title, "x")

    def test_missing_transcript_is_an_empty_digest(self):
        self.assertEqual(self.home.transcript(world.sid(9), "/nowhere"), Digest.EMPTY)

    def test_subagents_come_from_their_meta_files_live_first(self):
        self.w.transcript(1, "/r/a", [ai_title("x")])
        self.w.subagent(1, "/r/a", "a", NOW - 3600, kind="forge-scout", desc="Medir el contraste")
        self.w.subagent(1, "/r/a", "b", NOW - 5, finished=True, desc="Leer la guía", tool_use="toolu_b")
        self.w.subagent(1, "/r/a", "c", NOW - 50, desc="**Buscar** `x` " + "muy " * 30)
        subs = self.home.subagents(world.sid(1), "/r/a")
        self.assertEqual([(s.id, s.live) for s in subs], [("c", True), ("a", True), ("b", False)])
        self.assertEqual((subs[1].type, subs[1].description), ("forge-scout", "Medir el contraste"))
        self.assertEqual(subs[2].tool_use, "toolu_b")
        self.assertLessEqual(len(subs[0].description), claude.ASK_MAX)
        self.assertTrue(subs[0].description.startswith("Buscar x muy"))

    def test_a_meta_older_than_the_process_is_an_orphan_not_live(self):
        self.w.transcript(1, "/r/a", [ai_title("x")])
        self.w.subagent(1, "/r/a", "old", NOW - 9500)
        self.w.subagent(1, "/r/a", "new", NOW - 10)
        subs = self.home.subagents(world.sid(1), "/r/a", started=NOW - 9000)
        self.assertEqual([(s.id, s.live) for s in subs], [("new", True), ("old", False)])

    def test_a_torn_meta_is_skipped_and_a_finished_one_is_seen_on_change(self):
        self.w.transcript(1, "/r/a", [ai_title("x")])
        self.w.subagent(1, "/r/a", "a", NOW - 5)
        meta = self.w.root / "claude" / "projects" / world.slug("/r/a") / world.sid(1) / "subagents" / "agent-a.meta.json"
        (meta.parent / "agent-b.meta.json").write_text('{"agentType": "Expl')
        (meta.parent / "notes.txt").write_text("x")
        self.assertEqual([(s.id, s.live) for s in self.home.subagents(world.sid(1), "/r/a")], [("a", True)])
        meta.write_text(json.dumps({"agentType": "Explore", "finished": True}))
        os.utime(meta, (NOW, NOW))
        self.assertEqual([(s.id, s.live) for s in self.home.subagents(world.sid(1), "/r/a")], [("a", False)])

    def test_no_subagents_directory_is_an_empty_list(self):
        self.w.transcript(1, "/r/a", [ai_title("x")])
        self.assertEqual(self.home.subagents(world.sid(1), "/r/a"), [])
        self.assertEqual(self.home.subagents(world.sid(9), "/nowhere"), [])

    def test_a_fifo_never_blocks_a_read(self):
        # A blocking open() of a FIFO with no writer waits forever: the daemon would freeze.
        self.w.transcript(1, "/r/a", [ai_title("x")])
        self.w.subagent(1, "/r/a", "a", NOW - 5)
        subs = self.w.root / "claude" / "projects" / world.slug("/r/a") / world.sid(1) / "subagents"
        os.mkfifo(subs / "agent-b.meta.json")
        os.mkfifo(self.sfile(10))
        fifo_transcript = self.w.root / "claude" / "projects" / world.slug("/r/b") / f"{world.sid(2)}.jsonl"
        fifo_transcript.parent.mkdir(parents=True)
        os.mkfifo(fifo_transcript)
        done = []

        def run():
            done.append((self.home.sessions(), [s.id for s in self.home.subagents(world.sid(1), "/r/a")],
                         self.home.transcript(world.sid(2), "/r/b")))
        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(5)
        self.assertFalse(t.is_alive(), "a FIFO blocked the read")
        self.assertEqual(done[0], ({}, ["a"], Digest.EMPTY))

    def test_a_symlinked_transcript_is_not_followed(self):
        secret = self.w.root / "elsewhere.jsonl"
        secret.write_text(json.dumps(ai_title("de otro sitio")) + "\n")
        d = self.w.root / "claude" / "projects" / world.slug("/r/a")
        d.mkdir(parents=True)
        os.symlink(secret, d / f"{world.sid(1)}.jsonl")
        self.assertEqual(self.home.transcript(world.sid(1), "/r/a"), Digest.EMPTY)

    def test_a_session_id_that_is_not_a_uuid_is_never_globbed(self):
        self.w.transcript(1, "/r/a", [ai_title("x")])
        self.assertEqual(self.home.transcript("*", "/r/a"), Digest.EMPTY)
        self.assertEqual(self.home.subagents("../../x", "/r/a"), [])


class ProjectTest(unittest.TestCase):
    def test_git_root_basename_from_a_subdirectory(self):
        with tempfile.TemporaryDirectory() as t:
            w = World(Path(t))
            w.repo("/home/u/Repos/site")
            fs = str(w.root / "fs")
            self.assertEqual(project_of("/home/u/Repos/site/src/pages", fs), "site")
            self.assertEqual(project_of("/home/u/Downloads", fs), "Downloads")
            self.assertEqual(project_of("/", fs), "/")
            self.assertEqual(project_of("", fs), "")

    def test_a_repo_created_later_is_seen_after_the_cache_expires(self):
        with tempfile.TemporaryDirectory() as t:
            w = World(Path(t))
            fs = str(w.root / "fs")
            clock = [1000.0]
            self.assertEqual(project_of("/home/u/new/src", fs, now=clock[0]), "src")
            w.repo("/home/u/new")
            self.assertEqual(project_of("/home/u/new/src", fs, now=clock[0] + 30), "src")
            self.assertEqual(project_of("/home/u/new/src", fs, now=clock[0] + 61), "new")

    def test_walk_stops_after_eight_levels(self):
        with tempfile.TemporaryDirectory() as t:
            w = World(Path(t))
            w.repo("/r")
            deep = "/r/" + "/".join("abcdefghij")
            self.assertEqual(project_of(deep, str(w.root / "fs")), "j")


if __name__ == "__main__":
    unittest.main()
