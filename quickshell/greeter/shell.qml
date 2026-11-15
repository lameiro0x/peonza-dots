import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Greetd
import qs

// ryce's login page: greetd's greeter after the LUKS passphrase, inside cage
// (install/boot/ryce-greeter). One fixed look whatever the desktop theme (Look.qml) over the
// art theme/boot/greeter.py renders. cage 0.3 has no layer shell: one FloatingWindow, which
// cage makes fullscreen. It always starts the same session, start-hyprland.
//
//   RYCE_GREETER_HEARTBEAT  file the wrapper watches: "up" once the page is built and greetd
//                           answers, "launch" just before the session starts. No "up" in
//                           time and the wrapper falls back to regreet, then tuigreet.
//   RYCE_GREETER_LAYOUTS    cage's XKB_DEFAULT_LAYOUT (us,es): the layouts Alt+Shift cycles
//   RYCE_GREETER_DEMO       fake greetd, for screenshots on the stage; nothing sets it in
//                           production (the wrapper does not, greetd starts it clean):
//                           1 (any password but «error» or «locked» signs in), typing (the
//                           field filled, Caps Lock on), error (a refusal shown), locked
//                           (faillock's long line shown). Never runs systemctl.
ShellRoot {
    id: shell

    QtObject {
        id: login

        readonly property string demo: Quickshell.env("RYCE_GREETER_DEMO") || ""
        property var users: []
        property int userIndex: 0
        readonly property string user: users.length > 0 ? users[userIndex] : (demo !== "" ? Quickshell.env("USER") : "")

        // The keyboard group. Alt+Shift (grp:alt_shift_toggle) switches it inside xkb, where
        // this page cannot see, and it may already have switched before this window mapped
        // (during the load after LUKS). So the layout starts unknown (-1, the tag shows every
        // name), turns unknown again after the chord, and is known only once a key that types
        // differently in each layout says which one xkb used. Never a guess.
        readonly property var layouts: (Quickshell.env("RYCE_GREETER_LAYOUTS") || "us").split(",")
        property int layoutIndex: layouts.length > 1 ? -1 : 0
        readonly property string layoutName: layoutIndex >= 0 ? layouts[layoutIndex].toUpperCase()
            : layouts.map(l => l.toUpperCase()).join("/")
        // Per layout, by xkb keycode: the key's characters without and with Shift, for the
        // keys where us and es differ (the digits' Shift row and the punctuation).
        readonly property var keyTable: ({
            "us": { 11: "2@", 12: "3#", 15: "6^", 16: "7&", 17: "8*", 18: "9(", 19: "0)", 20: "-_", 21: "=+",
                    35: "]}", 47: ";:", 49: "`~", 51: "\\|", 59: ",<", 60: ".>", 61: "/?" },
            "es": { 11: "2\"", 12: "3·", 15: "6&", 16: "7/", 17: "8(", 18: "9)", 19: "0=", 20: "'?", 21: "¡¿",
                    35: "+*", 47: "ñÑ", 49: "ºª", 51: "çÇ", 59: ",;", 60: ".:", 61: "-_" }
        })

        // The page's own refusal, shown as a chip; PAM's lines (they run long) stay a line.
        readonly property string wrongPassword: "Contraseña incorrecta"
        // Where greetd runs this greeter, for the record row (greetd sets it; absent, omitted).
        readonly property string vt: Quickshell.env("XDG_VTNR") || ""

        property bool busy: false
        property bool failed: false
        property bool capsLock: false
        property string message: ""
        property bool leaving: false
        // The password typed for the session being created; handed to greetd only inside
        // onAuthMessage (quickshell 0.3.2 leaks a response given at any other time into
        // the next session).
        property var pending: null

        signal refused()

        // Every key press, from the field and from the page: what it says about the layout
        // and about Caps Lock (Qt shows neither; cage runs ctrl:nocaps, so Caps Lock only
        // lights if that option goes).
        function sawKey(event) {
            const shift = (event.modifiers & Qt.ShiftModifier) !== 0;
            const alt = (event.modifiers & Qt.AltModifier) !== 0;
            // In the chord xkb hands Qt ISO_Next_Group, which Qt has no key for: the
            // modifier keys are also known by their keycodes (Shift 50 62, Alt 64 108).
            const code = event.nativeScanCode;
            const shiftKey = event.key === Qt.Key_Shift || code === 50 || code === 62;
            const altKey = event.key === Qt.Key_Alt || event.key === Qt.Key_Meta || code === 64 || code === 108;
            if ((shiftKey && alt) || (altKey && shift)) {
                if (layouts.length > 1)
                    layoutIndex = -1;
                return;
            }
            const t = event.text;
            if (t.length !== 1 || (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) !== 0)
                return;
            if (t.toUpperCase() !== t.toLowerCase())
                capsLock = (t === t.toUpperCase()) !== shift;
            // AltGr is no Qt modifier: matching the Shift level keeps its characters out.
            const level = shift ? 1 : 0;
            let found = -1;
            for (let i = 0; i < layouts.length; i++) {
                const keys = keyTable[layouts[i]];
                const chars = keys ? keys[code] : undefined;
                if (chars === undefined)
                    return;     // a layout we cannot tell apart on this key
                if (chars[level] === t) {
                    if (found >= 0)
                        return; // two layouts type it alike
                    found = i;
                }
            }
            if (found >= 0)
                layoutIndex = found;
        }

        function submit(password) {
            if (busy || leaving || password === "")
                return;
            if (user === "") {
                fail("No hay ningún usuario con el que entrar");
                return;
            }
            busy = true;
            failed = false;
            message = "";
            pending = password;
            if (demo !== "")
                demoCheck.restart();
            else
                Greetd.createSession(user);
        }

        // Also the way back from a handover that broke: the page shows again, and the
        // wrapper reads "up" rather than a launch that never happened.
        function fail(why) {
            pending = null;
            busy = false;
            failed = true;
            message = why;
            if (leaving) {
                leaving = false;
                fadeOut.stop();
                cover.opacity = 0;
                shell.heartbeat("up");
            }
            refused();
        }

        function start() {
            busy = false;
            leaving = true;
            fadeOut.start();
        }

        function nextUser() {
            if (busy || users.length < 2)
                return;
            userIndex = (userIndex + 1) % users.length;
            failed = false;
            message = "";
        }

        function power(action) {
            if (demo !== "") {
                message = "Demostración: aquí se ejecutaría systemctl " + action;
                return;
            }
            // logind lets the active greeter seat reboot and power off without a password.
            Quickshell.execDetached(["systemctl", action]);
        }
    }

    Connections {
        target: Greetd
        enabled: login.demo === ""

        function onAuthMessage(message, error, responseRequired, echoResponse) {
            if (responseRequired) {
                if (login.pending !== null) {
                    Greetd.respond(login.pending);
                    login.pending = null;
                } else {
                    // A second question (a code, a token): this page only knows passwords.
                    Greetd.cancelSession();
                    login.fail(message !== "" ? message : "El sistema pide algo más que la contraseña");
                }
            } else if (message !== "") {
                // PAM's own lines (faillock's lock, its minutes left): kept for the refusal.
                login.message = login.message === "" ? message : login.message + " " + message;
            }
        }
        // The session is gone: the next attempt creates a new one. greetd's reason is PAM's
        // generic error string (in English); what PAM said during this attempt beats it.
        function onAuthFailure(message) {
            console.info("greeter: greetd refused: " + message);
            login.fail(login.message !== "" ? login.message : login.wrongPassword);
        }
        function onReadyToLaunch() {
            login.start();
        }
        function onError(error) {
            console.warn("greeter: greetd error: " + error);
            Greetd.cancelSession();
            login.fail("greetd no ha podido seguir: " + error);
        }
    }

    Timer {
        id: demoCheck
        interval: 700
        onTriggered: {
            if (login.pending === "error")
                login.fail(login.wrongPassword);
            else if (login.pending === "locked")    // pam_faillock's own words, untranslated
                login.fail("The account is locked due to 3 failed logins. (10 minutes left to unlock)");
            else
                login.start();
            login.pending = null;
        }
    }

    // Human accounts from /etc/passwd (world-readable): uid 1000 to 59999 with a login shell.
    FileView {
        path: "/etc/passwd"
        onLoaded: {
            const found = [];
            for (const line of text().split("\n")) {
                const f = line.split(":");
                const uid = parseInt(f[2]);
                if (f.length >= 7 && uid >= 1000 && uid < 60000 && !/(nologin|false)$/.test(f[6]))
                    found.push({ name: f[0], uid: uid });
            }
            found.sort((a, b) => a.uid - b.uid);
            login.users = found.map(u => u.name);
        }
    }

    FileView {
        id: beat
        path: Quickshell.env("RYCE_GREETER_HEARTBEAT") || ""
        // Written, never read.
        preload: false
        printErrors: false
        blockWrites: true
        atomicWrites: false
    }

    function heartbeat(state) {
        if (beat.path !== "")
            beat.setText(state + "\n");
    }

    SequentialAnimation {
        id: fadeOut
        NumberAnimation { target: cover; property: "opacity"; to: 1; duration: 420; easing.type: Easing.InOutCubic }
        ScriptAction {
            script: {
                if (login.demo !== "") {
                    Qt.quit();
                    return;
                }
                shell.heartbeat("launch");
                Greetd.launch(["start-hyprland"]);
            }
        }
    }

    FloatingWindow {
        id: window
        title: "ryce-greeter"
        implicitWidth: 1920
        implicitHeight: 1080
        color: Look.bg0
        visible: true

        Image {
            anchors.fill: parent
            source: Look.art
            fillMode: Image.PreserveAspectCrop
            sourceSize: Qt.size(1920, 1080)
            asynchronous: true
            visible: status === Image.Ready
        }

        Page {
            id: page
            anchors.fill: parent
            auth: login
            now: clock.date
            focus: true
            opacity: 0
            transform: Translate { id: arrive; x: -14 }

            ParallelAnimation {
                running: true
                NumberAnimation { target: page; property: "opacity"; to: 1; duration: 420; easing.type: Easing.OutCubic }
                NumberAnimation { target: arrive; property: "x"; to: 0; duration: 520; easing.type: Easing.OutCubic }
            }
        }

        // Fades the page to black before greetd starts the session.
        Rectangle {
            id: cover
            anchors.fill: parent
            color: Look.bg0
            opacity: 0
        }

        // Every object in this file, the page and its field included, exists by now: a
        // component that failed to load fails the whole file, and no "up" is ever written.
        Component.onCompleted: {
            if (login.demo === "" && !Greetd.available) {
                console.error("greeter: greetd is not reachable (GREETD_SOCK unset?): no heartbeat, the wrapper falls back");
                return;
            }
            page.forceActiveFocus();
            shell.heartbeat("up");
            if (login.demo === "error" || login.demo === "locked")
                Qt.callLater(() => login.submit(login.demo));
            else if (login.demo === "typing")
                login.capsLock = true;
        }
    }

    SystemClock {
        id: clock
        precision: SystemClock.Minutes
    }
}
