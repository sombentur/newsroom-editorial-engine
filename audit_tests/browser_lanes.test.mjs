// Simulates Chrome + the Newsroom app to exercise the extension's two-lane loop.
import assert from "node:assert/strict";


const storage = { token: "t", workspaceEnabled: true, workspace: { research: { tabId: 11 }, image: { tabId: 22 } } };
const tabs = new Map([[11, { id: 11, url: "https://gemini.google.com/app", status: "complete", groupId: 5, windowId: 1 }],
                      [22, { id: 22, url: "https://chatgpt.com/", status: "complete", groupId: 5, windowId: 1 }]]);
let alarmHandler;
const noop = () => {};
globalThis.chrome = {
  storage: {
    local: {
      setAccessLevel: noop,
      async get(keys) { const list = typeof keys === "string" ? [keys] : keys; return Object.fromEntries(list.filter(k => k in storage).map(k => [k, structuredClone(storage[k])])); },
      async set(obj) { Object.assign(storage, structuredClone(obj)); },
      async remove(k) { delete storage[k]; },
    },
    session: { _s: { workspace: { research: { tabId: 11 }, image: { tabId: 22 } } },
      async get(k) { return { [k]: structuredClone(this._s[k]) }; }, async set(o) { Object.assign(this._s, structuredClone(o)); } },
  },
  tabs: {
    async get(id) { if (!tabs.has(id)) throw new Error("No tab with id: " + id); return tabs.get(id); },
    async sendMessage(id, msg) { if (msg.type === "observe") return { elements: [{ editable: true, disabled: false, empty: true, name: "prompt" }], snapshot: "s", text: "", url: tabs.get(id).url }; return {}; },
    async update() {}, async remove() {}, async create() { throw new Error("unexpected create"); }, async group() { return 5; },
  },
  debugger: { async attach() {}, async detach() {}, async sendCommand() { return {}; }, onEvent: { addListener: noop }, onDetach: { addListener: noop } },
  alarms: { create: noop, onAlarm: { addListener(fn) { alarmHandler = fn; } } },
  runtime: { id: "ext", onStartup: { addListener: noop }, onInstalled: { addListener: noop }, onMessage: { addListener: noop } },
};

// Fake app: two queued jobs (one per lane) plus a legacy saved research job needing attention.
const jobs = {
  old: { id: "old", kind: "research", status: "attention", prompt: "p", message: "needs you" },
  img: { id: "img", kind: "image", status: "queued", prompt: "draw" },
  res: { id: "res", kind: "research", status: "queued", prompt: "research" },
};
const claims = [];
globalThis.fetch = async (url, init = {}) => {
  const path = url.replace("http://127.0.0.1:8001/api/browser-worker", "");
  const body = init.body ? JSON.parse(init.body) : undefined;
  let out = {};
  if (path === "/workspace") out = {};
  else if (path === "/claim") {
    claims.push(body.lane);
    const kinds = body.lane === "research" ? ["research"] : ["image", "seo"];
    const job = Object.values(jobs).find(j => j.status === "queued" && kinds.includes(j.kind));
    if (job) job.status = "running";
    out = { job: job ? { ...job } : null };
  } else if (path.startsWith("/jobs/")) out = { ...jobs[path.split("/")[2]] };
  return { ok: true, status: 200, json: async () => out };
};

storage.active = { job: jobs.old, tabId: 11, workspace: true, submitted: true, protocol: 2 };
await import(new URL("../chrome-extension/worker.js", import.meta.url).href);
await alarmHandler();

assert.equal(storage.active, undefined, "legacy single-lane job migrated");
assert.equal(storage["active:research"].job.id, "old", "attention job kept in the research lane");
assert.deepEqual(claims, ["image"], "research lane busy with attention job; image lane still claims");
assert.equal(storage["active:image"].job.id, "img", "ChatGPT lane picked up the image job");

// The attention job is released server-side -> research lane frees and claims the next research job.
jobs.old.status = "cancelled";
await new Promise(r => setTimeout(r, 0));
await alarmHandler();
assert.equal(storage["active:research"], undefined, "cancelled job cleared from research lane");
await alarmHandler();
assert.equal(storage["active:research"].job.id, "res", "research lane claimed the queued research job");
assert.ok(tabs.has(11), "work tab was not closed when its job was cancelled");
console.log("lanes harness: all checks passed");
process.exit(0);
