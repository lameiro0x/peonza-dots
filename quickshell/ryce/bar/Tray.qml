import QtQuick
import Quickshell
import Quickshell.Services.SystemTray
import qs as Ryce

// The status notifier tray, one module holding every item. Left click activates (or
// opens the menu of a menu-only item), right click opens the menu, middle click is the
// secondary action, the wheel scrolls the item. Hidden while no app sits in the tray.
Module {
    id: tray
    shown: SystemTray.items.values.length > 0
    spacing: 2

    Repeater {
        model: SystemTray.items

        Item {
            id: entry
            required property SystemTrayItem modelData
            readonly property int size: BarUi.chipHeight - 6

            anchors.verticalCenter: parent.verticalCenter
            width: size
            height: size
            Accessible.role: Accessible.Button
            Accessible.name: modelData.tooltipTitle || modelData.title || modelData.id

            function menu() {
                const p = entry.mapToItem(null, 0, entry.height);
                entry.modelData.display(QsWindow.window, Math.round(p.x), BarUi.band);
            }

            Rectangle {
                anchors.fill: parent
                radius: BarUi.radius
                color: BarUi.skin === "chip" || BarUi.skin === "capsule" ? Ryce.Palette.bg3 : Ryce.Palette.bg2
                opacity: mouse.containsMouse ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: Ryce.Palette.motionMs * 0.5; easing.type: Easing.OutCubic } }
            }
            AppIcon {
                anchors.centerIn: parent
                implicitSize: Math.min(BarUi.iconPx, entry.size - 4)
                source: entry.modelData.icon
                scale: mouse.pressed ? 0.9 : 1
                Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
            }
            MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                cursorShape: Qt.PointingHandCursor
                onClicked: m => {
                    const item = entry.modelData;
                    if (m.button === Qt.MiddleButton) item.secondaryActivate();
                    else if (m.button === Qt.RightButton || item.onlyMenu) { if (item.hasMenu) entry.menu(); }
                    else item.activate();
                }
                onWheel: w => entry.modelData.scroll(w.angleDelta.y !== 0 ? w.angleDelta.y : w.angleDelta.x, w.angleDelta.y === 0)
            }
        }
    }
}
