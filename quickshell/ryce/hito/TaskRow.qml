import QtQuick
import qs
import qs as Ryce

// One task in the drawer: a box to tick it off, its project's colour and title, and a
// note at the end (its time, day or project). A repeating task shows a repeat mark in
// place of the box and stays read-only: completing it rolls it to its next occurrence
// with Hito's own recurrence rules, which live in its client, not in the database.
Item {
    id: row
    required property var task
    property Hito hito
    property string note                    // the right-hand note
    property color noteColor: Ryce.Palette.fg2
    property string mark: ""                // "" | "busy" (sent) | "done" (confirmed)
    signal completeRequested()

    readonly property bool done: mark !== ""
    readonly property bool hovered: mouse.containsMouse

    implicitHeight: 30
    Accessible.role: Accessible.CheckBox
    Accessible.name: task.title
    Accessible.checked: done

    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: -8
        anchors.rightMargin: -8
        radius: Math.min(Ryce.Palette.pillRadius, 6)
        color: Ryce.Palette.bg1
        opacity: row.hovered ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 120 } }
    }

    Rectangle {
        id: box
        visible: !row.task.recurring
        anchors.verticalCenter: parent.verticalCenter
        width: 14
        height: 14
        radius: Math.min(Ryce.Palette.pillRadius, 4)
        color: row.done ? Ryce.Palette.pill : "transparent"
        border.width: row.done ? 0 : 1
        border.color: row.hovered ? Ryce.Palette.fg1 : Ryce.Palette.fg2
        Behavior on color { ColorAnimation { duration: 120 } }

        Label {
            anchors.centerIn: parent
            visible: row.done
            text: Ui.check
            color: Ryce.Palette.inkOnPill
            font.family: Ryce.Palette.fontIcon
            font.pixelSize: 11
            elide: Text.ElideNone
        }
    }
    Label {
        visible: row.task.recurring
        anchors.verticalCenter: parent.verticalCenter
        width: 14
        horizontalAlignment: Text.AlignHCenter
        text: String.fromCodePoint(0xf0456)     // md-repeat
        color: Ryce.Palette.fg2
        font.family: Ryce.Palette.fontIcon
        font.pixelSize: 13
        elide: Text.ElideNone
    }

    Rectangle {
        id: dot
        x: 26
        anchors.verticalCenter: parent.verticalCenter
        width: 6
        height: 6
        radius: Math.min(3, Ryce.Palette.pillRadius)
        color: row.hito.dotColor(row.task.hue, Ryce.Palette.fg2)
    }
    Label {
        x: 42
        width: note.x - x - 12
        anchors.verticalCenter: parent.verticalCenter
        text: row.task.title
        color: row.done ? Ryce.Palette.fg2 : Ryce.Palette.fg0
        font.strikeout: row.mark === "done"
    }
    Label {
        id: note
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(implicitWidth, 150)
        // The tooltip of a repeating task: where it can be completed.
        text: row.task.recurring && row.hovered ? "se completa desde Hito" : row.note
        color: row.task.recurring && row.hovered ? Ryce.Palette.fg1 : row.noteColor
        font.pixelSize: Ui.meta
        font.features: { "tnum": 1 }
    }

    // Hover over the whole row; only the box completes, so a stray click on a title
    // never closes a task (the drawer has no undo).
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true

        MouseArea {
            visible: !row.task.recurring && !row.done
            x: -8
            width: 30
            height: parent.height
            cursorShape: Qt.PointingHandCursor
            onClicked: row.completeRequested()
        }
    }
}
