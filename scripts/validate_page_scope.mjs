import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "workbench/machine-dashboard-server/web/assets/js/shared/page-scope.js"), "utf8")
  .replace("export function createPageScope", "function createPageScope");
const factory = new Function(`${source}\nreturn createPageScope;`)();
let intervals = new Set();
let aborted = false;
let release;
globalThis.window = {
  fetch(_url, options) {
    options.signal.addEventListener("abort", () => { aborted = true; });
    return new Promise(resolve => { release = () => resolve({ ok: true }); });
  },
  setInterval(fn) { const id = setInterval(fn, 100000); intervals.add(id); return id; },
  clearInterval(id) { clearInterval(id); intervals.delete(id); },
};
const scope = factory();
let ticks = 0;
scope.setInterval(() => ticks++, 1);
const inFlight = scope.fetch("/api/health");
scope.dispose();
release();
const settled = await Promise.race([inFlight.then(() => true), new Promise(resolve => setTimeout(() => resolve(false), 20))]);
assert.equal(settled, false, "disposed request must not resume page flow");
assert.equal(aborted, true);
assert.equal(intervals.size, 0);
assert.equal(scope.setInterval(() => {}, 1), undefined);
assert.equal(ticks, 0);

// Active requests still propagate real failures before disposal.
globalThis.window.fetch = async () => { throw new Error("network-failure"); };
const failed = factory();
await assert.rejects(() => failed.fetch("/api/failure"), /network-failure/);
failed.dispose();
console.log("page scope lifecycle validation passed");
