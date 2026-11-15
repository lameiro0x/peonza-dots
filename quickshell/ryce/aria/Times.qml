pragma Singleton

import QtQuick
import Quickshell

// Durations as the drawer prints them: m:ss, or h:mm:ss for a long playlist.
Singleton {
    function clock(seconds) {
        const s = Math.max(0, Math.floor(seconds ?? 0));
        const mm = Math.floor(s / 60) % 60, ss = String(s % 60).padStart(2, "0");
        return s >= 3600 ? Math.floor(s / 3600) + ":" + String(mm).padStart(2, "0") + ":" + ss : mm + ":" + ss;
    }
}
