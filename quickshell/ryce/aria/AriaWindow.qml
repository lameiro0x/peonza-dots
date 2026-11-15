import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import qs
import qs as Ryce
import qs.bar
import qs.desk
import qs.drawers

// The Aria drawer: a card that comes out from under the bar's right end, in the frame's
// bg0 with the theme's radius (Tinta adds its 1 px line). Now playing on top; below, four
// tabs: the queue, the lists (every song on the server first, then the playlists), the
// albums (newest, random or most played) and a search. A song plays its whole list from
// there; a list's shuffle glyph plays it all in random order. Space plays or pauses, /
// searches, Escape or a click elsewhere closes.
// Built once per screen and never unmapped: hiding a layer window destroys it, and
// building one costs a new surface and render thread on every opening. Closed, it sits
// on the Bottom layer (a mapped Overlay would keep a fullscreen game from direct
// scanout), takes no input and its card is hidden, so nothing in it renders. The window
// starts at the bar's lower edge, so the card slides out from under the bar (the window
// clips it); DrawerMotion runs it on the render thread, and the network waits until it
// is in (`entered`).
PanelWindow {
    id: win
    property bool shown: false
    required property var aria
    signal closeRequested()
    signal entered()
    signal rested()                         // closed and still again
    readonly property bool moving: reveal.running

    readonly property var api: aria.api
    readonly property var lib: aria.library
    readonly property var player: aria.player
    readonly property string skin: BarUi.skin
    readonly property int pad: 20
    readonly property int listHeight: 300
    readonly property int under: Ryce.Palette.gapsOut   // the card's place below the bar
    readonly property bool needsSetup: api.status === "setup" || api.status === "loading"

    // The tabs: 0 queue, 1 lists, 2 albums, 3 search.
    property int tab: 1
    property int searchEpoch: 0            // bumped by `/`: the search field takes the keys
    property var albums: null
    property string albumOrder: "newest"
    property var opened: null              // { title, songs, album } of the list or album shown
    property var results: []
    property string loading: ""            // what is being fetched, for the empty state
    property string failed: ""

    // The lists tab: every song first, then the playlists; one whose songs are all gone
    // from the server sinks to the end, dimmed.
    readonly property var lists: lib.playlists === null ? [] : [{ all: true }].concat(
        lib.playlists.filter(p => !(lib.checked(p) && lib.sizeOf(p) === 0)),
        lib.playlists.filter(p => lib.checked(p) && lib.sizeOf(p) === 0))

    // Only the latest request lands: a slower answer to an older search, or to a list
    // asked for before the tab changed, is dropped instead of overwriting the newer one.
    property int epoch: 0
    function fetch(what, name, params, take) {
        follow(what, (ok, fail) => api.call(name, params, ok, fail), take);
    }
    // `start(ok, fail)` runs the request; `take(answer)` lands only if nothing newer was asked.
    function follow(what, start, take) {
        const mine = ++epoch;
        loading = what;
        failed = "";
        start(r => {
            if (mine !== epoch) return;
            loading = "";
            take(r);
        }, text => {
            if (mine !== epoch) return;
            loading = "";
            failed = text;
        });
    }
    function showTab(i) {
        epoch++;
        tab = i;
        opened = null;
        failed = "";
        loading = "";
        if (i === 1) loadPlaylists();
        if (i === 2 && albums === null) loadAlbums(albumOrder);
    }
    // The queue when something is queued, the lists otherwise.
    function firstTab() { return player.entries.length > 0 ? 0 : 1; }
    // Closed: back to how a fresh drawer opens, while nothing shows. The lists stay (in
    // the library), to show at once next time; `entered` asks for them again.
    function rest() {
        epoch++;
        opened = null;
        results = [];
        albums = null;
        albumOrder = "newest";
        failed = "";
        loading = "";
        tab = firstTab();
    }
    function loadPlaylists() {
        follow(lib.playlists === null ? "playlists" : "", (ok, fail) => lib.loadPlaylists(ok, fail), () => {});
    }
    function loadAlbums(order) {
        albumOrder = order;
        albums = null;
        fetch("albums", "getAlbumList2", { type: order, size: 60 }, r => albums = r.albumList2?.album ?? []);
    }
    function openPlaylist(p) {
        follow("songs", (ok, fail) => lib.songsOf(p, ok, fail), songs => opened = { title: p.name ?? "", songs: songs });
    }
    function openAlbum(a) {
        fetch("songs", "getAlbum", { id: a.id }, r => opened = { title: a.name, songs: r.album?.song ?? [], album: true });
    }
    function openAll() {
        follow("all", everything, songs => opened = { title: "Todas las canciones", songs: songs });
    }
    // Every song, through the library: ok(songs) or fail(why).
    function everything(ok, fail) {
        lib.loadAll(() => lib.all !== null && lib.allFailed === "" ? ok(lib.all) : fail(lib.allFailed || "Aria no devolvió canciones"));
    }
    // Shuffle a list and play it from its first song; the queue tab shows where it went.
    function shuffle(songs) {
        if (songs.length === 0) return;
        aria.play(lib.shuffled(songs), 0);
        showTab(0);
    }
    function shufflePlaylist(p) {
        follow("songs", (ok, fail) => lib.songsOf(p, ok, fail), songs => shuffle(songs));
    }
    function shuffleAll() { follow("all", everything, songs => shuffle(songs)); }
    function search(text) {
        const q = text.trim();
        if (q === "") {
            epoch++;
            results = [];
            loading = "";
            return;
        }
        fetch("search", "search3", { query: q, songCount: 40, albumCount: 0, artistCount: 0 },
            r => results = r.searchResult3?.song ?? []);
    }
    function retry() {
        failed = "";
        api.ping();
        if (tab === 1) loadPlaylists();
        else if (tab === 2) loadAlbums(albumOrder);
    }
    function clock(seconds) { return seconds > 0 ? Times.clock(seconds) : ""; }
    function songs(n) { return n === 1 ? "1 canción" : n + " canciones"; }

    // The header's note: the server, or why it is not there.
    readonly property string tone: player.failure !== "" ? "err"
        : api.status === "denied" ? "err" : api.status === "offline" ? "warn" : ""
    readonly property string note: player.failure !== "" ? player.failure
        : api.status === "offline" || api.status === "denied" ? api.problem
        : api.status === "checking" ? "conectando…"
        : needsSetup ? "sin configurar" : api.host

    anchors { top: true; right: true }
    margins.top: Ryce.Palette.frameTop
    margins.right: Ryce.Palette.frameRim + Ryce.Palette.gapsOut
    implicitWidth: 420
    implicitHeight: under + content.implicitHeight + 2 * pad
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    // Open, only the card takes the pointer: the strip under the bar stays the bar's.
    mask: shown ? cardArea : noInput
    Region { id: noInput }
    Region {
        id: cardArea
        item: card
    }

    WlrLayershell.namespace: "qs-aria"
    // On Overlay from the opening until the card is hidden again: bound to `shown`, a
    // close would drop it to Bottom for a beat before the leave starts.
    WlrLayershell.layer: card.visible ? WlrLayer.Overlay : WlrLayer.Bottom
    WlrLayershell.keyboardFocus: shown ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    onShownChanged: shown ? open() : close()
    // Never opens itself: a window built while its screen is the open one (an output back
    // from a hotplug) asks to close instead of popping a drawer with the keyboard.
    Component.onCompleted: {
        tab = firstTab();
        if (shown) closeRequested();
    }
    // Back from setup or offline: fill the tab that could not load. Closed, it waits for
    // the next opening, which asks anyway.
    Connections {
        target: win.api
        function onStatusChanged() {
            if (win.shown && win.api.status === "ok" && (win.failed !== "" || (win.tab === 1 && win.lib.playlists === null)))
                win.showTab(win.tab);
        }
    }
    function open() {
        card.visible = true;
        // Caught while leaving, it simply turns back; from rest it starts as a fresh drawer
        // (the queue may have filled while closed; the keys go to the card again).
        if (!reveal.leaving) {
            tab = firstTab();
            card.forceActiveFocus();
        }
        reveal.show();
    }
    function close() {
        reveal.hide();
    }

    DrawerMotion {
        id: reveal
        panel: card
        content: content
        // Bottom up: the card comes down out of the bar, so its lower edge shows first.
        tiers: [hint, pane, tabs, now, setup, header]
        vertical: true
        home: win.under
        away: -card.height
        contentHome: win.pad
        lag: 18
        onEntered: if (win.shown) {
            win.entered();
            if (win.tab === 1 && win.opened === null) win.loadPlaylists();
        }
        // Hiding the card also renders the frame that commits the move to Bottom.
        onRested: if (!win.shown) {
            card.visible = false;
            win.rest();
            win.rested();
        }
    }

    // Armed once the drawer is in: the move to Overlay and the keyboard only reach the
    // compositor with the next frame, and a grab that comes first is cleared at once.
    HyprlandFocusGrab {
        active: win.shown && !reveal.arriving
        windows: [win]
        onCleared: win.closeRequested()
    }

    // DrawerMotion owns its y, the content's y and every tier's opacity.
    Item {
        id: card
        visible: false                      // open() and the leave own it
        width: win.width
        height: win.height - win.under
        focus: true

        FrameProbe {
            name: "aria"
            busy: reveal.running
            opening: win.shown
            since: win.aria.toggledAt
        }

        Keys.onEscapePressed: win.closeRequested()
        Keys.onPressed: event => {
            if (win.needsSetup) return;
            if (event.key === Qt.Key_Space) {
                win.player.toggle();
                event.accepted = true;
            } else if (event.key === Qt.Key_Slash) {
                if (win.tab !== 3 || win.opened !== null) win.showTab(3);
                win.searchEpoch++;
                event.accepted = true;
            }
        }

        Rectangle {
            visible: win.skin !== "box"
            anchors.fill: parent
            radius: Ryce.Palette.rounding
            color: Ryce.Palette.bg0
        }
        // Tinta: smoked glass in a 1 px line, as its bar boxes are drawn. Darker than the
        // theme's panel alpha: lists are read here, over a desk HUD that is all text too.
        Shape {
            visible: win.skin === "box"
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer

            ShapePath {
                fillColor: Ryce.Palette.rgba(Ryce.Palette.bg0, Math.max(0.985, Ryce.Palette.alphaPanel))
                strokeColor: Ryce.Palette.line
                strokeWidth: 1
                PathRectangle {
                    x: 0.5
                    y: 0.5
                    width: card.width - 1
                    height: card.height - 1
                    radius: Math.max(0, Ryce.Palette.rounding - 0.5)
                }
            }
        }

        ColumnLayout {
            id: content
            x: win.pad
            width: card.width - 2 * win.pad
            spacing: 16

            SectionRule {
                id: header
                Layout.fillWidth: true
                label: "aria"
                meta: win.note
                metaMax: 300
                metaColor: win.tone === "err" ? Ryce.Palette.err : win.tone === "warn" ? Ryce.Palette.warn : Ryce.Palette.fg2
            }

            Setup {
                id: setup
                visible: win.needsSetup
                Layout.fillWidth: true
                api: win.api
            }

            NowPlaying {
                id: now
                visible: !win.needsSetup
                Layout.fillWidth: true
                player: win.player
                api: win.api
            }

            RowLayout {
                id: tabs
                visible: !win.needsSetup
                Layout.fillWidth: true
                spacing: win.skin === "bare" ? 2 : 6

                Repeater {
                    model: ["Cola", "Listas", "Álbumes", "Buscar"]

                    Tab {
                        required property string modelData
                        required property int index
                        text: modelData
                        on: win.tab === index
                        onClicked: win.showTab(index)
                    }
                }
                Item { Layout.fillWidth: true }
            }

            Loader {
                id: pane
                visible: !win.needsSetup
                active: !win.needsSetup
                Layout.fillWidth: true
                Layout.preferredHeight: win.listHeight
                sourceComponent: win.opened !== null ? songsPane
                    : [queuePane, listsPane, albumsPane, searchPane][win.tab]
            }

            Label {
                id: hint
                visible: !win.needsSetup
                Layout.fillWidth: true
                Layout.topMargin: -6
                text: "espacio reproduce · / busca · esc cierra"
                color: Ryce.Palette.fg2
                font.pixelSize: Ui.meta - 1
                horizontalAlignment: Text.AlignRight
            }
        }
    }

    // A list, or in its place one calm line: loading, empty or why it failed (+ retry).
    component Pane: Item {
        id: pane
        property alias model: list.model
        property alias delegate: list.delegate
        property alias list: list
        property string empty: ""
        readonly property bool blank: list.count === 0

        ListView {
            id: list
            anchors.fill: parent
            clip: true
            spacing: 2
            boundsBehavior: Flickable.StopAtBounds
            visible: !pane.blank
        }
        ColumnLayout {
            visible: pane.blank
            anchors.centerIn: parent
            width: parent.width - 40
            spacing: 12

            Label {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: win.failed !== "" ? win.failed : win.loading !== "" ? "Cargando…" : pane.empty
                color: win.failed !== "" ? Ryce.Palette.warn : Ryce.Palette.fg2
                wrapMode: Text.Wrap
                maximumLineCount: 3
            }
            Tab {
                visible: win.failed !== ""
                Layout.alignment: Qt.AlignHCenter
                text: "Reintentar"
                onClicked: win.retry()
            }
        }
    }

    Component {
        id: queuePane

        Pane {
            id: queue
            model: win.player.entries
            empty: "La cola está vacía"
            function center() { if (win.player.pos > 2) list.positionViewAtIndex(win.player.pos, ListView.Center); }
            Component.onCompleted: center()
            Connections {
                target: win
                function onShownChanged() { if (win.shown) queue.center(); }
            }
            delegate: Track {
                required property var modelData
                required property int index
                readonly property var song: win.player.songs[win.player.ids[index]] ?? null
                width: ListView.view.width
                lead: String(index + 1)
                title: song?.title ?? modelData.title ?? "Sin título"
                sub: song?.artist ?? ""
                trail: win.clock(song?.duration)
                current: index === win.player.pos
                onClicked: win.player.jump(index)
            }
        }
    }
    // Every song first; each playlist with the size its songs give once checked (the
    // server's own count until then), and the shuffle glyph at its end.
    Component {
        id: listsPane

        Pane {
            model: win.lists
            empty: "No hay listas"
            delegate: Track {
                required property var modelData
                readonly property bool all: modelData.all === true
                readonly property int size: all ? (win.lib.all?.length ?? -1) : win.lib.sizeOf(modelData)
                readonly property bool gone: !all && win.lib.checked(modelData) && size === 0
                width: ListView.view.width
                glyph: true
                lead: all ? Ui.library : String.fromCodePoint(0xf0cb8)      // md-playlist_music
                title: all ? "Todas las canciones" : modelData.name ?? ""
                sub: gone ? "Vacía: sus canciones ya no están en Aria"
                    : all ? (size >= 0 ? win.songs(size) : "Toda la biblioteca")
                    : win.songs(size)
                trail: all || gone ? "" : win.clock(modelData.duration)
                muted: gone
                action: gone ? "" : Ui.shuffle
                actionName: "Aleatorio"
                onClicked: all ? win.openAll() : win.openPlaylist(modelData)
                onActionClicked: all ? win.shuffleAll() : win.shufflePlaylist(modelData)
            }
        }
    }
    Component {
        id: albumsPane

        ColumnLayout {
            spacing: 8

            RowLayout {
                spacing: 6
                Repeater {
                    model: [["newest", "recientes"], ["random", "al azar"], ["frequent", "más oídos"]]

                    Tab {
                        required property var modelData
                        small: true
                        text: modelData[1]
                        on: win.albumOrder === modelData[0]
                        onClicked: win.loadAlbums(modelData[0])
                    }
                }
            }
            Pane {
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: win.albums ?? []
                empty: "No hay álbumes"
                delegate: Track {
                    required property var modelData
                    width: ListView.view.width
                    cover: win.api.coverUrl(modelData.coverArt, 80)
                    title: modelData.name ?? ""
                    sub: [modelData.artist, modelData.year].filter(x => !!x).join(" · ")
                    trail: modelData.songCount ? modelData.songCount + (modelData.songCount === 1 ? " pista" : " pistas") : ""
                    onClicked: win.openAlbum(modelData)
                }
            }
        }
    }
    Component {
        id: searchPane

        ColumnLayout {
            spacing: 8

            Field {
                id: query
                Layout.fillWidth: true
                placeholder: "Canción, artista o álbum"
                onTextChanged: debounce.restart()
                onAccepted: {
                    debounce.stop();
                    win.search(text);
                }
                Component.onCompleted: input.forceActiveFocus()
                input.Keys.onEscapePressed: win.closeRequested()
                Connections {
                    target: win
                    function onSearchEpochChanged() { query.input.forceActiveFocus(); }
                }
                Timer {
                    id: debounce
                    interval: 300
                    onTriggered: win.search(query.text)
                }
            }
            Pane {
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: win.results
                empty: query.text.trim() === "" ? "Escribe para buscar en Aria" : "Nada coincide"
                delegate: Track {
                    required property var modelData
                    required property int index
                    width: ListView.view.width
                    lead: String(index + 1)
                    title: modelData.title ?? ""
                    sub: [modelData.artist, modelData.album].filter(x => !!x).join(" · ")
                    trail: win.clock(modelData.duration)
                    current: modelData.id === win.player.currentId
                    onClicked: win.aria.play(win.results, index)
                }
            }
        }
    }
    // A list or an album opened: back, its size and «aleatorio» on top, then its songs.
    Component {
        id: songsPane

        ColumnLayout {
            spacing: 6

            Track {
                Layout.fillWidth: true
                glyph: true
                lead: String.fromCodePoint(0xf0141)      // md-chevron_left
                title: win.opened?.title ?? ""
                sub: win.songs(win.opened?.songs.length ?? 0) + " · volver"
                action: (win.opened?.songs.length ?? 0) > 1 ? Ui.shuffle : ""
                actionName: "Aleatorio"
                onClicked: win.opened = null
                onActionClicked: win.shuffle(win.opened.songs)
            }
            Pane {
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: win.opened?.songs ?? []
                empty: "Sin canciones"
                delegate: Track {
                    required property var modelData
                    required property int index
                    width: ListView.view.width
                    // An album numbers its tracks; a list, its own order.
                    lead: String(win.opened?.album ? modelData.track ?? index + 1 : index + 1)
                    title: modelData.title ?? ""
                    sub: modelData.artist ?? ""
                    trail: win.clock(modelData.duration)
                    current: modelData.id === win.player.currentId
                    onClicked: win.aria.play(win.opened.songs, index)
                }
            }
        }
    }
}
