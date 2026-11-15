import QtQuick
import Quickshell
import Quickshell.Io
import qs as Ryce
import qs.frame
import qs.drawers
import qs.desk
import qs.aria
import qs.hito
import qs.keys
import qs.wallpick
import qs.peonza

// ryce «Marco»: the whole shell in one process.
//   FrameRoot     the screen corners and the floating bar (systemd probes
//                 `qs -c ryce ipc call bar ping`; if this process crash-loops, Waybar takes over)
//   DrawersRoot   the sidebar (SUPER+a, the bar's agent counter) and the theme selector (SUPER+t)
//   AmbientRoot   desk clock and stats (SUPER+d, SUPER+SHIFT+d), the volume OSD and the
//                 live-wallpaper experiment (off by default)
//   AriaRoot      the Aria music drawer (SUPER+m) and its mpv player (ryce-aria.service)
//   HitoRoot      Hito's «Hoy» desk card (qs ipc call hito desk) and its drawer (SUPER+h)
//   KeysRoot      the keybinding cheat sheet (SUPER+F1)
//   WallpickRoot  the wallpaper picker: the current theme's pictures (SUPER+SHIFT+W)
//   PeonzaRoot    the desk's spinning peonza (qs ipc call peonza toggle)
// Colours, fonts, geometry and motion come from the generated Palette singleton, which
// follows ~/.local/state/ryce/theme/current; `ryce-theme set` calls `theme reload` below.
ShellRoot {
    id: shell

    IpcHandler {
        target: "theme"

        // The `current` link is swapped by rename, which a file watch does not survive:
        // ryce-theme asks explicitly, and every colour cross-fades from here.
        function reload(): void { Ryce.Palette.reload(); }
    }

    FrameRoot {
        onSidebarToggleRequested: screenName => drawers.toggleSidebar(screenName)
    }

    DrawersRoot {
        id: drawers
    }

    AmbientRoot {}

    AriaRoot {}

    HitoRoot {}

    KeysRoot {}

    WallpickRoot {}

    PeonzaRoot {}
}
