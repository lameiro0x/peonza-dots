import QtQuick
import Quickshell
import Quickshell.Io

// Aria's library: Navidrome's Subsonic API with token auth (no apiKey extension on
// 0.61). The credentials live outside the repo in ~/.config/ryce-private/aria.json
// ({"url","user","pass"}, 0600 in a 0700 dir); RYCE_ARIA_CONFIG points a test shell at
// its own. The password is only read to derive the token: the salt is drawn once per
// shell, so stream and cover URLs stay stable (Qt's image cache keys on them). Those
// URLs carry the token: never print one.
Scope {
    id: api

    readonly property string configPath: Quickshell.env("RYCE_ARIA_CONFIG") || ((Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config") + "/ryce-private/aria.json")
    // No default server: the setup screen asks for the address, and a saved config
    // (its "url") is what every later start reads.
    readonly property string defaultUrl: ""

    // "loading" reading the file · "setup" no usable credentials · "checking" ping in
    // flight · "ok" · "offline" the server does not answer · "denied" it refuses them
    property string status: "loading"
    property string problem: ""          // Spanish, one line, why it is not "ok"
    property string base: ""             // https://host, no trailing slash
    property string host: ""
    property string auth: ""             // u, t, s, v, c, f as a query string

    readonly property bool usable: auth !== "" && status !== "setup" && status !== "loading"

    function query(params) {
        return Object.keys(params).map(k => encodeURIComponent(k) + "=" + encodeURIComponent(params[k])).join("&");
    }
    function authFor(user, pass) {
        let salt = "";
        for (let i = 0; i < 12; i++) salt += "abcdefghijklmnopqrstuvwxyz0123456789"[Math.floor(Math.random() * 36)];
        return query({ u: user, t: Qt.md5(pass + salt), s: salt, v: "1.16.1", c: "ryce", f: "json" });
    }
    function normalise(url) {
        return String(url ?? "").trim().replace(/\/+$/, "");
    }
    function endpoint(root, credentials, name, params) {
        const extra = params ? query(params) : "";
        return root + "/rest/" + name + ".view?" + credentials + (extra !== "" ? "&" + extra : "");
    }

    function streamUrl(id) { return endpoint(base, auth, "stream", { id: id }); }
    // Covers never go to Image as the authenticated URL: when a load fails, Qt warns with
    // the whole URL (token and salt) and the warning lands in the journal. curl fetches each
    // one once, with the URL on stdin (never in argv), into the runtime dir; Image gets the
    // file. Until it arrives the binding returns "" and the row shows its placeholder.
    property var covers: ({})            // "id@size" -> "file://…", or "" while pending/failed
    // A cover that failed while the server was away is asked again once it answers.
    onStatusChanged: if (status === "ok") {
        const kept = {};
        for (const k in covers) if (covers[k] !== "") kept[k] = covers[k];
        covers = kept;
    }
    property var coverQueue: []
    readonly property string coverDir: (Quickshell.env("RYCE_ARIA_RUN") || Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/ryce-aria-covers"
    function coverUrl(coverArt, size) {
        if (!coverArt || auth === "") return "";
        const key = coverArt + "@" + size;
        const known = covers[key];
        if (known !== undefined) return known;
        if (!coverQueue.some(c => c.key === key)) {
            coverQueue.push({ key: key, id: coverArt, size: size });
            Qt.callLater(nextCover);
        }
        return "";
    }
    function nextCover() {
        if (fetchCover.running || coverQueue.length === 0) return;
        const c = coverQueue.shift();
        fetchCover.key = c.key;
        fetchCover.file = coverDir + "/" + String(c.id).replace(/[^A-Za-z0-9_-]/g, "_") + "-" + c.size + ".img";
        fetchCover.payload = 'url = "' + endpoint(base, auth, "getCoverArt", { id: c.id, size: c.size }).replace(/["\\]/g, "") + '"\n';
        fetchCover.running = true;
    }
    Process {
        id: fetchCover
        property string key: ""
        property string file: ""
        property string payload: ""
        command: ["sh", "-c",
            "umask 077; mkdir -p \"${1%/*}\" || exit 1; [ -s \"$1\" ] && exit 0; "
            + "curl -fs --max-time 10 -K - -o \"$1.part\" && mv -f \"$1.part\" \"$1\" || { rm -f \"$1.part\"; exit 1; }",
            "sh", file]
        stdinEnabled: true
        onStarted: {
            write(payload);
            stdinEnabled = false;
        }
        onExited: code => {
            payload = "";
            stdinEnabled = true;
            const next = Object.assign({}, api.covers);
            next[key] = code === 0 ? "file://" + file : "";
            api.covers = next;
            Qt.callLater(api.nextCover);
        }
    }

    // GET one endpoint; ok(response) with the "subsonic-response" object, fail(text).
    // A request that has not answered in 10 s is aborted: nothing waits forever.
    function call(name, params, ok, fail) {
        if (auth === "") {
            fail?.("Aria no está configurado");
            return;
        }
        request(base, auth, name, params, r => {
            if (status !== "ok") { status = "ok"; problem = ""; }
            ok?.(r);
        }, (kind, text) => {
            if (kind === "offline" || kind === "denied") { status = kind; problem = text; }
            fail?.(text);
        });
    }
    function request(root, credentials, name, params, ok, fail) {
        const xhr = new XMLHttpRequest();
        const deadline = timeout.createObject(api);
        let settled = false;
        const settle = () => { settled = true; deadline.destroy(); };
        deadline.triggered.connect(() => {
            if (settled) return;
            settle();
            xhr.abort();
            fail("offline", "Aria no responde (más de 10 s)");
        });
        xhr.onreadystatechange = () => {
            if (xhr.readyState !== XMLHttpRequest.DONE || settled) return;
            settle();
            if (xhr.status === 0) return fail("offline", "No llego a " + root.replace(/^https?:\/\//, ""));
            let body = null;
            try {
                body = JSON.parse(xhr.responseText)["subsonic-response"];
            } catch (e) {
                body = null;
            }
            if (!body) return fail("offline", "La dirección no responde como un servidor Subsonic (HTTP " + xhr.status + ")");
            if (body.status === "ok") return ok(body);
            const code = body.error?.code ?? 0;
            if (code === 40 || code === 41) return fail("denied", "Usuario o contraseña incorrectos");
            fail("error", body.error?.message ?? "Aria respondió con un error");
        };
        xhr.open("GET", endpoint(root, credentials, name, params));
        xhr.send();
        deadline.start();
    }
    Component {
        id: timeout
        Timer { interval: 10000 }
    }

    function ping() {
        if (auth === "") return;
        status = "checking";
        call("ping", null, null, text => {
            if (status === "checking") { status = "offline"; problem = text; }
        });
    }

    // The setup form: verify against the server first, then write the file. done(text)
    // gets "" on success or the Spanish reason.
    function connect(url, user, pass, done) {
        const root = normalise(url);
        if (!/^https?:\/\/[^\s/]+/.test(root)) return done("La dirección empieza por https://");
        if (String(user).trim() === "" || pass === "") return done("Faltan el usuario o la contraseña");
        request(root, authFor(String(user).trim(), pass), "ping", null, () => {
            save.payload = JSON.stringify({ url: root, user: String(user).trim(), pass: pass });
            save.done = done;
            save.running = true;
        }, (kind, text) => done(text));
    }
    function forget() {
        auth = "";
        base = "";
        status = "setup";
        problem = "";
    }

    // umask 077 and a rename: the file is never readable by others, never half-written.
    // The password goes in on stdin, never on a command line that `ps` shows.
    Process {
        id: save
        property string payload: ""
        property var done: null
        command: ["sh", "-c",
            "umask 077; d=${1%/*}; mkdir -p \"$d\" && chmod 700 \"$d\" || exit 1; "
            + "t=$(mktemp \"$d/.aria.XXXXXX\") || exit 1; "
            + "if cat > \"$t\" && mv -f \"$t\" \"$1\"; then exit 0; fi; rm -f \"$t\"; exit 1",
            "sh", api.configPath]
        stdinEnabled: true
        onStarted: {
            write(payload);
            stdinEnabled = false;
        }
        onExited: code => {
            payload = "";
            stdinEnabled = true;
            const cb = done;
            done = null;
            if (code !== 0) return cb?.("No pude guardar " + api.configPath);
            config.reload();
            cb?.("");
        }
    }

    FileView {
        id: config
        path: api.configPath
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoadFailed: api.forget()
        onLoaded: {
            let c = null;
            try {
                c = JSON.parse(text());
            } catch (e) {
                c = null;
            }
            const url = api.normalise(c?.url);
            if (!c || !/^https?:\/\//.test(url) || typeof c.user !== "string" || c.user === "" || typeof c.pass !== "string" || c.pass === "") {
                api.forget();
                return;
            }
            api.base = url;
            api.host = url.replace(/^https?:\/\//, "");
            api.auth = api.authFor(c.user, c.pass);
            api.ping();
        }
    }
}
