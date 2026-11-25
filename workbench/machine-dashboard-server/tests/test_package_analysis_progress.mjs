import assert from "node:assert/strict";
import { progressForTask, mount, unmount } from "../web/assets/js/pages/package-error-analysis-task.js";
const event = (node, phase) => ({ message: "", data: {node, phase} });
let events = [event("parse", "start")];
assert.equal(progressForTask({events}).stages.parse, "active");
events.push(event("parse", "completed"), event("archive", "start"));
assert.equal(progressForTask({events}).stages.archive, "active");
events.push(event("archive", "completed"), event("worker", "skipped"), event("analysis", "start"));
assert.equal(progressForTask({events}).percent, 60);
assert.equal(progressForTask({events}).stages.worker, "skipped");
events.push(event("analysis", "failed"));
assert.equal(progressForTask({status:"failed", events}).stages.analysis, "failed");
const complete = [event("parse", "completed"), event("archive", "completed"), event("worker", "skipped"), event("analysis", "completed"), event("save_result", "completed")];
assert.equal(progressForTask({status:"completed", events:complete}).percent, 100);
assert.equal(progressForTask({events:[{message:"读取归档日志：开始"}]}).stages.archive, "active");

const elements = new Map();
function element() { return {textContent:"", value:"", style:{}, disabled:false, classList:{toggle(){}}, setAttribute(){}, querySelector(){return null;}}; }
for (const id of ["analysis-input","analysis-log","analysis-detail-title","analysis-detail-status","analysis-output-state","analysis-message","finish-analysis","progress-fill","progress-percent","progress-caption","run-analysis"]) elements.set(`#${id}`, element());
const nodes = ["parse","archive","worker","analysis","save_result"].map(step=>({...element(),dataset:{step}}));
const edges = ["parse-archive","archive-analysis","archive-worker","worker-analysis","worker-failure","analysis-save"].map(edge => {
  const classes = new Set();
  return {...element(),dataset:{edge},classes,classList:{toggle(name,on){if(on) classes.add(name); else classes.delete(name);}}};
});
let tick, cleared = false, requests = 0;
globalThis.document = {querySelector:s=>elements.get(s), querySelectorAll:selector=>selector === ".progress-node" ? nodes : edges};
globalThis.window = {__analysisTaskId:"existing", fetch:async()=>({ok:true,json:async()=>({ok:true,task: requests++ ? {id:"existing",status:"completed",events:complete} : {id:"existing",status:"queued",events:[event("parse","start")]}})}), setInterval:fn=>(tick=fn,1), clearInterval:()=>{cleared=true;}, dispatchEvent(){}};
await mount();
assert.equal(elements.get("#progress-caption").textContent.includes("解析输入"), true);
assert.equal(elements.get("#run-analysis").disabled, true);
tick();
await new Promise(resolve => setImmediate(resolve));
assert.equal(elements.get("#progress-percent").textContent, "100%");
assert.equal(edges.find(e=>e.dataset.edge === "archive-analysis").classes.has("taken"), true);
assert.equal(edges.find(e=>e.dataset.edge === "archive-worker").classes.has("taken"), false);
assert.equal(elements.get("#run-analysis").disabled, false);
assert.equal(cleared, true);
unmount();
console.log("progress transitions, fallback, resume polling and completion: passed");
