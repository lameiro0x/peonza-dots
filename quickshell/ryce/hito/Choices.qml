import QtQuick
import qs
import qs as Ryce

// A few words, one of them chosen: the chosen one in `ink` over a short rule that slides
// to whichever word is picked next, the rest in `dim` (brighter under the pointer). Words
// wrap onto more lines when they do not fit `width`. An option may carry a project dot.
// Used for Hito's views and filters, on the desk card (DeskUi's inks) and in the drawer.
Item {
    id: choices
    property var options: []                // [{ key, label, hue? }]; `hue` set: a dot
    property string current
    property color ink: Ryce.Palette.fg0
    property color dim: Ryce.Palette.fg2
    property color hover: Ryce.Palette.fg1
    property int size: Ui.meta
    property bool caps: false
    property bool square: false             // square dots (the box and plate themes)
    property Hito hito                      // for the dots' theme hues
    signal picked(string key)

    property int built: 0
    readonly property Item chosen: {
        const i = options.findIndex(o => o.key === current);
        return built >= 0 && i >= 0 ? words.itemAt(i) : null;          // built: a word made or gone
    }

    // The rule glides only between two words: where it first shows (the words laid out
    // after the options arrive) it is just there.
    property bool glide: false
    property Item last: null
    onChosenChanged: {
        if (last === null || chosen === null) {
            glide = false;
            if (chosen !== null) settle.restart();
        }
        last = chosen;
    }
    Timer {
        id: settle
        interval: 60
        onTriggered: choices.glide = choices.chosen !== null
    }

    implicitHeight: flow.implicitHeight + 4
    Accessible.role: Accessible.PageTabList

    Flow {
        id: flow
        width: choices.width
        spacing: 4                         // between lines; words keep 12 more after them

        Repeater {
            id: words
            model: choices.options
            // itemAt() is no binding: `chosen` looks again each time a word comes or goes.
            onItemAdded: choices.built++
            onItemRemoved: choices.built++

            Item {
                id: word
                required property var modelData
                readonly property bool on: modelData.key === choices.current
                readonly property bool dotted: modelData.hue !== undefined
                implicitWidth: label.x + label.implicitWidth + 12
                implicitHeight: label.implicitHeight + 6
                Accessible.role: Accessible.PageTab
                Accessible.name: modelData.label
                Accessible.checked: on

                Rectangle {
                    visible: word.dotted
                    y: Math.round((label.implicitHeight - height) / 2)
                    width: 6
                    height: 6
                    radius: choices.square ? 1 : 3
                    color: word.dotted && choices.hito ? choices.hito.dotColor(word.modelData.hue, choices.dim) : choices.dim
                }
                Label {
                    id: label
                    x: word.dotted ? 11 : 0
                    text: choices.caps ? word.modelData.label.toUpperCase() : word.modelData.label
                    color: word.on ? choices.ink : mouse.containsMouse ? choices.hover : choices.dim
                    font.pixelSize: choices.size
                    font.letterSpacing: choices.caps ? 0.6 : 0.2
                    font.features: { "tnum": 1 }
                    elide: Text.ElideNone
                    Behavior on color { ColorAnimation { duration: 120 } }
                }
                MouseArea {
                    id: mouse
                    anchors.fill: parent
                    anchors.margins: -4
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: choices.picked(word.modelData.key)
                }
            }
        }
    }

    // The rule under the chosen word, sliding on the theme's curve.
    Rectangle {
        id: rule
        readonly property int ms: choices.glide ? Math.round(Ryce.Palette.motionMs * 0.6) : 0
        visible: choices.chosen !== null
        x: choices.chosen ? choices.chosen.x + (choices.chosen.dotted ? 11 : 0) : 0
        y: choices.chosen ? choices.chosen.y + choices.chosen.height - 2 : 0
        width: choices.chosen ? choices.chosen.width - 12 - (choices.chosen.dotted ? 11 : 0) : 0
        height: 1.5
        radius: 1
        color: choices.ink
        Behavior on x { NumberAnimation { duration: rule.ms; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
        Behavior on y { NumberAnimation { duration: rule.ms; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
        Behavior on width { NumberAnimation { duration: rule.ms; easing.type: Easing.BezierSpline; easing.bezierCurve: Ryce.Palette.motionCurve } }
    }
}
