import QtQuick
import Quickshell
import Quickshell.Io
import qs as Ryce
import qs.bar

// «Marco»: per screen, the static frame (the screen's rounded corners), the floating
// bar, and the exclusive zone that keeps tiled windows under it; at the sides and the
// bottom the windows keep the theme's own gaps_out. shell.qml instantiates this once.
Scope {
    id: root

    // The bar's agent counter asks for the sidebar; shell.qml owns it and connects this.
    signal sidebarToggleRequested(string screenName)

    // systemd probes `qs -c ryce ipc call bar ping`: "ok" once a bar exists.
    IpcHandler {
        target: "bar"

        function ping(): string {
            return screens.instances.length > 0 ? "ok" : "no bar: Quickshell sees no screen";
        }
    }

    Variants {
        id: screens
        model: Quickshell.screens

        Scope {
            id: output
            required property var modelData

            FrameWindow {
                screen: output.modelData
            }
            BarWindow {
                screen: output.modelData
                onSidebarToggleRequested: root.sidebarToggleRequested(output.modelData.name)
            }
            EdgeReserve { screen: output.modelData; edge: "top"; size: Ryce.Palette.frameTop }
        }
    }
}
