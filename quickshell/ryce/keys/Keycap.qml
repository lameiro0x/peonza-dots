import QtQuick
import qs
import qs as Ryce
import qs.bar

// One key, drawn in the bar's skin so the sheet reads as the same instrument: Origen a
// soft chip with a pressed lip, Grafito a bare readout, Ola an outlined capsule, Tinta a
// 1 px box in its terminal face.
Item {
    id: cap
    property string text
    readonly property string skin: BarUi.skin

    implicitWidth: skin === "bare" ? face.implicitWidth : Math.max(face.implicitWidth + 2 * (skin === "capsule" ? 11 : 8), implicitHeight)
    implicitHeight: 24

    Rectangle {
        visible: cap.skin === "chip"
        anchors.fill: parent
        radius: Math.min(Ryce.Palette.pillRadius, 6)
        color: Ryce.Palette.bg3

        Rectangle {
            width: parent.width
            height: parent.height - 2
            radius: parent.radius
            color: Ryce.Palette.bg2
        }
    }
    Rectangle {
        visible: cap.skin === "capsule" || cap.skin === "box"
        anchors.fill: parent
        radius: cap.skin === "capsule" ? height / 2 : Math.min(Ryce.Palette.pillRadius, 3)
        color: "transparent"
        border.width: 1
        border.color: cap.skin === "box" ? Ryce.Palette.fg2 : Ryce.Palette.line
    }
    Label {
        id: face
        anchors.centerIn: parent
        anchors.verticalCenterOffset: cap.skin === "chip" ? -1 : 0
        text: cap.skin === "box" || cap.skin === "bare" ? cap.text.toUpperCase() : cap.text
        color: Ryce.Palette.fg0
        font.family: cap.skin === "bare" || cap.skin === "box" ? Ryce.Palette.fontMono : Ryce.Palette.fontUi
        font.pixelSize: Ui.meta + 1
        font.weight: cap.skin === "bare" ? Font.DemiBold : Font.Normal
        font.letterSpacing: cap.skin === "bare" ? 0.8 : 0
        elide: Text.ElideNone
    }
}
