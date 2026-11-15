import QtQuick
import Quickshell.Services.Mpris
import Quickshell.Services.Pipewire
import qs as Ryce

// Now playing, with the default output's live level beside the title, between a
// previous and a next button. A click anywhere else pauses or resumes. A paused player
// stays on the bar (its title in the quiet ink, the level hidden) so the same click
// resumes it, and so does a stopped one (Aria's mpv idles as a service): the module is
// on every bar, in every theme, while any player exists, not only after something
// played in this shell's lifetime. Everything else (queue, search, volume) lives in
// Aria's drawer. The level monitor captures only while something plays.
Module {
    id: media
    property real maxText: 260

    readonly property MprisPlayer playing: Mpris.players.values.find(p => p.isPlaying) ?? null
    property MprisPlayer last: null          // QObject property: nulls itself when the player quits
    onPlayingChanged: if (playing !== null) last = playing
    readonly property MprisPlayer player: playing ?? last
        ?? Mpris.players.values.find(p => p.playbackState === MprisPlaybackState.Paused)
        ?? Mpris.players.values[0] ?? null
    readonly property bool paused: player !== null && player.playbackState === MprisPlaybackState.Paused
    readonly property string line: player === null ? ""
        : [player.trackTitle, player.trackArtist].filter(s => s !== "").join(" · ") || player.identity

    // Everything but the title; Status gives the title what the bar has left. A title
    // squeezed under 60 px says nothing: it steps aside and the controls stay (a theme
    // with a wide clock, or two screens' slots in the centre, left none). Only a bar
    // without room for the controls themselves loses the module.
    readonly property real chrome: 2 * BarUi.padX + BarUi.gap + prev.width + note.width + meter.width + next.width + 4 * spacing
    shown: player !== null && maxText >= 0
    interactive: player?.canTogglePlaying ?? false      // a stopped player with nothing queued: no dead click
    lit: hovered && !prev.hot && !next.hot
    Accessible.role: Accessible.Button
    Accessible.name: (media.playing ? "Sonando: " : media.paused ? "En pausa: " : "Música: ") + media.line
    spacing: 8

    onClicked: if (media.player !== null && media.player.canTogglePlaying) media.player.togglePlaying()

    PwNodePeakMonitor {
        id: peaks
        node: Pipewire.defaultAudioSink
        enabled: media.playing !== null
    }

    Skip {
        id: prev
        glyph: Ryce.Ui.prev
        can: media.player?.canGoPrevious ?? false
        Accessible.name: "Pista anterior"
        onHit: media.player.previous()
    }
    BarText {
        id: note
        text: media.paused ? Ryce.Ui.pause : Ryce.Ui.music
        ink: Ryce.Ui.music
        color: media.playing ? Ryce.Palette.hueMedia : Ryce.Palette.fg2
        font.family: Ryce.Palette.fontIcon
        font.pixelSize: BarUi.iconPx
        font.weight: Font.Normal
    }
    // Left and right peaks; a mono stream lights both. Paused, the level fades to nothing
    // (two flat 2 px stubs beside the title read as a stray «‥») but keeps its room, so
    // the title does not jump on pause and resume. Opacity, not `visible`: the module's
    // Row would drop an invisible child's room.
    Row {
        id: meter
        anchors.verticalCenter: parent.verticalCenter
        height: Math.round(BarUi.chipHeight * 0.46)
        spacing: 2
        opacity: media.playing ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Ryce.Palette.motionMs * 0.5; easing.type: Easing.OutCubic } }

        Repeater {
            model: 2

            Item {
                required property int index
                readonly property real level: media.playing === null ? 0
                    : Math.min(1, peaks.peaks[index] ?? peaks.peak)
                width: 3
                height: parent.height

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: Math.max(2, Math.round(parent.level * parent.height))
                    radius: Math.min(1, Ryce.Palette.pillRadius)
                    color: Ryce.Palette.hueMedia
                }
            }
        }
    }
    // Measured, never read back from the elided Text: its implicit width moves with its
    // own width and Qt reports that as a binding loop (same as FocusLine).
    BarText {
        id: title
        visible: media.maxText >= 60       // invisible, the Row drops its room and spacing
        width: Math.min(Math.max(0, media.maxText), Math.ceil(titleFont.advanceWidth(media.line)))
        text: media.line
        elide: Text.ElideRight
        color: media.playing ? Ryce.Palette.fg1 : Ryce.Palette.fg2

        FontMetrics {
            id: titleFont
            font: title.font
        }
    }
    Skip {
        id: next
        glyph: Ryce.Ui.next
        can: media.player?.canGoNext ?? false
        Accessible.name: "Pista siguiente"
        onHit: media.player.next()
    }

    // A skip button in the drawers' IconButton look (bg2 ground under the pointer, the
    // pill's radius), its glyph centred on its ink like the rest of the bar.
    component Skip: Item {
        id: skip
        property string glyph
        property bool can: false
        readonly property bool hot: area.containsMouse && can
        signal hit()

        anchors.verticalCenter: parent.verticalCenter
        width: BarUi.chipHeight - 8
        height: width
        Accessible.role: Accessible.Button

        Rectangle {
            anchors.fill: parent
            radius: Math.min(Ryce.Palette.pillRadius, width / 2)
            color: Ryce.Palette.bg2
            opacity: skip.hot ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 120 } }
        }
        BarText {
            x: Math.round((parent.width - width) / 2)
            text: skip.glyph
            ink: text
            color: Ryce.Palette.fg1
            opacity: skip.can ? 1 : 0.35
            font.family: Ryce.Palette.fontIcon
            font.pixelSize: BarUi.iconPx
            font.weight: Font.Normal
            scale: area.pressed && skip.can ? 0.88 : 1
            Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
        }
        // Takes every click on the button, a dead one too: a click meant for «next»
        // must never fall through to the module and pause the music.
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: skip.can ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: if (skip.can) skip.hit()
        }
    }
}
