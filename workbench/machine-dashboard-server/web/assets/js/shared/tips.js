// Shared transient status message; message text is never interpreted as HTML.
let container;
export function showTip(message, { type = "info", duration = 2000 } = {}) {
  if (!container || !container.isConnected) {
    container = document.createElement("div");
    container.className = "workbench-tips";
    container.setAttribute("aria-live", "polite");
    document.body.append(container);
  }
  const tip = document.createElement("div");
  tip.className = `workbench-tip workbench-tip--${["success", "error"].includes(type) ? type : "info"}`;
  tip.textContent = String(message);
  container.append(tip);
  window.setTimeout(() => { tip.remove(); if (!container.childElementCount) { container.remove(); container = undefined; } }, duration);
}
