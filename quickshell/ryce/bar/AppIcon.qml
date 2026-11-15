import QtQuick
import QtQuick.Effects
import Quickshell.Widgets

// An application or tray icon at bar size. The grey themes (BarUi.mono) show it
// without colour: a static layer, rendered once per icon, not per frame.
IconImage {
    implicitSize: BarUi.iconPx
    mipmap: true
    layer.enabled: BarUi.mono
    layer.effect: MultiEffect {
        saturation: -1
    }
}
