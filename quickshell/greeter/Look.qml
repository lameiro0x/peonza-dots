pragma Singleton

import QtQuick
import Quickshell

// The login page's one look, the same whatever the desktop theme: Tinta's greys pushed
// towards black, a record sheet from a terminal (direction «Expediente», sibling of the GRUB
// art in theme/boot/grub.py). Every family here is installed system-wide, because the
// greeter user cannot read ~: Inter from the distro, Martian Mono and Doto in
// /usr/local/share/fonts/ryce.
Singleton {
    id: root

    // theme/boot/greeter.py renders it; the installer puts it next to this file. Missing,
    // the page stands on bg0 alone.
    readonly property url art: Quickshell.shellDir + "/background.jpg"

    readonly property color bg0: "#0a0a0a"
    readonly property color bg1: "#111111"
    readonly property color bg2: "#1a1a1a"
    readonly property color bg3: "#262626"
    readonly property color line: "#3a3a3a"     // decoration only: hairlines, never a control's edge
    readonly property color rule: "#6b6b6b"     // a field's rule, 3.5:1 on bg0
    readonly property color fg0: "#f0f0f0"
    readonly property color fg1: "#b4b4b4"
    readonly property color fg2: "#7c7c7c"      // on bg0 and bg1 only
    readonly property color paper: "#d6d6d6"    // the button's fill: the brightest area on screen
    readonly property color err: "#d4a9a9"

    readonly property string fontLabel: "Martian Mono"
    readonly property string fontText: "Inter"
    readonly property string fontClock: "Doto"
    // Martian Mono's caps tracked out by 0.2 em, in pixels at each size.
    function track(px) {
        return Math.round(px * 0.2 * 10) / 10;
    }

    // The date from Qt's own Spanish (it needs no generated system locale).
    readonly property var es: Qt.locale("es_ES")
    function longDate(d) {
        return es.toString(d, "dddd d 'de' MMMM 'de' yyyy");
    }
    // Doto draws ':' as a dotted dagger: its middle dot is the separator, as in the bar.
    function clock(d) {
        return Qt.formatTime(d, "HH'·'mm");
    }
}
