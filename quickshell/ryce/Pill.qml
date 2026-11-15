import QtQuick
import QtQuick.Layouts
import qs
import qs as Ryce

// A quick toggle. Off: a quiet ground. On: the bar's active mark (pill colour and
// radius), so "on" means the same thing everywhere. Its face is centred, like a switch;
// `row` lays it out as one of the sidebar's rows instead — glyph and label on the left,
// `meta` (a state, a level, with an optional `metaGlyph`) on the right — for a pill that
// names a thing. `busy` breathes the glyph while something is on its way.
Rectangle {
    id: pill
    property string glyph
    property string label
    property string meta
    property string metaGlyph
    property string metaSpoken: meta        // what a screen reader says for meta
    property color metaColor: on ? Ryce.Palette.dimOnPill : Ryce.Palette.fg2
    property bool row: false
    property bool on: false
    property bool available: true
    property bool busy: false
    signal clicked()

    readonly property color ink: on ? Ryce.Palette.inkOnPill : available ? Ryce.Palette.fg1 : Ryce.Palette.fg2

    implicitHeight: 34
    radius: Math.min(Ryce.Palette.pillRadius, height / 2)
    color: on ? Ryce.Palette.pill : mouse.containsMouse && available ? Ryce.Palette.bg2 : Ryce.Palette.bg1
    Accessible.role: Accessible.CheckBox
    Accessible.name: metaSpoken === "" ? label : label + ", " + metaSpoken
    Accessible.checked: on
    Behavior on color { ColorAnimation { duration: 140 } }

    // The glyph, breathing while busy (only while on screen: a closed drawer hides it).
    component Glyph: Label {
        text: pill.glyph
        color: pill.ink
        font.family: Ryce.Palette.fontIcon
        font.pixelSize: 15
        elide: Text.ElideNone

        SequentialAnimation on opacity {
            running: pill.busy && visible     // its own visibility: the other face's copy never runs
            loops: Animation.Infinite
            alwaysRunToEnd: true
            NumberAnimation { to: 0.35; duration: 520; easing.type: Easing.InOutSine }
            NumberAnimation { to: 1; duration: 520; easing.type: Easing.InOutSine }
        }
    }
    // The meta: an optional glyph and a word or a level, quieter than the label.
    component Meta: Row {
        visible: pill.meta !== ""
        spacing: 4

        Label {
            visible: pill.metaGlyph !== ""
            anchors.verticalCenter: parent.verticalCenter
            text: pill.metaGlyph
            color: pill.metaColor
            font.family: Ryce.Palette.fontIcon
            font.pixelSize: 13
            elide: Text.ElideNone
        }
        Label {
            anchors.verticalCenter: parent.verticalCenter
            text: pill.meta
            color: pill.metaColor
            // A row's value matches the sidebar's other values (the volume's «72 %»).
            font.pixelSize: pill.row ? Ui.meta : Ui.meta + 1
            font.features: { "tnum": 1 }
            elide: Text.ElideNone
        }
    }

    // A switch: the face centred (exactly as before rows existed).
    Row {
        visible: !pill.row
        anchors.centerIn: parent
        spacing: 8

        Glyph { anchors.verticalCenter: parent.verticalCenter }
        Label {
            text: pill.label
            color: pill.ink
            font.pixelSize: Ui.meta + 1
            anchors.verticalCenter: parent.verticalCenter
        }
        Meta { anchors.verticalCenter: parent.verticalCenter }
    }
    // A row: glyph and label on the left, the meta on the right; the label gives way.
    RowLayout {
        visible: pill.row
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        spacing: 8

        Glyph {}
        Label {
            text: pill.label
            color: pill.ink
            font.pixelSize: Ui.meta + 1
            Layout.fillWidth: true
        }
        Meta {}
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: pill.available ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (pill.available) pill.clicked()
    }
}
