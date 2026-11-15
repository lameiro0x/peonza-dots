pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Services.Mpris

// One answer to «which player?» for the sidebar (and anything else that shows one): the
// one playing, else the last one that played, else a paused one, else any (the bar's
// Media.qml chooses the same way). And one rule between the two Navidrome clients, Aria
// (its mpv through mpv-mpris, streaming Subsonic's /rest/stream) and Feishin: they never
// play at once — when one starts, the other pauses. Every other player (a browser, a video
// in mpv) is left alone.
Singleton {
    id: root

    readonly property MprisPlayer playing: Mpris.players.values.find(p => p.isPlaying) ?? null
    property MprisPlayer last: null          // QObject property: nulls itself when the player quits
    onPlayingChanged: if (playing !== null) last = playing
    readonly property MprisPlayer player: playing ?? last
        ?? Mpris.players.values.find(p => p.playbackState === MprisPlaybackState.Paused)
        ?? Mpris.players.values[0] ?? null

    function isFeishin(p: MprisPlayer): bool {
        return p !== null && (p.identity === "Feishin" || p.dbusName.endsWith(".Feishin"));
    }
    // The URL carries the stream's query (credentials included): it is matched, never shown.
    function isAria(p: MprisPlayer): bool {
        return p !== null && p.dbusName.startsWith("org.mpris.MediaPlayer2.mpv")
            && String(p.metadata["xesam:url"] ?? "").includes("/rest/stream");
    }

    Instantiator {
        model: Mpris.players
        delegate: Connections {
            required property MprisPlayer modelData
            target: modelData

            function onIsPlayingChanged() {
                if (!modelData.isPlaying)
                    return;
                const rival = root.isFeishin(modelData) ? root.isAria
                    : root.isAria(modelData) ? root.isFeishin : null;
                if (rival === null)
                    return;
                for (const p of Mpris.players.values) {
                    if (p !== modelData && p.isPlaying && p.canPause && rival(p))
                        p.pause();
                }
            }
        }
    }
}
