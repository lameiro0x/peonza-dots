pragma Singleton

import QtQuick
import Quickshell

// Type scale, spacing and glyphs of the drawers. Colours and fonts live in Palette
// (generated); these are sizes only, the same in every theme.
Singleton {
    readonly property int body: 13
    readonly property int project: 14
    readonly property int meta: 11
    readonly property int clock: 60          // the sidebar clock, in the theme's display face
    readonly property int pad: 24
    readonly property int panelWidth: 400    // the sidebar drawer's width

    // The opaque drawers that are open. The desk widgets step aside while one is: half a
    // clock or a Hito card sticking out from under a drawer reads as a rendering fault.
    property bool sidebarOpen: false
    property bool ariaOpen: false
    property bool hitoOpen: false
    readonly property bool deskCovered: sidebarOpen || ariaOpen || hitoOpen

    // Material Design glyphs (nf-md-*) by code point: no private-use character is typed.
    readonly property string prev: String.fromCodePoint(0xf04ae)       // md-skip_previous
    readonly property string play: String.fromCodePoint(0xf040a)       // md-play
    readonly property string pause: String.fromCodePoint(0xf03e4)      // md-pause
    readonly property string next: String.fromCodePoint(0xf04ad)       // md-skip_next
    readonly property string music: String.fromCodePoint(0xf0387)      // md-music_note
    readonly property string bellOff: String.fromCodePoint(0xf0a91)    // md-bell_off_outline
    readonly property string night: String.fromCodePoint(0xf0594)      // md-weather_night
    readonly property string headphones: String.fromCodePoint(0xf02cb)     // md-headphones
    readonly property string headphonesOff: String.fromCodePoint(0xf07ce)  // md-headphones_off
    // md-battery_20 … md-battery_90 by tens, md-battery when full, md-battery_alert when low
    // (≤ 15 %, HeadsetLogic.low: time to charge).
    function battery(level) {
        if (level < 0) return "";
        if (level <= 15) return String.fromCodePoint(0xf0083);
        if (level >= 95) return String.fromCodePoint(0xf0079);
        return String.fromCodePoint(0xf007a + Math.max(0, Math.min(8, Math.floor(level / 10) - 1)));
    }
    readonly property string volHigh: String.fromCodePoint(0xf057e)    // md-volume_high
    readonly property string volMid: String.fromCodePoint(0xf0580)     // md-volume_medium
    readonly property string volLow: String.fromCodePoint(0xf057f)     // md-volume_low
    readonly property string volOff: String.fromCodePoint(0xf0581)     // md-volume_off
    readonly property string chevron: String.fromCodePoint(0xf0142)    // md-chevron_right
    readonly property string check: String.fromCodePoint(0xf012c)      // md-check
    readonly property string terminal: String.fromCodePoint(0xf018d)    // md-console
    readonly property string cpu: String.fromCodePoint(0xf0ee0)        // md-cpu_64_bit
    readonly property string memory: String.fromCodePoint(0xf035b)     // md-memory
    readonly property string shuffle: String.fromCodePoint(0xf049d)    // md-shuffle
    readonly property string library: String.fromCodePoint(0xf0333)    // md-music_box_multiple
}
