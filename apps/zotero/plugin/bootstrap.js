/* Ryce for Zotero: the desktop's current theme, live.
 *
 * ryce-theme swaps ~/.local/state/ryce/theme/current (a symlink) to another
 * themes/<id>/ directory. Every second this plugin resolves that link; when it, or the
 * mtime of a file below, changed, it
 *   - registers <theme>/zotero/ryce.css as a user sheet (it scopes itself to Zotero's
 *     own documents with @-moz-document) and drops the previous theme's sheet, and
 *   - writes <theme>/zotero/reader.json as one custom reader theme, id "custom-ryce",
 *     next to the user's own custom themes (Zotero keeps them in the synced setting
 *     readerCustomThemes), and points reader.lightTheme/darkTheme at it unless the
 *     user picked another theme there.
 * userChrome.css would need a restart per switch and cannot reach the reader's paper.
 * RYCE_THEME_STATE overrides the state directory (the stage and tests use it).
 * Installed by apps/zotero/setup.py as an extension proxy file.
 */

"use strict";

const READER_THEME = "custom-ryce";
const READER_PREFS = ["reader.lightTheme", "reader.darkTheme"];
const POLL_MS = 1000;

var sss = null;      // nsIStyleSheetService
var sheet = null;    // nsIURI of the registered sheet
var timer = null;
var seen = "";       // what the last poll found: theme dir + mtimes

function log(msg) {
  Zotero.debug(`Ryce: ${msg}`);
}

function themeDir() {
  let state = Services.env.get("RYCE_THEME_STATE")
    || PathUtils.join(Services.dirsvc.get("Home", Ci.nsIFile).path, ".local", "state", "ryce", "theme");
  let file = Zotero.File.pathToFile(PathUtils.join(state, "current"));
  try {
    file.normalize(); // realpath: the link's target, so a switch changes the path
    return file.path;
  }
  catch (e) {
    return null; // no theme state (yet): keep whatever is applied
  }
}

function mtime(path) {
  let f = Zotero.File.pathToFile(path);
  return f.exists() ? f.lastModifiedTime : 0;
}

function applySheet(path) {
  let next = null;
  if (path) {
    next = Services.io.newFileURI(Zotero.File.pathToFile(path));
    // The query makes a re-rendered file a new sheet; a file: URI ignores it on load.
    next = Services.io.newURI(`${next.spec}?${mtime(path)}`);
    sss.loadAndRegisterSheet(next, sss.USER_SHEET);
  }
  if (sheet && sss.sheetRegistered(sheet, sss.USER_SHEET)) {
    sss.unregisterSheet(sheet, sss.USER_SHEET);
  }
  sheet = next;
}

async function applyReaderTheme(theme) {
  let lib = Zotero.Libraries.userLibraryID;
  let list = Zotero.SyncedSettings.get(lib, "readerCustomThemes");
  list = Array.isArray(list) ? list : [];
  let next = list.filter(t => t.id !== READER_THEME);
  if (theme) {
    let ours = { id: READER_THEME, label: theme.label, background: theme.background, foreground: theme.foreground };
    let at = list.findIndex(t => t.id === READER_THEME);
    next.splice(at < 0 ? next.length : at, 0, ours); // keep its place: no reorder on a switch
  }
  if (JSON.stringify(next) !== JSON.stringify(list)) {
    if (next.length) {
      await Zotero.SyncedSettings.set(lib, "readerCustomThemes", next);
    }
    else {
      await Zotero.SyncedSettings.clear(lib, "readerCustomThemes");
    }
  }
  for (let pref of READER_PREFS) {
    let mine = Zotero.Prefs.get(pref) === READER_THEME;
    if (theme && (mine || !Zotero.Prefs.prefHasUserValue(pref))) {
      Zotero.Prefs.set(pref, READER_THEME);
    }
    else if (!theme && mine) {
      Zotero.Prefs.clear(pref);
    }
  }
}

async function readTheme(path) {
  if (!mtime(path)) {
    return null;
  }
  let t = JSON.parse(await Zotero.File.getContentsAsync(path));
  for (let key of ["background", "foreground"]) {
    if (!/^#[0-9a-f]{6}$/i.test(t[key] || "")) {
      throw new Error(`${path}: "${key}" is not a #rrggbb colour`);
    }
  }
  return t;
}

async function poll() {
  let dir = themeDir();
  if (!dir) {
    return;
  }
  let css = PathUtils.join(dir, "zotero", "ryce.css");
  let reader = PathUtils.join(dir, "zotero", "reader.json");
  let now = `${dir}|${mtime(css)}|${mtime(reader)}`;
  if (now === seen) {
    return;
  }
  seen = now;
  log(`theme ${dir}`);
  try {
    applySheet(mtime(css) ? css : null);
    await applyReaderTheme(await readTheme(reader));
  }
  catch (e) {
    Zotero.logError(e); // a broken theme file must not stop the next switch
  }
}

function startup({ id, version }, reason) {
  sss = Cc["@mozilla.org/content/style-sheet-service;1"].getService(Ci.nsIStyleSheetService);
  poll();
  timer = Cc["@mozilla.org/timer;1"].createInstance(Ci.nsITimer);
  timer.initWithCallback({ notify: () => poll() }, POLL_MS, Ci.nsITimer.TYPE_REPEATING_SLACK);
  log(`${id} ${version} started`);
}

function shutdown(data, reason) {
  if (timer) {
    timer.cancel();
    timer = null;
  }
  if (reason === APP_SHUTDOWN) {
    return;
  }
  applySheet(null);
  seen = "";
  // Disabled or removed: give the reader back the user's own choice.
  if (reason === ADDON_DISABLE || reason === ADDON_UNINSTALL) {
    applyReaderTheme(null).catch(e => Zotero.logError(e));
  }
}

function install() {}

function uninstall() {}
