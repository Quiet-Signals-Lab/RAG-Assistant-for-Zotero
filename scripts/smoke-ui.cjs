/**
 * Smoke test for the interface switch: the app must render, switch from search to
 * the chat and back (through Settings and through the chat's own button), survive a
 * reload in each mode, and do one search and one chat turn, with no console error,
 * failed load or renderer crash along the way. The stored interface setting is put back.
 *
 *   npm run smoke:ui            # needs the backend on :8000 and Vite on :5173 (npm run dev)
 *   npm run smoke:ui -- --no-chat   # skip the chat turn (no model set up)
 *
 * Runs the repo's own Electron offscreen. Exits 1 on any failure, 2 when a server is down.
 */
const { app, BrowserWindow } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");

const arg = (name, fallback) => { const i = process.argv.indexOf(name); return i === -1 ? fallback : process.argv[i + 1]; };
const APP = arg("--app", "http://localhost:5173/");
const API = arg("--api", "http://localhost:8000");
const NO_CHAT = process.argv.includes("--no-chat");
const QUERY = arg("--query", "learning");

const problems = [];
const warnings = [];
const steps = [];
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function preflight() {
  for (const [name, url, hint] of [["backend", `${API}/health`, "npm run dev:backend"], ["frontend", APP, "npm run dev:frontend"]]) {
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
    } catch (e) {
      console.error(`${name} is not answering at ${url} (${e.message}). Start it with: ${hint}`);
      process.exit(2);
    }
  }
}

async function settings(patch) {
  const r = await fetch(`${API}/api/settings`, patch ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) } : undefined);
  return r.json();
}

async function main() {
  await preflight();
  const before = (await settings()).interfaceMode || "desk";
  const win = new BrowserWindow({ show: false, width: 1440, height: 820, webPreferences: { offscreen: true } });
  const wc = win.webContents;
  wc.on("console-message", (_e, level, message, line, source) => {
    // The CSP warning is the harness's: the app's main process sets the policy on its own window.
    if (level < 2 || /Download the React DevTools|\[vite\]|Electron Security Warning/.test(message)) return;
    (level === 3 ? problems : warnings).push(`console ${level === 3 ? "error" : "warning"}: ${message.slice(0, 300)} (${path.basename(source || "")}:${line})`);
  });
  wc.on("did-fail-load", (_e, code, desc, url) => problems.push(`failed to load ${url}: ${desc} (${code})`));
  wc.on("render-process-gone", (_e, d) => problems.push(`renderer gone: ${d.reason}`));
  wc.on("unresponsive", () => problems.push("renderer unresponsive"));

  const js = (code) => wc.executeJavaScript(code).catch((e) => { problems.push(`script failed: ${String(e).slice(0, 160)}`); return undefined; });
  const until = async (name, code, ms = 30000) => {
    const started = Date.now();
    while (Date.now() - started < ms) {
      if (await js(code)) { steps.push(`ok   ${name}`); return true; }
      await wait(250);
    }
    steps.push(`FAIL ${name} (after ${ms / 1000} s)`);
    problems.push(`timed out: ${name}`);
    const shot = path.join(os.tmpdir(), `smoke-ui-${name.replace(/\W+/g, "-")}.png`);
    fs.writeFileSync(shot, (await wc.capturePage()).toPNG());
    steps.push(`     screenshot: ${shot}`);
    return false;
  };
  const click = (selector) => js(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) return false; el.click(); return true; })()`);
  const toSettings = async () => { await click("button[aria-label='Settings']"); await until("settings page opens", `!!document.querySelector("input[name=interfaceMode]")`); };
  const chooseMode = async (mode) => {
    await click(`input[name=interfaceMode][value=${mode}]`);
    await until(`setting saved as ${mode}`, `document.querySelector("input[name=interfaceMode][value=${mode}]")?.checked === true`);
    await wait(600); // the save round-trips to the backend before the shell can follow it
    await click("button.btn"); // "← Back to …", the first button on the page
  };

  try {
    await settings({ interfaceMode: "desk" });
    await win.loadURL(APP);
    await until("search interface renders", `!!document.querySelector(".desk")`);

    // Settings → legacy chat
    await toSettings();
    await chooseMode("chat");
    await until("chat renders after the switch", `!!document.querySelector(".app-shell .chat-input__textarea")`);
    await win.reload();
    await until("chat renders after a reload", `!!document.querySelector(".app-shell .chat-input__textarea")`);

    if (!NO_CHAT) {
      await js(`document.querySelector(".chat-input__textarea").focus()`);
      wc.insertText(`What does my library say about ${QUERY}?`);
      await wait(300);
      await js(`document.querySelector(".chat-input__textarea").dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }))`);
      await until("chat turn gets an answer or an error message", `!!document.querySelector(".message--assistant:not([aria-busy]), .chat-view__error")`, 90000);
    }

    // The chat's own "switch to search" button
    await click("button[title='Switch to search']");
    await until("search interface renders from the chat's button", `!!document.querySelector(".desk")`);

    // Settings → legacy chat → Settings → search
    await toSettings();
    await chooseMode("chat");
    await until("chat renders a second time", `!!document.querySelector(".app-shell")`);
    await toSettings();
    await chooseMode("desk");
    await until("search interface renders after switching back", `!!document.querySelector(".desk")`);
    await win.reload();
    await until("search interface renders after a reload", `!!document.querySelector(".desk")`);

    await js(`const t = document.querySelector("#desk-query"); t.focus();`);
    wc.insertText(QUERY);
    await wait(300);
    await click("form[role=search] button[type=submit]");
    await until("a search returns and the reading shows", `!!document.querySelector(".reading") && !document.querySelector(".loading-rule")`, 90000);
  } finally {
    await settings({ interfaceMode: before });
  }

  console.log(steps.join("\n"));
  if (warnings.length) console.log("\nWarnings (not failures):\n" + [...new Set(warnings)].map((w) => `- ${w}`).join("\n"));
  const unique = [...new Set(problems)];
  if (unique.length) {
    console.log("\nProblems:\n" + unique.map((p) => `- ${p}`).join("\n"));
    process.exitCode = 1;
  } else {
    console.log("\nNo console errors, failed loads or renderer crashes.");
  }
  app.quit();
}

setTimeout(() => { console.error("smoke-ui: gave up after 5 minutes"); process.exit(1); }, 300000);
app.whenReady().then(main).catch((e) => { console.error(e); process.exit(1); });
