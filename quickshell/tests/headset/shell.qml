import QtQuick
import Quickshell
import Quickshell.Bluetooth

// Headless tests for the headset's state machine (HeadsetLogic.qml) and its OSD's life
// (HeadsetOsdLife.qml), against stand-ins that behave like Quickshell 0.3.2's Bluetooth
// objects. quickshell/tests/test_headset.py copies both files next to this one and runs
//   QT_QPA_PLATFORM=offscreen qs -p <that folder>
// Prints one `FAIL <scenario>: <what>` per broken check, then `DONE checks=N failures=M`,
// and exits 1 on any failure.
ShellRoot {
    id: t

    property var lg: null                    // the logic under test
    property var ad: null                    // its adapter
    property var dv: []                      // its devices
    property var ol: null                    // an OSD life under test
    property var remembered: []
    property string scenario: ""
    property int checks: 0
    property int failures: 0
    property var queue: []
    property var current: null
    property bool connectedFirst: false     // how the fake devices order their notifications
    property int pass: 1

    readonly property int settleMs: 400
    readonly property int forgetMs: 250
    readonly property int powerUpMs: 80
    readonly property int againMs: 80
    readonly property int retryMs: 100
    readonly property int powerWaitMs: 150
    readonly property int holdMs: 150
    readonly property int failHoldMs: 300

    Component { id: logicC; HeadsetLogic {} }
    Component { id: deviceC; FakeDevice {} }
    Component { id: adapterC; FakeAdapter {} }
    Component { id: lifeC; HeadsetOsdLife {} }

    function check(ok, what) {
        checks++;
        if (!ok) {
            failures++;
            console.log(`FAIL [pass ${pass}] ${scenario}: ${what}`);
        }
    }
    function at(ms, fn) {
        queue.push({ ms: ms, fn: fn });
    }
    function scenario_(name, build) {
        at(0, () => {
            t.scenario = name;
            console.log(`SCENARIO [pass ${t.pass}] ${name}`);
        });
        build();
    }

    // A fresh world: an adapter, devices from plain option objects, the logic over them.
    function fresh(devices, adapter) {
        for (const o of [lg, ad, ol, ...dv]) if (o) o.destroy();
        ol = null;
        ad = adapter === null ? null : adapterC.createObject(t, adapter ?? {});
        if (ad) ad.writes = 0;              // setting the initial `enabled` is not a write
        dv = devices.map((o, i) => device(Object.assign({ address: `00:00:00:00:00:0${i + 1}` }, o)));
        remembered = [];
        lg = logicC.createObject(t, {
            adapter: ad, devices: dv,
            settleMs: settleMs, forgetMs: forgetMs, powerUpMs: powerUpMs, againMs: againMs,
            retryMs: retryMs, powerWaitMs: powerWaitMs
        });
        lg.remember.connect(address => {
            t.remembered.push(address);
            t.lg.last = address;
        });
    }
    function device(props) {
        return deviceC.createObject(t, Object.assign({ connectedFirst: t.connectedFirst }, props));
    }
    function life(props) {
        if (ol) ol.destroy();
        ol = lifeC.createObject(t, Object.assign({ holdMs: holdMs, failHoldMs: failHoldMs }, props ?? {}));
        return ol;
    }
    readonly property var connectedDevice: ({ connected: true, state: BluetoothDeviceState.Connected })

    function next() {
        if (queue.length === 0) {
            console.log(`DONE checks=${checks} failures=${failures}`);
            Qt.exit(failures > 0 ? 1 : 0);
            return;
        }
        const step = queue.shift();
        current = step.fn;
        tick.interval = Math.max(1, step.ms);
        tick.start();
    }
    Timer {
        id: tick
        onTriggered: {
            try {
                t.current();
            } catch (e) {
                t.failures++;
                console.log(`FAIL [pass ${t.pass}] ${t.scenario}: threw ${e}`);
            }
            t.next();
        }
    }

    function build() {
        // ---- the state machine -------------------------------------------------------
        scenario_("connect succeeds", () => {
            at(0, () => {
                fresh([{}]);
                check(lg.word === "desconectado", `starts «desconectado», got «${lg.word}»`);
                lg.toggle();
                check(lg.busy, "busy right after the press");
                check(lg.word === "conectando…", `«conectando…», got «${lg.word}»`);
                check(dv[0].connects === 1, `one connect, got ${dv[0].connects}`);
            });
            at(30, () => {
                dv[0].linkUp();
                check(!lg.busy, "settled once the link is up");
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
                check(!lg.failed, "not failed");
            });
            at(10, () => check(remembered.length === 1 && remembered[0] === dv[0].address, "the device is remembered"));
        });

        scenario_("connect fails (headset off)", () => {
            at(0, () => { fresh([{}]); lg.toggle(); });
            at(30, () => {
                dv[0].refused();
                check(lg.failed, "failed");
                check(!lg.busy, "not busy after the failure");
                check(lg.word === "no responde", `«no responde», got «${lg.word}»`);
            });
            at(forgetMs + 60, () => {
                check(!lg.failed, "the failure is forgotten after forgetMs");
                check(lg.word === "desconectado", `back to «desconectado», got «${lg.word}»`);
            });
        });

        scenario_("a refused connect, then the headset connects by itself", () => {
            at(0, () => { fresh([{}]); lg.toggle(); dv[0].refused(); check(lg.failed, "failed first"); });
            at(30, () => {
                dv[0].linkUp();
                check(!lg.failed, "a link that comes up clears the failure");
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
            });
        });

        scenario_("disconnect", () => {
            at(0, () => {
                fresh([connectedDevice]);
                check(lg.word === "conectado", `starts «conectado», got «${lg.word}»`);
                lg.toggle();
                check(lg.word === "desconectando…", `«desconectando…», got «${lg.word}»`);
                check(dv[0].disconnects === 1, "one disconnect");
            });
            at(30, () => {
                dv[0].linkDown();
                check(!lg.busy, "settled");
                check(lg.word === "desconectado", `«desconectado», got «${lg.word}»`);
                check(!lg.failed, "a disconnect never fails");
            });
        });

        scenario_("a refused disconnect", () => {
            at(0, () => { fresh([connectedDevice]); lg.toggle(); });
            at(30, () => {
                dv[0].refused();
                check(!lg.busy, "not left «desconectando…» (adversary A3)");
                check(lg.pending === "", `pending cleared, got «${lg.pending}»`);
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
            });
        });

        scenario_("reconnect while connected (SUPER+b)", () => {
            at(0, () => {
                fresh([connectedDevice]);
                lg.reconnect();
                check(lg.busy, "busy");
                check(lg.word === "reconectando…", `«reconectando…», got «${lg.word}»`);
                check(dv[0].disconnects === 1 && dv[0].connects === 0, "the disconnect half first");
            });
            at(30, () => {
                dv[0].linkDown();
                check(lg.busy, "still busy between the halves");
                check(lg.word === "reconectando…", `still «reconectando…», got «${lg.word}»`);
                check(dv[0].connects === 0, "no connect before againMs");
            });
            at(againMs + 60, () => {
                check(dv[0].connects === 1, `the connect half, got ${dv[0].connects}`);
                check(lg.word === "reconectando…", `«reconectando…» while connecting, got «${lg.word}»`);
            });
            at(30, () => {
                dv[0].linkUp();
                check(!lg.busy, "settled");
                check(!lg.reconnecting, "the reconnect is over");
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
            });
        });

        scenario_("reconnect while disconnected is a connect", () => {
            at(0, () => {
                fresh([{}]);
                lg.reconnect();
                check(dv[0].connects === 1 && dv[0].disconnects === 0, "a plain connect");
                check(lg.word === "conectando…", `«conectando…», got «${lg.word}»`);
            });
            at(30, () => { dv[0].linkUp(); check(lg.word === "conectado", `«conectado», got «${lg.word}»`); });
        });

        scenario_("a reconnect whose connect half is refused once", () => {
            at(0, () => { fresh([connectedDevice]); lg.reconnect(); });
            at(30, () => dv[0].linkDown());
            at(againMs + 60, () => {
                dv[0].refused();
                check(!lg.failed && lg.busy, "not given up after one refusal (adversary 3 M1)");
                check(lg.word === "reconectando…", `«reconectando…», got «${lg.word}»`);
            });
            at(retryMs + 60, () => {
                check(dv[0].connects === 2, `tried once more, got ${dv[0].connects}`);
                dv[0].linkUp();
                check(lg.word === "conectado" && !lg.busy, `«conectado», got «${lg.word}»`);
            });
        });

        scenario_("a reconnect whose connect half is refused twice", () => {
            at(0, () => { fresh([connectedDevice]); lg.reconnect(); });
            at(30, () => dv[0].linkDown());
            at(againMs + 60, () => dv[0].refused());
            at(retryMs + 60, () => {
                dv[0].refused();
                check(lg.failed, "failed after the second refusal");
                check(!lg.reconnecting && !lg.busy, "the reconnect is over");
                check(lg.word === "no responde", `«no responde», got «${lg.word}»`);
                check(dv[0].connects === 2, `two tries, got ${dv[0].connects}`);
            });
        });

        scenario_("adapter off: switched on, then connected", () => {
            at(0, () => {
                fresh([{}], { state: BluetoothAdapterState.Disabled, enabled: false });
                lg.toggle();
                check(ad.enabled && ad.writes === 1, "the adapter is switched on");
                check(dv[0].connects === 1, "a first connect goes anyway");
            });
            at(30, () => {
                dv[0].refused();     // NotReady: the adapter is not up yet
                check(!lg.failed, "not a failure while the adapter powers up");
                check(lg.busy, "still busy");
                check(lg.word === "conectando…", `«conectando…», got «${lg.word}»`);
                ad.state = BluetoothAdapterState.Enabled;
                check(dv[0].connects === 1, "no connect before powerUpMs");
            });
            at(powerUpMs + 60, () => {
                check(dv[0].connects === 2, `connected again once powered, got ${dv[0].connects}`);
                dv[0].linkUp();
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
            });
        });

        scenario_("adapter off and the headset unreachable", () => {
            at(0, () => {
                fresh([{}], { state: BluetoothAdapterState.Disabled, enabled: false });
                lg.toggle();
                dv[0].refused();
                ad.state = BluetoothAdapterState.Enabled;
            });
            at(powerUpMs + 60, () => {
                dv[0].refused();
                check(lg.failed, "the second refusal is a failure");
                check(!lg.busy, "not busy");
            });
        });

        scenario_("an adapter still powering up (after a hibernation)", () => {
            at(0, () => {
                fresh([{}], { state: BluetoothAdapterState.Enabling, enabled: true });
                lg.toggle();
                check(ad.writes === 0, "nothing to write: it is on its way");
                dv[0].refused();
                check(!lg.failed && lg.busy, "NotReady while Enabling is not a failure (adversary 3 L5)");
                ad.state = BluetoothAdapterState.Enabled;
            });
            at(powerUpMs + 60, () => {
                check(dv[0].connects === 2, `tried again once on, got ${dv[0].connects}`);
                dv[0].linkUp();
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
            });
        });

        scenario_("an adapter stuck in Enabling (quickshell#1372)", () => {
            at(0, () => {
                fresh([{}], { state: BluetoothAdapterState.Enabling, enabled: true });
                lg.toggle();
                dv[0].refused();
            });
            at(powerWaitMs + 60, () => {
                check(dv[0].connects === 2, `tried as things are after powerWaitMs, got ${dv[0].connects}`);
                dv[0].refused();
                check(lg.failed, "then a refusal fails, well before settleMs (adversary A4)");
            });
        });

        scenario_("Bluetooth blocked (rfkill)", () => {
            at(0, () => {
                fresh([{}], { state: BluetoothAdapterState.Blocked, enabled: false });
                lg.toggle();
                lg.reconnect();
                check(dv[0].connects === 0 && ad.writes === 0, "nothing is tried");
                check(!lg.busy, "not busy");
                check(lg.word === "Bluetooth desactivado", `«Bluetooth desactivado», got «${lg.word}»`);
            });
        });

        scenario_("no adapter at all", () => {
            at(0, () => {
                fresh([{}], null);
                check(!lg.present, "not present");
                check(lg.word === "sin Bluetooth", `«sin Bluetooth», got «${lg.word}»`);
                lg.toggle();
                lg.reconnect();
                check(dv[0].connects === 0, "nothing is tried");
            });
        });

        scenario_("nothing paired that plays sound", () => {
            at(0, () => {
                fresh([{ paired: false }, { icon: "input-mouse" }, { icon: "phone" }]);
                check(lg.device === null, "no candidate");
                check(lg.word === "sin emparejar", `«sin emparejar», got «${lg.word}»`);
                lg.toggle();
                check(dv.every(d => d.connects === 0), "nothing is tried");
            });
        });

        scenario_("which device: connected, then last, then first", () => {
            at(0, () => {
                fresh([{ name: "uno" }, { name: "dos", icon: "audio-card" }]);
                check(lg.device === dv[0], "the first when nothing else says");
                lg.last = dv[1].address;
                check(lg.device === dv[1], "the last connected");
                dv[0].linkUp();
                check(lg.device === dv[0], "the connected one");
            });
            at(10, () => {
                check(lg.last === dv[0].address, "and it becomes the last");
                dv[0].linkDown();
                check(lg.device === dv[0], "still the last one after it disconnects");
            });
        });

        scenario_("a reconnect keeps its device", () => {
            at(0, () => {
                fresh([{ name: "dos" }, Object.assign({ name: "uno" }, connectedDevice)]);
                lg.last = "";
                check(lg.device === dv[1], "the connected one");
                lg.reconnect();
            });
            at(30, () => {
                dv[1].linkDown();
                check(lg.device === dv[1], "pinned between the halves (the first would win otherwise)");
            });
            at(againMs + 60, () => {
                check(dv[1].connects === 1 && dv[0].connects === 0, "the same device is connected again");
                dv[1].linkUp();
            });
            at(10, () => {
                check(lg.target === "", "released once answered");
            });
        });

        scenario_("a press while busy is ignored", () => {
            at(0, () => {
                fresh([{}]);
                lg.toggle();
                lg.toggle();
                lg.reconnect();
                check(dv[0].connects === 1 && dv[0].disconnects === 0, "one connect, nothing else");
                fresh([connectedDevice]);
                lg.toggle();
                lg.toggle();
                lg.reconnect();
                check(dv[0].disconnects === 1 && lg.pending === "off", `one disconnect while disconnecting, got ${dv[0].disconnects} «${lg.pending}»`);
                fresh([connectedDevice]);
                lg.reconnect();
                lg.reconnect();
                lg.toggle();
                check(dv[0].disconnects === 1 && lg.pending === "re", `one reconnect at a time, got ${dv[0].disconnects} «${lg.pending}»`);
            });
        });

        scenario_("no answer at all", () => {
            at(0, () => { fresh([{}]); lg.toggle(); });
            at(settleMs + 60, () => {
                check(lg.failed, "failed after settleMs");
                check(lg.pending === "", "nothing pending");
                check(lg.word === "no responde", `«no responde», got «${lg.word}»`);
                dv[0].refused();    // QtDBus's own timeout reaches Quickshell later (25 s)
                check(!lg.busy, "not busy once the call is answered (adversary 2 L5)");
            });
        });

        scenario_("the device goes away mid-press and never comes back", () => {
            at(0, () => {
                fresh([{}]);
                lg.toggle();
                lg.devices = [];
                check(lg.busy, "the press waits for its device");
                check(lg.word === "conectando…", `«conectando…», got «${lg.word}»`);
            });
            at(settleMs + 60, () => {
                check(lg.failed && !lg.busy, "settle ends it as a failure");
                check(lg.word === "no responde", `«no responde», got «${lg.word}»`);
            });
        });

        scenario_("a reconnect across a re-registration (hci0 → hci1)", () => {
            at(0, () => {
                fresh([connectedDevice]);
                lg.reconnect();
            });
            at(30, () => {
                dv[0].linkDown();
                lg.devices = [];            // the controller goes away mid-reconnect
                lg.adapter = null;
                check(lg.busy, "still busy while the controller is away");
                check(lg.word === "reconectando…", `«reconectando…», got «${lg.word}»`);
            });
            at(againMs + 60, () => {
                check(lg.reconnecting && lg.pending === "re", "the press is still alive");
                const fresh2 = device({ address: "00:00:00:00:00:01" });
                lg.adapter = ad;
                lg.devices = [fresh2];      // back as a new object with the same address
                dv = [fresh2];
                check(lg.device === fresh2, "the press follows the address to the new object");
            });
            at(againMs + 60, () => {
                check(dv[0].connects === 1, `the new object is connected, got ${dv[0].connects}`);
                dv[0].linkUp();
                check(!lg.busy && !lg.failed, "answered");
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
            });
        });

        scenario_("a connect across a re-registration", () => {
            at(0, () => {
                fresh([{}]);
                lg.toggle();
                lg.devices = [];
                check(!lg.failed, "the device going away is not a failure");
            });
            at(30, () => {
                const fresh2 = device({ address: "00:00:00:00:00:01" });
                lg.devices = [fresh2];
                dv = [fresh2];
            });
            at(againMs + 60, () => {
                check(dv[0].connects === 1, `connected on the new object, got ${dv[0].connects}`);
                dv[0].linkUp();
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
            });
        });

        scenario_("a refused disconnect half of a reconnect", () => {
            at(0, () => {
                fresh([connectedDevice]);
                lg.reconnect();
                dv[0].refused();            // Disconnecting → Connected: nothing happened
                check(lg.failed, "a reconnect that could not disconnect failed (adversary 2 L4)");
                check(!lg.busy && dv[0].connects === 0, "answered, nothing else tried");
                check(lg.word === "no responde", `«no responde», got «${lg.word}»`);
            });
        });

        scenario_("the headset reconnects by itself during a reconnect", () => {
            at(0, () => {
                fresh([connectedDevice]);
                lg.reconnect();
            });
            at(30, () => {
                dv[0].linkDown();
                dv[0].linkUp();             // before againMs
                check(!lg.busy && !lg.failed, "a success");
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
            });
            at(againMs + 60, () => check(dv[0].connects === 0, "no extra connect"));
        });

        scenario_("a stale «on» on an adapter that is off (quickshell#1372)", () => {
            at(0, () => {
                fresh([{}], { state: BluetoothAdapterState.Disabled, enabled: true });
                lg.toggle();
                check(ad.writes === 2 && ad.enabled, `written off then on, got ${ad.writes} writes (adversary 2)`);
                dv[0].refused();
                check(!lg.failed && lg.busy, "waits for the power-up");
                ad.state = BluetoothAdapterState.Enabled;
            });
            at(powerUpMs + 60, () => {
                check(dv[0].connects === 2, `tried again once powered, got ${dv[0].connects}`);
                dv[0].linkUp();
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
            });
        });

        scenario_("NotReady arrives after the adapter is up", () => {
            at(0, () => {
                fresh([{}], { state: BluetoothAdapterState.Disabled, enabled: false });
                lg.toggle();
                ad.state = BluetoothAdapterState.Enabled;
                dv[0].refused();            // the refusal of the first connect comes late
                check(!lg.failed, "not a failure (adversary 2 L7)");
            });
            at(powerUpMs + 60, () => {
                check(dv[0].connects === 2, `tried again, got ${dv[0].connects}`);
                dv[0].linkUp();
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
            });
        });

        scenario_("two devices: a failed press while the other connects by itself", () => {
            at(0, () => {
                fresh([{ name: "uno" }, { name: "dos" }]);
                lg.last = dv[0].address;
                lg.toggle();                // acts on «uno»
                dv[1].linkUp();             // «dos» connects by itself meanwhile
                check(lg.device === dv[0], "the press stays on its device");
                dv[0].refused();
                check(lg.failed, "«uno» failed");
            });
            at(30, () => {
                check(lg.device === dv[1], "then the connected one is shown");
                check(lg.linkState === BluetoothDeviceState.Connected, "its state is not stale (adversary 2 M1)");
                check(lg.word === "conectado", `«conectado», got «${lg.word}»`);
                check(remembered.includes(dv[1].address), "and remembered");
            });
        });

        scenario_("battery", () => {
            at(0, () => {
                fresh([Object.assign({ batteryAvailable: true, battery: 0.4 }, connectedDevice)]);
                check(lg.batteryLevel === 40, `40, got ${lg.batteryLevel}`);
                check(!lg.low, "40 % is not low");
                dv[0].battery = 0.15;
                check(lg.low, "15 % is low");
                dv[0].battery = 0.16;
                check(!lg.low, "16 % is not low");
                dv[0].linkDown();
                check(lg.batteryLevel === -1, `-1 once disconnected, got ${lg.batteryLevel}`);
                fresh([connectedDevice]);
                check(lg.batteryLevel === -1, `-1 when not reported, got ${lg.batteryLevel}`);
            });
        });

        scenario_("the last device is written only when it changes", () => {
            at(0, () => {
                fresh([{}]);
                lg.last = dv[0].address;
                lg.toggle();
                dv[0].linkUp();
            });
            at(10, () => check(remembered.length === 0, `no write, got ${remembered.length}`));
        });

        scenario_("a reconnect whose device comes back already connected", () => {
            at(0, () => {
                fresh([connectedDevice]);
                lg.reconnect();
                lg.devices = [];            // the controller goes away before any linkDown
                lg.adapter = null;
            });
            at(30, () => {
                const back = device(Object.assign({ address: "00:00:00:00:00:01" }, connectedDevice));
                lg.adapter = ad;
                lg.devices = [back];
                dv = [back];
                check(!lg.failed, "a device back and connected is a success (adversary 3 L3)");
                check(!lg.busy && lg.word === "conectado", `«conectado», got «${lg.word}»`);
            });
        });

        scenario_("two connected: the last one used is the one", () => {
            at(0, () => {
                fresh([Object.assign({ name: "altavoz", icon: "audio-card" }, connectedDevice),
                       Object.assign({ name: "cascos" }, connectedDevice)]);
                lg.last = dv[1].address;
                check(lg.device === dv[1], "the last used, not the list's first (adversary 3 L7)");
            });
        });

        // ---- the OSD's life ------------------------------------------------------------
        scenario_("OSD: a peek shows, then hides", () => {
            at(0, () => { life({ armed: true }).announce(); check(ol.shown, "shown"); });
            at(holdMs + 60, () => check(!ol.shown, "hidden after holdMs"));
        });

        scenario_("OSD: kept while the press is in flight", () => {
            at(0, () => { life({ armed: true, busy: true }).announce(); });
            at(holdMs + 100, () => { check(ol.shown, "still shown while busy"); ol.busy = false; });
            at(holdMs - 60, () => check(ol.shown, "held for holdMs after the outcome"));
            at(120, () => check(!ol.shown, "then hidden"));
        });

        scenario_("OSD: a failure is held longer", () => {
            at(0, () => { life({ armed: true, busy: true }).announce(); ol.failed = true; ol.busy = false; });
            at(holdMs + 50, () => check(ol.shown, "still shown past holdMs"));
            at(failHoldMs - holdMs + 50, () => check(!ol.shown, "hidden after failHoldMs"));
        });

        scenario_("OSD: only on the focused screen", () => {
            at(0, () => {
                life({ armed: false }).announce();
                check(!ol.shown, "not shown when not armed");
                ol.armed = true;
                ol.busy = true;
                ol.announce();
                ol.armed = false;
                ol.announce();      // a second press after the focus moved
                check(!ol.shown, "the old screen lets go (adversary A8)");
            });
        });

        scenario_("OSD: never over the sidebar", () => {
            at(0, () => {
                life({ armed: true, sidebarOpen: true }).announce();
                check(!ol.shown, "not shown over an open sidebar");
                ol.sidebarOpen = false;
                ol.busy = true;
                ol.announce();
                check(ol.shown, "shown");
                ol.sidebarOpen = true;
                check(!ol.shown, "the sidebar opening hides it (adversary A5)");
            });
        });

        scenario_("OSD: the newest of the two drawers wins", () => {
            at(0, () => {
                life({ armed: true }).announce();
                check(ol.shown, "shown");
                ol.yielding = true;         // the volume OSD came out at the same spot
                check(!ol.shown, "yields to the volume OSD (adversary 3 L4)");
                ol.announce();              // a press while the volume OSD is out
                check(ol.shown, "a newer press shows it again");
            });
        });

        scenario_("OSD + logic: a failed connect is held for failHoldMs", () => {
            at(0, () => {
                fresh([{}]);
                life({ armed: true });
                ol.busy = Qt.binding(() => t.lg.busy);
                ol.failed = Qt.binding(() => t.lg.failed);
                lg.toggle();
                ol.announce();
                dv[0].refused();
            });
            at(holdMs + 50, () => check(ol.shown, "the failure sees `failed` before `busy` drops (adversary A6)"));
            at(failHoldMs - holdMs + 50, () => check(!ol.shown, "hidden after failHoldMs"));
        });

    }

    Component.onCompleted: {
        build();
        at(0, () => {
            t.connectedFirst = true;
            t.pass = 2;
        });
        build();
        next();
    }
}
