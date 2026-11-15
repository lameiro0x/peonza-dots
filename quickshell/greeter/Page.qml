import QtQuick
import qs

// The sheet, a record («expediente»): a header rule across the top with the record row under
// it; one column 12 % in (the clock, the date, the user, the password and ENTRAR; no greeting:
// a record, not an app); the power words at the foot. The background's drawing has the right
// half. Pixel sizes are for 1920x1080.
FocusScope {
    id: root

    required property var auth
    required property date now
    readonly property int inset: Math.round(width * 0.12)
    readonly property int edge: 56

    // Every key the focused item leaves reaches here too: the layout tag and Caps Lock follow
    // what xkb types, wherever the focus is.
    Keys.onPressed: event => auth.sawKey(event)

    Caps {
        id: title
        x: root.inset
        y: root.edge
        text: "Ryce // acceso"
        color: Look.fg1
    }
    Rectangle {
        anchors.left: title.right
        anchors.right: sheetNo.left
        anchors.leftMargin: 20
        anchors.rightMargin: 20
        anchors.verticalCenter: title.verticalCenter
        height: 1
        color: Look.line
    }
    Caps {
        id: sheetNo
        anchors.right: parent.right
        anchors.rightMargin: root.inset
        y: root.edge
        text: "Hoja 1 de 1"
    }
    // The record: its number (the background's drawing is RY-PZ-001), the console greetd
    // runs on, and what ENTRAR starts (always the one session, there is no picker).
    Caps {
        x: root.inset
        anchors.top: title.bottom
        anchors.topMargin: 14
        text: ["Exp. RY-001", root.auth.vt !== "" ? "tty" + root.auth.vt : "", "Hyprland"]
            .filter(s => s !== "").join(" · ")
    }

    Column {
        id: column
        x: root.inset
        anchors.verticalCenter: parent.verticalCenter
        width: 440

        Text {
            x: -3   // Doto's side bearing: the dots line up with the column's edge
            text: Look.clock(root.now)
            color: Look.fg1
            font.family: Look.fontClock
            font.pixelSize: 112
            font.weight: Font.Black    // the solid dots: lighter cuts fall apart into specks
            font.features: { "tnum": 1 }
            textFormat: Text.PlainText
        }
        Caps {
            topPadding: 10
            px: 12
            text: Look.longDate(root.now)
        }

        Item { width: 1; height: 72 }


        Caps { text: "Usuario" }
        Item {
            width: parent.width
            height: 52
            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 120
                elide: Text.ElideRight
                text: root.auth.user
                color: Look.fg0
                font.family: Look.fontText
                font.pixelSize: 20
                textFormat: Text.PlainText
            }
            Link {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                visible: root.auth.users.length > 1
                label: "Cambiar"
                onActivated: root.auth.nextUser()
            }
            // Not a control: the line is the sheet's, in the decorative grey.
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Look.line
            }
        }

        Item { width: 1; height: 30 }

        PasswordField {
            id: field
            auth: root.auth
            width: parent.width
            focus: true
        }

        Item { width: 1; height: 26 }

        Rectangle {
            id: enter
            readonly property bool lit: go.containsMouse || activeFocus
            width: 176
            height: 44
            radius: 0
            color: go.pressed ? Look.fg1 : lit ? Look.fg0 : Look.paper
            opacity: root.auth.busy ? 0.55 : 1
            activeFocusOnTab: true
            Behavior on color { ColorAnimation { duration: 120 } }
            Behavior on opacity { NumberAnimation { duration: 160 } }
            Accessible.role: Accessible.Button
            Accessible.name: "Entrar"
            Accessible.onPressAction: root.auth.submit(field.input.text)
            Keys.onReturnPressed: root.auth.submit(field.input.text)
            Keys.onEnterPressed: root.auth.submit(field.input.text)
            Keys.onSpacePressed: root.auth.submit(field.input.text)

            Caps {
                anchors.left: parent.left
                anchors.leftMargin: 18
                anchors.verticalCenter: parent.verticalCenter
                px: 12
                text: root.auth.busy ? "Comprobando" : "Entrar"
                color: Look.bg0
                font.weight: Font.Medium
            }
            Caps {
                anchors.right: parent.right
                anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                px: 14
                text: "→"
                color: Look.bg0
                font.letterSpacing: 0
            }
            // The keyboard's focus: a hairline frame off the fill, as the sheet marks lines.
            Rectangle {
                anchors.fill: parent
                anchors.margins: -4
                color: "transparent"
                border.width: 1
                border.color: Look.fg1
                visible: enter.activeFocus
            }
            MouseArea {
                id: go
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.auth.submit(field.input.text)
            }
        }
    }

    Row {
        x: root.inset
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.edge
        spacing: 14
        Link {
            label: "Reiniciar"
            onActivated: root.auth.power("reboot")
        }
        Caps { text: "·" }
        Link {
            label: "Apagar"
            onActivated: root.auth.power("poweroff")
        }
    }

    // The key, then what it does, as GRUB's foot reads.
    Row {
        anchors.right: parent.right
        anchors.rightMargin: root.inset
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.edge
        spacing: 12
        Caps { text: "Alt + Mayús"; color: Look.fg1 }
        Caps { text: "cambia el teclado" }
    }
}
