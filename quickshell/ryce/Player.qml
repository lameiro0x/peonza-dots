import QtQuick
import QtQuick.Layouts
import Quickshell.Services.Mpris
import Quickshell.Widgets
import qs
import qs as Ryce

// The player Players.qml names (playing, else the last one that played, else a paused
// one — Aria's mpv or Feishin alike): cover, track, transport, progress. The sidebar hides
// this row while no player exists.
RowLayout {
    id: root
    property bool active

    readonly property MprisPlayer player: Ryce.Players.player
    readonly property bool hasTrack: player !== null && player.trackTitle !== ""
    readonly property bool hasLength: player !== null && player.lengthSupported && player.length > 0

    function clock(seconds) {
        const s = Math.max(0, Math.floor(seconds));
        return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
    }

    spacing: 16

    // MPRIS position does not update by itself: nudge it once a second while it matters.
    Timer {
        running: root.active && root.player !== null && root.player.isPlaying
        interval: 1000
        repeat: true
        onTriggered: root.player.positionChanged()
    }

    ClippingRectangle {
        implicitWidth: 76
        implicitHeight: 76
        Layout.alignment: Qt.AlignTop
        radius: Ryce.Palette.rounding
        color: Ryce.Palette.bg1

        Image {
            id: art
            anchors.fill: parent
            source: root.player ? root.player.trackArtUrl : ""
            sourceSize: Qt.size(152, 152)
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
            font.pixelSize: 24
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignTop
        spacing: 2

        Label {
            Layout.fillWidth: true
            text: root.hasTrack ? root.player.trackTitle : "Sin título"
            color: Ryce.Palette.fg0
            font.pixelSize: Ui.project
        }
        Label {
            Layout.fillWidth: true
            text: root.player ? (root.player.trackArtist || root.player.identity) : ""
            font.pixelSize: Ui.meta + 1
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 6
            spacing: 4

            IconButton {
                size: 28
                glyph: Ui.prev
                enabled: root.player?.canGoPrevious ?? false
                Accessible.name: "Anterior"
                onClicked: root.player.previous()
            }
            IconButton {
                size: 28
                glyph: root.player?.isPlaying ? Ui.pause : Ui.play
                primary: true
                enabled: root.player?.canTogglePlaying ?? false
                Accessible.name: root.player?.isPlaying ? "Pausa" : "Reproducir"
                onClicked: root.player.togglePlaying()
            }
            IconButton {
                size: 28
                glyph: Ui.next
                enabled: root.player?.canGoNext ?? false
                Accessible.name: "Siguiente"
                onClicked: root.player.next()
            }
            Item { Layout.fillWidth: true }
            Label {
                visible: root.hasLength
                text: root.clock(root.player?.position ?? 0) + " / " + root.clock(root.player?.length ?? 0)
                color: Ryce.Palette.fg2
                font.pixelSize: Ui.meta
                font.features: { "tnum": 1 }
            }
        }

        Item {
            visible: root.hasLength
            Layout.fillWidth: true
            Layout.topMargin: 6
            implicitHeight: 2

            Rectangle {
                anchors.fill: parent
                radius: 1
                color: Ryce.Palette.line
            }
            Rectangle {
                height: parent.height
                radius: 1
                width: root.hasLength ? parent.width * Math.min(1, root.player.position / root.player.length) : 0
                color: Ryce.Palette.fg1
            }
        }
    }
}
