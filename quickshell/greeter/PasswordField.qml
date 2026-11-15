import QtQuick
import qs

// The password, a ruled line on the sheet: its label above, dots on the line, the tags at the
// rule's right end (the keyboard layout; Caps Lock as an inverted chip, only while it is on).
// With the focus the rule thickens to white and a square marks the line; a refusal turns the
// rule to the error colour, says why under it and shakes the field. Dimmed while greetd checks.
FocusScope {
    id: field

    required property var auth
    property alias input: input

    implicitWidth: 440
    implicitHeight: label.height + 8 + line.height + 12 + note.height

    transform: Translate { id: nudge }

    SequentialAnimation {
        id: shake
        NumberAnimation { target: nudge; property: "x"; to: -8; duration: 45; easing.type: Easing.OutQuad }
        NumberAnimation { target: nudge; property: "x"; to: 7; duration: 70; easing.type: Easing.InOutQuad }
        NumberAnimation { target: nudge; property: "x"; to: -4; duration: 60; easing.type: Easing.InOutQuad }
        NumberAnimation { target: nudge; property: "x"; to: 0; duration: 55; easing.type: Easing.OutQuad }
    }

    // RYCE_GREETER_DEMO=typing: a filled field, for the screenshot.
    Component.onCompleted: if (auth.demo === "typing") input.text = "contraseña"

    Connections {
        target: field.auth
        function onRefused() {
            input.clear();
            shake.restart();
        }
    }

    Caps {
        id: label
        text: "Contraseña"
        color: input.activeFocus ? Look.fg1 : Look.fg2
    }

    Item {
        id: line
        anchors.top: label.bottom
        anchors.topMargin: 8
        width: parent.width
        height: 44

        // The sheet's selection: a square hung in the margin, in front of the line.
        Rectangle {
            x: -22
            anchors.verticalCenter: parent.verticalCenter
            width: 8
            height: 8
            color: field.auth.failed ? Look.err : Look.fg0
            visible: input.activeFocus
        }

        TextInput {
            id: input
            anchors.left: parent.left
            anchors.right: tags.left
            anchors.rightMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            echoMode: TextInput.Password
            passwordCharacter: "•"
            passwordMaskDelay: 0
            readOnly: field.auth.busy
            focus: true
            activeFocusOnTab: true
            clip: true
            color: Look.fg0
            opacity: field.auth.busy ? 0.45 : 1
            Behavior on opacity { NumberAnimation { duration: 160 } }
            selectionColor: Look.fg0
            selectedTextColor: Look.bg0
            font.family: Look.fontText
            font.pixelSize: 24
            font.letterSpacing: 5
            Accessible.name: "Contraseña"
            // A terminal's block caret; Qt blinks the delegate by its visibility.
            cursorDelegate: Rectangle {
                width: 10
                height: 22
                y: (input.height - height) / 2
                color: Look.fg1
            }

            onAccepted: field.auth.submit(text)
            // A new attempt starts on a clean line.
            onTextEdited: {
                field.auth.failed = false;
                field.auth.message = "";
            }
            Keys.onPressed: event => field.auth.sawKey(event)
        }

        Row {
            id: tags
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 14

            // Inverted, not amber: amber means «an agent waits» everywhere in ryce.
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                visible: field.auth.capsLock
                width: capsTag.implicitWidth + 10
                height: capsTag.implicitHeight + 4
                color: Look.paper

                Caps {
                    id: capsTag
                    anchors.centerIn: parent
                    text: "Bloq Mayús"
                    color: Look.bg0
                }
            }
            Caps {
                anchors.verticalCenter: parent.verticalCenter
                text: field.auth.layoutName
            }
        }

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: input.activeFocus ? 2 : 1
            color: field.auth.failed ? Look.err : input.activeFocus ? Look.fg0 : Look.rule
            Behavior on color { ColorAnimation { duration: 160 } }
        }
    }

    // Why the password was refused, or what PAM says. The page's own refusal is a short
    // stamp in the error colour; PAM's lines (faillock's run long) stay readable text and
    // wrap. One line's height is kept when empty, so nothing under the field moves.
    Item {
        id: note
        readonly property bool stamp: field.auth.failed && field.auth.message === field.auth.wrongPassword
        anchors.top: line.bottom
        anchors.topMargin: 12
        width: parent.width
        height: Math.max(20, note.stamp ? chip.height : why.implicitHeight)
        opacity: field.auth.message === "" ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: 160 } }

        Rectangle {
            id: chip
            visible: note.stamp
            width: chipText.implicitWidth + 14
            height: chipText.implicitHeight + 6
            color: Look.err
            Caps {
                id: chipText
                anchors.centerIn: parent
                text: "× " + field.auth.message
                color: Look.bg0
            }
        }

        Text {
            text: "×"
            visible: field.auth.failed && !note.stamp
            color: Look.err
            font.family: Look.fontLabel
            font.pixelSize: 14
            textFormat: Text.PlainText
        }
        Text {
            id: why
            visible: !note.stamp
            x: field.auth.failed ? 20 : 0
            width: parent.width - x
            text: field.auth.message
            color: field.auth.failed ? Look.err : Look.fg1
            font.family: Look.fontLabel
            font.pixelSize: 12
            lineHeight: 1.25
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
            textFormat: Text.PlainText
        }
    }
}
