// Ryce: apps/zotero/setup.py links <Zotero profile>/user.js here. Zotero copies these
// into prefs.js on every start, so a change here wins at the next start; anything not
// listed stays the user's own (Settings in Zotero writes prefs.js).

// Enable add-ons placed in the profile's extensions/ folder (Better BibTeX and the Ryce
// theme plugin, both installed by setup.py). Zotero's default, 15, installs them disabled
// until someone clicks them on in Tools > Plugins. 14 keeps that guard for every other scope.
user_pref("extensions.autoDisableScopes", 14);
// ...and look in that folder at every start (Zotero's 0 looks only after a Zotero update),
// so an add-on placed or replaced there after the first start is picked up.
user_pref("extensions.startupScanScopes", 1);
