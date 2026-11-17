import { createPageScope } from "../shared/page-scope.js";
import { localApi } from "../shared/local-agent.js";
let scope;
export async function mount() {
  scope = createPageScope();
  const input = document.getElementById("storage"), msg = document.getElementById("msg"), choose = document.getElementById("load-storage"), check = document.getElementById("check-local-agent"), help = document.getElementById("local-agent-help");
  const reset = document.getElementById("reset-storage");
  const showHelp = () => { help.hidden = false; help.textContent = `请先下载下方客户端组件，在这台电脑解压并进入 machine-dashboard-client 目录，然后在 PowerShell 执行：powershell -NoProfile -ExecutionPolicy Bypass -File .\\setup-client.ps1 -DashboardUrl '${location.origin}' -Start。保持窗口运行，再点击“检查本机服务”。需要 Python 3.11 或更新版本。`; };
  const loadStorage = async () => { const data = await localApi("/api/settings/storage", { signal: scope.signal }); input.value = data.settings.storage_dir; return data; };
  try { await loadStorage(); msg.textContent = "已加载这台电脑上的保存路径"; } catch (error) { if (error.name !== "AbortError") { msg.textContent = error.message; showHelp(); } }
  check.onclick = async () => { check.disabled = true; try { const data = await localApi("/health", { signal: scope.signal }); if (data.ok) { await loadStorage(); msg.textContent = "本机服务已连接，可以选择目录"; help.hidden = true; } else msg.textContent = "本机服务未就绪"; } catch (error) { if (error.name !== "AbortError") { msg.textContent = error.message; showHelp(); } } finally { check.disabled = false; } };
  choose.onclick = async () => { choose.disabled = true; msg.textContent = "正在打开这台电脑的目录选择窗口..."; try { const data = await localApi("/api/settings/storage/choose", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); input.value = data.settings.storage_dir; msg.textContent = data.selected ? "已更新这台电脑的保存目录" : "未选择目录"; } catch (error) { msg.textContent = error.message; } finally { choose.disabled = false; } };
  reset.onclick = async () => { reset.disabled = true; try { const data = await localApi("/api/settings/storage/reset", { method: "POST" }); input.value = data.settings.storage_dir; msg.textContent = "已恢复默认目录"; } catch (error) { msg.textContent = error.message; } finally { reset.disabled = false; } };
}
export function unmount() { scope?.dispose(); }
