// Chromium loads --load-extension extensions after it has opened the first window, so the
// tab it starts with is still its own new tab page. Once this extension is up, send those
// tabs to chrome://newtab/ again: now that address resolves to newtab.html.
// Only at browser start (and on load): a later wake-up of this worker must not reload
// a new tab the user is typing in. «tabs» is needed to read a tab's address.
"use strict";

async function adopt() {
  for (const tab of await chrome.tabs.query({ url: "chrome://newtab/*" })) {
    chrome.tabs.update(tab.id, { url: "chrome://newtab/" });
  }
}

chrome.runtime.onStartup.addListener(adopt);
chrome.runtime.onInstalled.addListener(adopt);
