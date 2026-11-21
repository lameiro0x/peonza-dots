import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import Quickshell.Widgets
import qs
import qs as Ryce
import qs.bar

// What Aria plays: the cover, the title in the theme's voice (Ola: its serif), artist
// and album, the transport and a line you can click or drag to seek. The times are a
// readout: Grafito spells the elapsed one in Doto, the others in tabular figures.
ColumnLayout {
    id: now
    required property var player
    required property var api

    readonly property string skin: BarUi.skin
    readonly property var song: player.current
    readonly property var entry: player.pos >= 0 ? player.entries[player.pos] ?? null : null
    readonly property real length: player.duration > 0 ? player.duration : (song?.duration ?? 0)
    property real dragging: -1             // 0..1 while the pointer holds the line
    readonly property real shownTime: dragging >= 0 ? dragging * length : player.time

    function clock(seconds) { return Times.clock(seconds); }

    spacing: 12

    RowLayout {
        Layout.fillWidth: true
        spacing: 16

        ClippingRectangle {
            implicitWidth: 112
            implicitHeight: 112
            Layout.alignment: Qt.AlignTop
            radius: Ryce.Palette.rounding
            color: Ryce.Palette.bg1

            Image {
                id: art
                anchors.fill: parent
                source: now.song ? now.api.coverUrl(now.song.coverArt, 300) : ""
                sourceSize: Qt.size(224, 224)
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: status === Image.Ready
            }
            Label {
                anchors.centerIn: parent
                visible: !art.visible
                text: Ui.music
                color: Ryce.Palette.fg2
                font.family: Ryce.Palette.fontIcon
                font.pixelSize: 32
                elide: Text.ElideNone
            }
            Shape {
                visible: now.skin === "box"
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer

                ShapePath {
                    fillColor: "transparent"
                    strokeColor: Ryce.Palette.line
                    strokeWidth: 1
                    PathRectangle {
                        x: 0.5
                        y: 0.5
                        width: 111
                        height: 111
                        radius: Math.max(0, Ryce.Palette.rounding - 0.5)
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 3

            Label {
                Layout.fillWidth: true
                text: now.song?.title ?? now.entry?.title ?? "Nada en la cola"
                color: Ryce.Palette.fg0
                // Ola's capsules and Papel's page title the song in their display serif.
                font.family: now.skin === "capsule" || BarUi.folio ? Ryce.Palette.fontDisplay : Ryce.Palette.fontUi
                font.pixelSize: now.skin === "capsule" || BarUi.folio ? 24 : Ui.project + 2
                font.weight: now.skin === "bare" ? Font.Medium : Font.Normal
                wrapMode: Text.Wrap
                maximumLineCount: 2
            }
            Label {
                Layout.fillWidth: true
                text: now.song ? [now.song.artist, now.song.album].filter(x => !!x).join(" · ")
                    : now.entry ? "" : "Elige una lista, un álbum o busca"
                color: Ryce.Palette.fg1
                font.pixelSize: Ui.meta + 1
            }
            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: 4

                IconButton {
                    size: 30
                    glyph: Ui.prev
                    enabled: now.player.pos >= 0
                    Accessible.name: "Anterior"
                    onClicked: now.player.prev()
                }
                IconButton {
                    size: 34
                    glyph: now.player.playing ? Ui.pause : Ui.play
                    primary: true
                    enabled: now.player.entries.length > 0
                    Accessible.name: now.player.playing ? "Pausa" : "Reproducir"
                    onClicked: now.player.toggle()
                }
                IconButton {
                    size: 30
                    glyph: Ui.next
                    enabled: now.player.pos >= 0 && now.player.pos < now.player.entries.length - 1
                    Accessible.name: "Siguiente"
                    onClicked: now.player.next()
                }
                Item { Layout.fillWidth: true }
                Tab {
                    text: "aleatorio"
                    small: true
                    on: now.player.shuffled
                    onClicked: now.player.setShuffle(!now.player.shuffled)
                }
            }
        }
    }

    // The progress: a hairline with a generous hit area; click or drag to seek.
    Item {
        visible: now.player.pos >= 0
        Layout.fillWidth: true
        implicitHeight: 14
        enabled: now.length > 0

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
            height: now.skin === "capsule" ? 4 : 2
            radius: height / 2
            color: Ryce.Palette.line
        }
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            height: now.skin === "capsule" ? 4 : 2
            radius: height / 2
            width: now.length > 0 ? parent.width * Math.min(1, now.shownTime / now.length) : 0
            color: Ryce.Palette.hueMedia
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            function at(x) { return Math.max(0, Math.min(1, x / width)); }
            onPressed: m => now.dragging = at(m.x)
            onPositionChanged: m => { if (pressed) now.dragging = at(m.x); }
            onReleased: m => {
                now.player.seek(at(m.x) * now.length);
                now.dragging = -1;
            }
            onCanceled: now.dragging = -1
        }
    }
    RowLayout {
        visible: now.player.pos >= 0
        Layout.fillWidth: true
        Layout.topMargin: now.skin === "bare" ? -2 : -8

        Label {
            // Doto's colon is a dotted dagger: its middle dot reads as the separator (as the bar clock).
            text: now.skin === "bare" ? now.clock(now.shownTime).replace(/:/g, "·") : now.clock(now.shownTime)
            color: now.skin === "bare" ? Ryce.Palette.fg0 : Ryce.Palette.fg2
            font.family: now.skin === "bare" ? Ryce.Palette.fontDisplay : Ryce.Palette.fontUi
            font.pixelSize: now.skin === "bare" ? Math.max(26, Ryce.Palette.fontDisplayMinPx) : Ui.meta
            font.weight: now.skin === "bare" ? Font.Bold : Font.Normal     // Doto's thin dots fall apart
            font.features: { "tnum": 1 }
            elide: Text.ElideNone
        }
        Item { Layout.fillWidth: true }
        Label {
            text: now.length > 0 ? now.clock(now.length) : ""
            color: Ryce.Palette.fg2
            font.pixelSize: Ui.meta
            font.features: { "tnum": 1 }
            elide: Text.ElideNone
        }
    }
}
