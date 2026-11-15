// The new tab: clock and date in Spanish, a search box on the user's default engine
// (chrome.search), and the bookmarks bar as tiles and ruled folders. No network of its
// own: favicons come from Chromium's cache through the _favicon endpoint.
"use strict";

const $ = (id) => document.getElementById(id);
const clock = $("clock"), date = $("date"), form = $("search"), q = $("q"), marks = $("marks");

// ---- clock ---------------------------------------------------------------------------
const SEP = getComputedStyle(document.documentElement).getPropertyValue("--clock-sep").trim().replace(/^"|"$/g, "") || ":";
const DAY = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "long" });
let timer = 0;

function tick() {
  clearTimeout(timer);
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  clock.textContent = hh + SEP + mm;
  clock.dateTime = `${hh}:${mm}`;
  date.textContent = DAY.format(now);
  timer = setTimeout(tick, 60_000 - now.getSeconds() * 1000 - now.getMilliseconds() + 50);
}
tick();
// A tab left in the background (or a machine that slept) catches up when shown.
document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });

// ---- search --------------------------------------------------------------------------
const SCHEME = /^[a-z][a-z0-9+.-]*:\/\//i;
const ADDRESS = /^(?:localhost|(?:[\w-]+\.)+[a-z]{2,}|\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?(?:[/?#]\S*)?$/i;

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = q.value.trim();
  if (!text) return;
  if (SCHEME.test(text)) chrome.tabs.update({ url: text });
  else if (ADDRESS.test(text)) chrome.tabs.update({ url: `https://${text}` });
  else chrome.search.query({ text, disposition: "CURRENT_TAB" });
});

document.addEventListener("keydown", (e) => {
  const typing = e.target instanceof HTMLInputElement;
  if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault();
    q.focus();
  } else if (e.key === "Escape" && e.target === q) {
    if (q.value) q.value = ""; else q.blur();
  }
});

// ---- bookmarks -----------------------------------------------------------------------
const favicon = (url, size) => {
  const u = new URL(chrome.runtime.getURL("/_favicon/"));
  u.searchParams.set("pageUrl", url);
  u.searchParams.set("size", String(size));
  return u.href;
};
const WEB = /^(?:https?|ftp|file):/i;

function label(node) {
  if (node.title) return node.title;
  try { return new URL(node.url).hostname || node.url; } catch { return node.url; }
}

function link(node, cls, size) {
  const a = document.createElement("a");
  a.className = cls;
  a.href = node.url;
  a.title = `${label(node)}\n${node.url}`;
  const img = document.createElement("img");
  img.src = favicon(node.url, size);
  img.alt = "";
  img.width = img.height = size;
  img.decoding = "async";
  const span = document.createElement("span");
  span.textContent = label(node);
  a.append(img, span);
  // A page may not link to chrome:// or other browser schemes: the tab is told instead.
  if (!WEB.test(node.url)) {
    a.addEventListener("click", (e) => {
      if (e.button || e.ctrlKey || e.metaKey || e.shiftKey) return;
      e.preventDefault();
      chrome.tabs.update({ url: node.url });
    });
  }
  return a;
}

// Bookmarklets cannot run from an extension page (its CSP refuses javascript: URLs).
const usable = (n) => n.url && !/^javascript:/i.test(n.url);

function folder(node, depth) {
  const frag = document.createDocumentFragment();
  const links = node.children.filter(usable);
  const h = document.createElement(depth ? "h3" : "h2");
  const count = document.createElement("small");
  count.textContent = String(links.length || "");
  h.append(node.title || "Sin nombre", count);
  frag.append(h);
  if (links.length) {
    const ul = document.createElement("ul");
    for (const n of links) {
      const li = document.createElement("li");
      li.append(link(n, "link", 16));
      ul.append(li);
    }
    frag.append(ul);
  }
  for (const sub of node.children.filter((n) => !n.url)) frag.append(folder(sub, depth + 1));
  return frag;
}

async function bars() {
  const [root] = await chrome.bookmarks.getTree();
  // Chromium 134+ names the bar (one local and, signed in, one account bar); older: id "1".
  const named = root.children.filter((n) => n.folderType === "bookmarks-bar");
  return named.length ? named : root.children.filter((n) => n.id === "1");
}

async function render() {
  let top;
  try {
    top = (await bars()).flatMap((b) => b.children ?? []);
  } catch (err) {
    marks.replaceChildren(Object.assign(document.createElement("p"), {
      className: "empty", textContent: `No se pudieron leer los marcadores (${err.message}).`,
    }));
    return;
  }
  const loose = top.filter(usable);
  const folders = top.filter((n) => !n.url);
  const out = [];
  if (loose.length) {
    const ul = document.createElement("ul");
    ul.className = "tiles";
    for (const n of loose) {
      const li = document.createElement("li");
      li.append(link(n, "tile", 32));
      ul.append(li);
    }
    out.push(ul);
  }
  if (folders.length) {
    const box = document.createElement("div");
    box.className = "folders";
    for (const f of folders) {
      const sec = document.createElement("section");
      sec.className = "folder";
      sec.append(folder(f, 0));
      box.append(sec);
    }
    out.push(box);
  }
  if (!out.length) {
    out.push(Object.assign(document.createElement("p"), {
      className: "empty",
      textContent: "La barra de marcadores está vacía. Ctrl+D guarda aquí la página que tengas abierta.",
    }));
  }
  marks.replaceChildren(...out);
}

let pending = 0;
const rerender = () => { cancelAnimationFrame(pending); pending = requestAnimationFrame(render); };
for (const ev of ["onCreated", "onRemoved", "onChanged", "onMoved", "onChildrenReordered", "onImportEnded"]) {
  chrome.bookmarks[ev]?.addListener(rerender);
}
render();
