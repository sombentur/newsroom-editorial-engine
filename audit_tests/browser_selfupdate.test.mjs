// The extension reloads itself once when the app reports a newer version, and never loops.
import assert from "node:assert/strict";
const storage = { token: "t", workspaceEnabled: false };
let alarmHandler, reloads = 0;
const noop = () => {};
globalThis.chrome = {
  storage: { local: { setAccessLevel: noop,
    async get(keys) { const list = typeof keys === "string" ? [keys] : keys; return Object.fromEntries(list.filter(k => k in storage).map(k => [k, structuredClone(storage[k])])); },
    async set(o) { Object.assign(storage, structuredClone(o)); }, async remove(k) { delete storage[k]; } },
    session: { async get() { return {}; }, async set() {} } },
  tabs: { async get() { throw new Error("no tabs"); } },
  debugger: { onEvent: { addListener: noop }, onDetach: { addListener: noop } },
  alarms: { create: noop, onAlarm: { addListener(fn) { alarmHandler = fn; } } },
  runtime: { id: "ext", reload() { reloads++; }, onStartup: { addListener: noop }, onInstalled: { addListener: noop }, onMessage: { addListener: noop } },
};
globalThis.fetch = async (url) => ({ ok: true, status: 200, json: async () => (url.endsWith("/workspace") ? { latest_version: "9.9.9" } : { job: null }) });
await import(new URL("../chrome-extension/worker.js", import.meta.url).href);
await alarmHandler();
assert.equal(reloads, 1, "reloads once for a newer version");
assert.equal(storage.reloadedFor, "9.9.9");
await new Promise(r => setTimeout(r, 0));
await alarmHandler();
assert.equal(reloads, 1, "does not loop when the folder was not updated");
console.log("self-update: all checks passed");
process.exit(0);
