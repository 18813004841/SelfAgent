import { createPageScope } from "../shared/page-scope.js";
import { localApi } from "../shared/local-agent.js";
let scope;
export async function mount() {
  scope = createPageScope();
  const input = document.getElementById("storage"), msg = document.getElementById("msg"), choose = document.getElementById("load-storage"), check = document.getElementById("check-local-agent"), help = document.getElementById("local-agent-help"), versionLabel = document.getElementById("local-agent-version"), download = document.getElementById("local-agent-download"), updateHelp = document.getElementById("local-agent-update-help");
  const reset = document.getElementById("reset-storage");
  const showHelp = () => { help.hidden = false; help.textContent = `请先下载下方客户端组件，在这台电脑解压并进入 machine-dashboard-client 目录，然后在 PowerShell 执行：powershell -NoProfile -ExecutionPolicy Bypass -File .\\setup-client.ps1 -DashboardUrl '${location.origin}' -Start。保持窗口运行，再点击“检查本机服务”。需要 Python 3.11 或更新版本。`; };
  const loadStorage = async () => { const data = await localApi("/api/settings/storage", { signal: scope.signal }); input.value = data.settings.storage_dir; return data; };
  const loadVersion = async () => {
    const [local, release] = await Promise.all([
      localApi("/api/local-agent/version", { signal: scope.signal }),
      fetch("/api/local-agent/version", { cache: "no-store", signal: scope.signal }).then(r => r.json()),
    ]);
    if (!release.ok) throw Error(release.error || "无法读取发布版本");
    const current = local.version || "未安装";
    const latest = release.version;
    versionLabel.textContent = current === latest ? `${current}（最新）` : `当前 ${current}，可更新到 ${latest}`;
    const upToDate = current === latest;
    download.textContent = upToDate ? "重新下载本机客户端组件" : `更新客户端到 ${latest}`;
    download.classList.toggle("primary", !upToDate);
    updateHelp.textContent = upToDate ? "（当前已是最新版本）" : "（点击下载更新包，然后运行包内 update-client.ps1）";
  };
  try { await loadStorage(); await loadVersion(); msg.textContent = "已加载这台电脑上的保存路径"; } catch (error) { if (error.name !== "AbortError") { msg.textContent = error.message; versionLabel.textContent = "未连接或版本不可用"; showHelp(); } }
  check.onclick = async () => { check.disabled = true; try { const data = await localApi("/health", { signal: scope.signal }); if (data.ok) { await loadStorage(); await loadVersion(); msg.textContent = "本机服务已连接，可以选择目录"; help.hidden = true; } else msg.textContent = "本机服务未就绪"; } catch (error) { if (error.name !== "AbortError") { msg.textContent = error.message; showHelp(); } } finally { check.disabled = false; } };
  choose.onclick = async () => { choose.disabled = true; msg.textContent = "正在打开这台电脑的目录选择窗口..."; try { const data = await localApi("/api/settings/storage/choose", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); input.value = data.settings.storage_dir; msg.textContent = data.selected ? "已更新这台电脑的保存目录" : "未选择目录"; } catch (error) { msg.textContent = error.message; } finally { choose.disabled = false; } };
  reset.onclick = async () => { reset.disabled = true; try { const data = await localApi("/api/settings/storage/reset", { method: "POST" }); input.value = data.settings.storage_dir; msg.textContent = "已恢复默认目录"; } catch (error) { msg.textContent = error.message; } finally { reset.disabled = false; } };
}
export function unmount() { scope?.dispose(); }
