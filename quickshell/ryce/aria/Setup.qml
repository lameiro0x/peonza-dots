import QtQuick
import QtQuick.Layouts
import qs
import qs as Ryce

// First run, or a credentials file that no longer works: the server, the user and the
// password. «Conectar» pings with them first and only then writes the private file.
ColumnLayout {
    id: setup
    required property var api
    property string note: ""
    property bool busy: false

    function submit() {
        if (busy) return;
        busy = true;
        note = "Probando…";
        api.connect(url.text, user.text, pass.text, reason => {
            busy = false;
            note = reason;
            if (reason === "") pass.text = "";
        });
    }

    spacing: 10

    Label {
        Layout.fillWidth: true
        text: "Conecta tu servidor de música"
        color: Ryce.Palette.fg0
        font.pixelSize: Ui.project
    }
    Label {
        Layout.fillWidth: true
        Layout.bottomMargin: 6
        text: "Se guarda solo para ti en ~/.config/ryce-private/aria.json"
        color: Ryce.Palette.fg2
        font.pixelSize: Ui.meta
        wrapMode: Text.Wrap
    }
    Field {
        id: url
        Layout.fillWidth: true
        placeholder: "Dirección"
        text: setup.api.base !== "" ? setup.api.base : setup.api.defaultUrl
        input.KeyNavigation.tab: user.input
        onAccepted: user.input.forceActiveFocus()
    }
    Field {
        id: user
        Layout.fillWidth: true
        placeholder: "Usuario"
        input.KeyNavigation.tab: pass.input
        onAccepted: pass.input.forceActiveFocus()
        Component.onCompleted: input.forceActiveFocus()
    }
    Field {
        id: pass
        Layout.fillWidth: true
        placeholder: "Contraseña"
        secret: true
        input.KeyNavigation.tab: url.input
        onAccepted: setup.submit()
    }
    RowLayout {
        Layout.fillWidth: true
        Layout.topMargin: 6
        spacing: 12

        Tab {
            text: "Conectar"
            on: true
            enabled: !setup.busy
            onClicked: setup.submit()
        }
        Label {
            Layout.fillWidth: true
            text: setup.note
            color: setup.busy ? Ryce.Palette.fg2 : Ryce.Palette.err
            font.pixelSize: Ui.meta
            wrapMode: Text.Wrap
            maximumLineCount: 2
        }
    }
}
