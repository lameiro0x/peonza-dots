// The rice's look for Feishin, written the way Feishin itself would write it: Feishin
// keeps its settings in the renderer's localStorage (zustand persist), so this runs a
// hidden window of the same Electron, on the same file:// origin and the same profile,
// and merges a few keys into two stores — `store_settings` and
// `store_full_screen_player`. Run by seed.sh, never while Feishin runs.
//
// Only the keys below are ever written; server, login, queue, playback and every other
// choice stay as the user left them. A profile with no settings yet also gets FIRST_RUN
// (Spanish, native frame). Each merge backs up the localStorage LevelDB first and drops
// the backup again if nothing changed, so a second run is a no-op.
//
// Partial on purpose: Feishin deep-merges what it finds over its defaults. The versions
// are Feishin 1.17's; a store at any other version is left alone (a newer Feishin may
// have reshaped it), and the run says so.
//
//   electron seed.js [APP.ASAR] [--dry-run | --check]
//   --dry-run prints the key names only; --check writes nothing and exits 3 if anything
//   is still to change (seed.sh runs it in a fresh process to see the write on disk).
const { app, BrowserWindow, session } = require('electron');
const fs = require('fs');
const path = require('path');

const SETTINGS_VERSION = 34;
const FULL_SCREEN_VERSION = 5;

// The analyser's three pure channels, which ryce.css re-inks in the current theme's
// colours: red the loud bars (the theme's warm accent), green the body (the media hue),
// blue the quiet floor (the mark grey). With `bar-level` colouring each bar takes one
// stop by its height: up to 0.1 the floor, up to 0.35 the body, above it the accent.
// Upserted by name, so the user's own gradients stay.
const RYCE_GRADIENT = {
    name: 'ryce',
    colorStops: [
        { color: '#ff0000', level: 1, levelEnabled: true },
        { color: '#00ff00', level: 0.35, levelEnabled: true },
        { color: '#0000ff', level: 0.1, levelEnabled: true },
    ],
};

const LOOK = {
    store_settings: {
        general: {
            // The theme from ~/.config/feishin/Themes/ryce.json (theme/templates/feishin):
            // without it the bars below would show their raw red, green and blue.
            theme: 'ryce',
            themeDark: 'ryce',
            themeLight: 'ryce',
            followSystemTheme: false,
            showVisualizerInSidebar: true,
        },
        visualizer: {
            type: 'audiomotionanalyzer',
            audiomotionanalyzer: {
                gradient: 'ryce',
                colorMode: 'bar-level',
                channelLayout: 'single',
                // The corona: a closed ring of round 1/8-octave bars, mirrored left and
                // right, around the full-screen player's cover disc. radius 0.75 puts the
                // ring's inside (0.375 × radius × the canvas' short side) at the 56 % disc's
                // edge (ryce.css); ryce.css also turns the ring, so no spin of its own here.
                mode: 3,
                radial: true,
                radialInvert: false,
                radius: 0.75,
                mirror: -1,
                spinSpeed: 0,
                roundBars: true,
                barSpace: 0.25,
                alphaBars: false,
                lumiBars: false,
                ledBars: false,
                outlineBars: false,
                showPeaks: true,
                fadePeaks: true,
                peakLine: false,
                reflexRatio: 0,
                // Even all round: a log scale from 30 Hz to 16 kHz, D-weighting to lift the
                // presence band, and a 3.4th-root amplitude so quiet bands still show and
                // the ring stays closed; only the loud ones reach the accent.
                frequencyScale: 'log',
                minFreq: 30,
                maxFreq: 16000,
                weightingFilter: 'D',
                linearAmplitude: true,
                linearBoost: 3.4,
                smoothing: 0.75,
                showScaleX: false,
                showScaleY: false,
            },
        },
    },
    store_full_screen_player: {
        // The cover's shapes as a grey ghost behind the player (ryce.css tones it), and the
        // visualizer tab, where the ring turns around the cover.
        dynamicBackground: true,
        dynamicIsImage: true,
        activeTab: 'visualizer',
    },
};

const FIRST_RUN = {
    general: { language: 'es', useThemeAccentColor: true },
    // Native frame, as the main process already assumes on Linux (its store default):
    // Hyprland tiles the window and draws its border, so no in-app title bar and no
    // «settings differ, restart» toast on first start.
    window: { windowBarStyle: 'linux' },
};

const VERSIONS = { store_settings: SETTINGS_VERSION, store_full_screen_player: FULL_SCREEN_VERSION };

const isPlain = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// Deep-merge `patch` into `into` in place; returns the dotted names of what changed.
function merge(into, patch, at = '') {
    const changed = [];
    for (const [k, v] of Object.entries(patch)) {
        const name = at ? `${at}.${k}` : k;
        if (isPlain(v)) {
            if (!isPlain(into[k])) into[k] = {};
            changed.push(...merge(into[k], v, name));
        } else if (!same(into[k], v)) {
            into[k] = structuredClone(v);
            changed.push(name);
        }
    }
    return changed;
}

// What one store becomes: { text, changed } or { skip } with the reason.
function plan(key, raw) {
    let stored;
    try {
        stored = raw === null ? { state: {}, version: VERSIONS[key] } : JSON.parse(raw);
    } catch {
        return { skip: `${key} is not JSON` };
    }
    if (!isPlain(stored) || !isPlain(stored.state)) return { skip: `${key} has no state object` };
    if (stored.version !== VERSIONS[key]) {
        return { skip: `${key} is at version ${stored.version}, this seed knows ${VERSIONS[key]}` };
    }
    const patch = structuredClone(LOOK[key]);
    if (key === 'store_settings') {
        const own = stored.state.visualizer?.audiomotionanalyzer?.customGradients;
        const gradients = Array.isArray(own) ? own.filter((g) => g?.name !== RYCE_GRADIENT.name) : [];
        const at = Array.isArray(own) ? own.findIndex((g) => g?.name === RYCE_GRADIENT.name) : -1;
        gradients.splice(at < 0 ? gradients.length : at, 0, RYCE_GRADIENT);
        patch.visualizer.audiomotionanalyzer.customGradients = gradients;
        if (raw === null) merge(patch, FIRST_RUN);
    }
    const changed = merge(stored.state, patch);
    return { text: JSON.stringify(stored), changed: changed.map((c) => `${key}: ${c}`) };
}

const check = process.argv.includes('--check');
const dryRun = check || process.argv.includes('--dry-run');
// The release notes Feishin shows when this key differs from its own version (stored
// JSON-quoted): a first start opens on the login form instead. The app's path comes
// from seed.sh; without it the notes show once, as in a plain install.
const asar = process.argv.find((a) => a.endsWith('app.asar'));
let seen = null;
try {
    seen = asar ? JSON.stringify(require(path.join(asar, 'package.json')).version) : null;
} catch {
    seen = null;
}

app.setPath('userData', path.join(app.getPath('appData'), 'feishin'));
const leveldb = path.join(app.getPath('userData'), 'Local Storage', 'leveldb');

// Feishin takes this same lock on its profile: holding it means Feishin is closed and
// cannot start until the merge is done.
if (!app.requestSingleInstanceLock()) {
    console.error('feishin seed: Feishin está abierto; ciérralo y vuelve a ejecutarlo');
    process.exit(1);
}

app.whenReady().then(async () => {
    let backup = null;
    let wrote = false;
    const win = new BrowserWindow({ show: false, webPreferences: { javascript: true } });
    try {
        // Copied before the page opens the database, so the copy is a consistent one.
        if (!dryRun && fs.existsSync(leveldb)) {
            backup = `${leveldb}.ryce-${new Date().toISOString().replace(/[:.]/g, '-')}`;
            fs.cpSync(leveldb, backup, { recursive: true });
        }
        await win.loadFile(__filename);
        const keys = Object.keys(LOOK);
        const raws = await win.webContents.executeJavaScript(
            `${JSON.stringify(keys)}.map((k) => localStorage.getItem(k))`,
        );
        const writes = {};
        const changed = [];
        keys.forEach((key, i) => {
            const p = plan(key, raws[i]);
            if (p.skip) {
                console.error(`feishin seed: ${p.skip}; left alone`);
                process.exitCode = 1;
            } else if (p.changed.length) {
                writes[key] = p.text;
                changed.push(...p.changed);
            }
        });
        if (raws[0] === null && seen !== null) writes.version = seen;
        if (check) {
            if (changed.length) process.exitCode = 3;
        } else if (dryRun) {
            console.log(changed.length ? changed.join('\n') : 'feishin seed: nothing to change');
        } else if (Object.keys(writes).length) {
            await win.webContents.executeJavaScript(
                `Object.entries(${JSON.stringify(writes)}).forEach(([k, v]) => localStorage.setItem(k, v))`,
            );
            await session.defaultSession.flushStorageData();
            wrote = true;
            console.log(`feishin seed: ${changed.length} settings written${backup ? `; the previous ones are in ${backup}` : ''}`);
        } else {
            console.log('feishin seed: settings already there, left alone');
        }
    } catch (e) {
        console.error(`feishin seed: could not write the settings (${e.message})`);
        process.exitCode = 1;
    } finally {
        if (backup && !wrote) fs.rmSync(backup, { recursive: true, force: true });
        win.destroy();
        app.quit();
    }
});
