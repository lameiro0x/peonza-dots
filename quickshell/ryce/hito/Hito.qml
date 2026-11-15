import QtQuick
import Quickshell
import Quickshell.Io
import qs as Ryce
import qs.bar

// Hito (a task manager on Supabase) over its REST API.
// Credentials come from an env file in the Vite style of Hito's own clients (VITE_SUPABASE_URL,
// VITE_SUPABASE_ANON_KEY, VITE_APP_EMAIL, VITE_APP_PASSWORD), read at runtime and never
// copied or logged; RYCE_HITO_ENV points elsewhere. The session is this shell's own: a
// password login on first need, tokens in memory only, refreshed before they expire,
// never shared with Hito's other clients (refresh tokens are single-use).
// Nothing runs while nothing shows it: HitoRoot sets `wanted` while the drawer is open or
// a desk card is seen; only then does it fetch (throttled) and poll every 10 minutes.
Scope {
    id: hito

    property bool wanted: false
    readonly property string envPath: Quickshell.env("RYCE_HITO_ENV") || (Quickshell.env("HOME") + "/.config/ryce-private/hito.env")
    // "loading" until the env file answers, then "missing" | "incomplete" | "ready".
    property string config: "loading"
    property bool busy: false
    property bool again: false
    property string problem: ""             // the last failure, in Spanish; "" when fine
    property real fetchedAt: 0              // ms; 0 = never
    property string today: day(new Date())
    property var tasks: []                  // pending, overdue to 7 days ahead, plus undated
    // id -> "busy" (PATCH in flight) | ms when the server confirmed it completed.
    property var completing: ({})

    readonly property var overdue: tasks.filter(t => t.date !== "" && t.date < today)
    readonly property var dueToday: tasks.filter(t => t.date === today)
    readonly property var upcoming: tasks.filter(t => t.date > today)
    // Grouped by project: sorted once per fetch here, not by every view that lists them.
    readonly property var undated: tasks.filter(t => t.date === "").sort((a, b) => a.project.localeCompare(b.project, "es"))
    readonly property var everything: overdue.concat(dueToday, upcoming, undated)
    property var projects: ({})             // id -> { name, hue }, from the last fetch

    // The drawer's calendar: every pending task due in the six weeks on show around
    // `month` ("YYYY-MM"), overdue ones on the day they were due. Fetched apart from the
    // list (which stops 7 days ahead), only while `calendarOn`.
    property bool calendarOn: false
    property string month: today.slice(0, 7)
    property var monthTasks: []
    property string monthOf: ""             // the month monthTasks holds; "" = none yet
    property real monthAt: 0
    readonly property string columns: "id,title,project_id,priority,scheduled_date,scheduled_time,recurrence_rule"
    readonly property string order: "scheduled_date.asc.nullslast,scheduled_time.asc.nullslast,priority.asc,sort_order.asc,created_at.asc"
    // Who shows a project's tasks filters by this key; "none" holds the tasks without one.
    readonly property string noProject: "none"
    readonly property var es: Qt.locale("es_ES")

    property var creds: null
    property var auth: ({ token: "", refresh: "", expiresAt: 0, user: "" })
    property var waiting: []                // callbacks queued behind a login
    property bool authing: false
    property var inflight: []               // [{ xhr, at }], for the watchdog

    readonly property int timeoutMs: 15000
    readonly property int staleMs: 120000   // a reveal refetches only if older than this

    function day(d) {
        return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    }
    function shift(iso, n) {
        const p = iso.split("-").map(Number);
        return day(new Date(p[0], p[1] - 1, p[2] + n));
    }
    function date(iso) {
        const p = iso.split("-").map(Number);
        return new Date(p[0], p[1] - 1, p[2]);
    }
    function lateBy(iso) {
        const days = Math.round((date(today) - date(iso)) / 86400000);
        return days === 1 ? "ayer" : "hace " + days + " días";
    }
    function weekday(iso) { return es.toString(date(iso), "ddd d").replace(".", ""); }
    // The Monday that opens the six weeks a month grid shows (MonthGrid, Monday first).
    function gridStart(key) {
        const p = key.split("-").map(Number);
        const first = new Date(p[0], p[1] - 1, 1);
        return day(new Date(p[0], p[1] - 1, 1 - (first.getDay() + 6) % 7));
    }

    function projectKey(task) { return task.projectId !== "" ? task.projectId : noProject; }
    function ofProject(list, key) { return list.filter(t => projectKey(t) === key); }
    function projectName(key) {
        return key === noProject ? "sin proyecto" : (projects[key]?.name ?? "");
    }
    // The projects `list` touches, by name, «sin proyecto» last: [{ key, name, hue }].
    // `keep` stays in even with nothing pending (the one the user picked), as long as
    // Hito still knows it.
    function projectsIn(list, keep) {
        const seen = {};
        for (const t of list) {
            const key = projectKey(t);
            seen[key] = seen[key] ?? { key: key, name: projectName(key) || t.project, hue: t.hue };
        }
        if (keep && !seen[keep] && projectName(keep) !== "")
            seen[keep] = { key: keep, name: projectName(keep), hue: projects[keep]?.hue ?? "" };
        return Object.values(seen).sort((a, b) => a.key === noProject ? 1 : b.key === noProject ? -1
            : a.name.localeCompare(b.name, "es"));
    }
    // A row as the views use it; titles lose their control characters.
    function shape(r) {
        const p = projects[String(r.project_id)] ?? null;
        return {
            id: String(r.id),
            title: String(r.title ?? "").replace(/[\u0000-\u001f\u007f]+/g, " ").trim(),
            projectId: p ? String(r.project_id) : "",
            project: p ? p.name : "",
            hue: p ? p.hue : "",                    // the project colour
            date: r.scheduled_date ? String(r.scheduled_date) : "",
            time: r.scheduled_time ? String(r.scheduled_time).slice(0, 5) : "",
            recurring: !!r.recurrence_rule,
            priority: Number(r.priority) || 3
        };
    }

    // A project's dot. Grey themes (Grafito, Tinta) keep it grey, at the project
    // colour's own lightness, so projects still read apart.
    // A project's colour comes from Hito's own palette (generic web hues). On the desk it
    // is drawn in the theme's ink instead: the grey themes keep its lightness only, the
    // others take the theme hue closest to it (gruvbox in Origen, kanagawa in Ola), so a
    // project still reads apart without a colour from outside the theme.
    // Every desk widget now sits on its own card in the theme's ground (desk/Card.qml), so
    // the theme hues always meet the ground they were chosen for.
    function dotColor(hue, fallback) {
        return pickInk(hue, fallback);
    }
    function pickInk(hue, fallback) {
        if (hue === "") return Qt.color(fallback);
        const c = Qt.color(hue);
        if (BarUi.mono) return Qt.hsla(c.hslHue, 0, c.hslLightness, 1);
        if (c.hslSaturation < 0.12 || c.hslHue < 0) return Qt.color(fallback);
        const inks = [Ryce.Palette.hueCpu, Ryce.Palette.hueMem, Ryce.Palette.hueNet,
                      Ryce.Palette.hueVol, Ryce.Palette.hueMedia, Ryce.Palette.hueDisk];
        let best = fallback, gap = 2;
        for (const ink of inks) {
            if (ink.hslSaturation < 0.12) continue;
            const d = Math.abs(ink.hslHue - c.hslHue);
            const around = Math.min(d, 1 - d);
            if (around < gap) { gap = around; best = ink; }
        }
        return best;
    }

    // KEY=value lines; `export`, quotes and comments tolerated.
    function parseEnv(text) {
        const out = {};
        for (const line of text.split("\n")) {
            const m = line.trim().match(/^(?:export\s+)?([A-Za-z_]\w*)\s*=\s*(.*)$/);
            if (!m) continue;
            const q = m[2].match(/^([\x22\x27])(.*)\1\s*(?:#.*)?$/);      // \x22 \x27: the quotes
            out[m[1]] = q ? q[2] : m[2].replace(/\s+#.*$/, "").trim();
        }
        return out;
    }
    function useEnv(text) {
        const e = parseEnv(text);
        const url = (e.VITE_SUPABASE_URL ?? "").replace(/\/+$/, "");
        // The password only ever goes to a Supabase project over https: an edited .env that
        // points elsewhere (or at plain http) is treated as incomplete, never sent to.
        // RYCE_HITO_ANY_HOST=1 lifts it for the local fake used in tests.
        const host = Quickshell.env("RYCE_HITO_ANY_HOST") === "1" ? /^https?:\/\/[^\s/]+$/ : /^https:\/\/[a-z0-9-]+\.supabase\.co$/;
        const ok = host.test(url) && e.VITE_SUPABASE_ANON_KEY && e.VITE_APP_EMAIL && e.VITE_APP_PASSWORD;
        creds = ok ? { url: url, key: e.VITE_SUPABASE_ANON_KEY, email: e.VITE_APP_EMAIL, password: e.VITE_APP_PASSWORD } : null;
        auth = { token: "", refresh: "", expiresAt: 0, user: "" };
        config = ok ? "ready" : "incomplete";
        problem = "";
        if (ok && wanted) refresh(true);
    }

    // One HTTP exchange. `done(status, body)`; status 0 = no answer (offline, timeout).
    function send(method, path, body, prefer, done) {
        // The .env can vanish for a moment (an editor's rename-save): answer as a failed
        // request instead of throwing, so whoever waits (busy, adding) is released.
        if (!creds) {
            Qt.callLater(() => done(-1, null));
            return;
        }
        const xhr = new XMLHttpRequest();
        xhr.open(method, creds.url + path);
        xhr.setRequestHeader("apikey", creds.key);
        if (auth.token !== "" && path.startsWith("/rest/")) xhr.setRequestHeader("Authorization", "Bearer " + auth.token);
        if (body !== undefined) xhr.setRequestHeader("Content-Type", "application/json");
        if (prefer) xhr.setRequestHeader("Prefer", prefer);
        xhr.onreadystatechange = () => {
            if (xhr.readyState !== XMLHttpRequest.DONE) return;
            inflight = inflight.filter(r => r.xhr !== xhr);
            let reply = null;
            try {
                reply = xhr.responseText ? JSON.parse(xhr.responseText) : null;
            } catch (e) {
                reply = null;
            }
            done(xhr.status, reply);
        };
        inflight = inflight.concat([{ xhr: xhr, at: Date.now() }]);
        xhr.send(body === undefined ? "" : JSON.stringify(body));
    }

    function signedIn(reply) {
        auth = {
            token: reply.access_token,
            refresh: reply.refresh_token ?? "",
            expiresAt: Date.now() + (reply.expires_in ?? 3600) * 1000,
            user: reply.user?.id ?? ""
        };
    }
    // Runs `then(ok)` with a token valid for at least a minute more.
    function withToken(then) {
        if (auth.token !== "" && auth.user !== "" && Date.now() < auth.expiresAt - 60000) {
            then(true);
            return;
        }
        waiting = waiting.concat([then]);
        if (authing) return;
        authing = true;
        const finish = ok => {
            authing = false;
            const queue = waiting;
            waiting = [];
            queue.forEach(f => f(ok));
        };
        const login = () => send("POST", "/auth/v1/token?grant_type=password",
            creds ? { email: creds.email, password: creds.password } : {}, "", (st, reply) => {
                if (st === 200 && reply?.access_token && reply?.user?.id) {
                    signedIn(reply);
                    finish(true);
                    return;
                }
                problem = st === 0 ? "Sin conexión con Hito"
                    : st === 400 ? "Hito no acepta el usuario o la contraseña del .env"
                    : "Hito no deja entrar (error " + st + ")";
                finish(false);
            });
        if (auth.refresh === "") {
            login();
            return;
        }
        // A refresh token is single-use: forget it before it is spent.
        const spent = auth.refresh;
        auth = { token: "", refresh: "", expiresAt: 0, user: "" };
        send("POST", "/auth/v1/token?grant_type=refresh_token", { refresh_token: spent }, "", (st, reply) => {
            if (st === 200 && reply?.access_token && reply?.user?.id) {
                signedIn(reply);
                finish(true);
            } else {
                login();
            }
        });
    }
    // An authenticated REST call; a 401 (token revoked early) signs in again, once.
    // `{user}` in the path becomes the signed-in user's id, known only after the login;
    // a body that needs it comes as a function, called then.
    function api(method, path, body, prefer, done, retried) {
        withToken(ok => {
            if (!ok) {
                done(-1, null);
                return;
            }
            const payload = typeof body === "function" ? body() : body;
            send(method, path.replace("{user}", auth.user), payload, prefer, (st, reply) => {
                if (st === 401 && !retried) {
                    auth = { token: "", refresh: "", expiresAt: 0, user: "" };
                    api(method, path, body, prefer, done, true);
                } else {
                    done(st, reply);
                }
            });
        });
    }
    function failed(st, what) {
        // -1: the login failed and already said why.
        if (st === -1) return;
        problem = st === 0 ? "Sin conexión con Hito" : "Hito no pudo " + what + " (error " + st + ")";
    }

    // Seen again: catch up on the date, and on the list unless it is fresh.
    function touch() {
        today = day(new Date());
        refresh(false);
    }
    function refresh(force) {
        if (config !== "ready") return;
        if (busy) {
            // A change landed while a fetch was out: fetch again once it is back.
            again = again || force;
            return;
        }
        if (!force && fetchedAt > 0 && Date.now() - fetchedAt < staleMs) return;
        busy = true;
        const startedAt = Date.now();
        const now = day(new Date());
        let rows = null;
        let projectRows = null;
        let failure = null;
        const land = () => {
            if (rows === null || projectRows === null) return;
            busy = false;
            if (again) {
                again = false;
                Qt.callLater(refresh, true);
            }
            if (failure !== null) {
                failed(failure, "leer tus tareas");
                return;
            }
            const byId = {};
            for (const p of projectRows)
                byId[String(p.id)] = { name: String(p.name ?? ""), hue: /^#[0-9a-fA-F]{6}$/.test(p.color ?? "") ? String(p.color) : "" };
            projects = byId;
            today = now;
            tasks = rows.map(shape);
            // Completions the server confirmed before this fetch began are now gone from it.
            const keep = {};
            for (const id in completing)
                if (completing[id] === "busy" || completing[id] > startedAt) keep[id] = completing[id];
            completing = keep;
            fetchedAt = Date.now();
            problem = "";
            // A completion or a new task may have changed the month on show too.
            loadMonth(force);
        };
        api("GET", "/rest/v1/tasks?select=" + columns + "&user_id=eq.{user}"
            + "&status=eq.pending&or=(scheduled_date.lte." + shift(now, 7) + ",scheduled_date.is.null)"
            + "&order=" + order + "&limit=400", undefined, "", (st, reply) => {
                rows = st === 200 && Array.isArray(reply) ? reply : [];
                if (rows.length === 0 && st !== 200) failure = st;
                land();
            });
        api("GET", "/rest/v1/projects?select=id,name,color&user_id=eq.{user}", undefined, "", (st, reply) => {
            projectRows = st === 200 && Array.isArray(reply) ? reply : [];
            land();
        });
    }

    // The month on show, once the list (and so the projects) has landed. A reply for a
    // month the user has paged away from is dropped.
    function loadMonth(force) {
        if (!calendarOn || config !== "ready" || fetchedAt === 0) return;
        if (!force && monthOf === month && Date.now() - monthAt < staleMs) return;
        const key = month;
        const from = gridStart(key);
        api("GET", "/rest/v1/tasks?select=" + columns + "&user_id=eq.{user}&status=eq.pending"
            + "&and=(scheduled_date.gte." + from + ",scheduled_date.lte." + shift(from, 41) + ")"
            + "&order=" + order + "&limit=1000", undefined, "", (st, reply) => {
                if (key !== month) return;
                if (st !== 200 || !Array.isArray(reply)) {
                    failed(st, "leer el mes");
                    return;
                }
                monthTasks = reply.map(shape);
                monthOf = key;
                monthAt = Date.now();
            });
    }
    onMonthChanged: loadMonth(false)
    onCalendarOnChanged: loadMonth(false)

    // What the web does on Completar for a task that does not repeat (packages/lib
    // tasks.ts completeTask). A repeating one must roll to its next occurrence with
    // Hito's rrule logic; the views keep those read-only instead.
    function complete(task) {
        if (config !== "ready" || task.recurring || completing[task.id] !== undefined) return;
        completing = Object.assign({}, completing, { [task.id]: "busy" });
        api("PATCH", "/rest/v1/tasks?id=eq." + encodeURIComponent(task.id) + "&user_id=eq.{user}",
            { status: "completed", completed_at: new Date().toISOString() }, "return=minimal", st => {
                const next = Object.assign({}, completing);
                if (st >= 200 && st < 300) {
                    next[task.id] = Date.now();
                    completing = next;
                    refresh(true);
                } else {
                    delete next[task.id];
                    completing = next;
                    failed(st, "completar la tarea");
                }
            });
    }

    // The web's quick add without its parser: today, no project (Hito has no inbox
    // project), priority 3. Row shape as packages/lib tasks.ts toDb().
    function add(title, done) {
        const t = title.replace(/[\u0000-\u001f\u007f]+/g, " ").trim();
        if (config !== "ready" || t === "") {
            done(false);
            return;
        }
        api("POST", "/rest/v1/tasks", () => ({
            user_id: auth.user, project_id: null, title: t.slice(0, 500), description: "", status: "pending",
            priority: 3, scheduled_date: day(new Date()), scheduled_time: null, sort_order: 0,
            time_of_day: "all_day", recurrence_rule: null, recurrence_end_date: null, completed_at: null,
            notifications: [], tags: [], attachments: [], parent_task_id: null
        }), "return=minimal", st => {
            const ok = st >= 200 && st < 300;
            if (ok) refresh(true);
            else failed(st, "guardar la tarea");
            done(ok);
        });
    }

    onWantedChanged: if (wanted) touch()

    FileView {
        path: hito.envPath
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: hito.useEnv(text())
        onLoadFailed: {
            hito.creds = null;
            hito.config = "missing";
        }
    }

    // Every 10 minutes, only while something shows the list.
    Timer {
        running: hito.wanted && hito.config === "ready"
        interval: 600000
        repeat: true
        onTriggered: {
            hito.today = hito.day(new Date());
            hito.refresh(true);
        }
    }

    // XMLHttpRequest has no timeout of its own: abort what hangs, which lands as status 0.
    Timer {
        running: hito.inflight.length > 0
        interval: 3000
        repeat: true
        onTriggered: hito.inflight.filter(r => Date.now() - r.at > hito.timeoutMs).forEach(r => r.xhr.abort())
    }
}
