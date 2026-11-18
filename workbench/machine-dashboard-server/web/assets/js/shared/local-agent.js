export const LOCAL_AGENT_ORIGIN = "http://127.0.0.1:18991";
export async function localApi(path, options = {}) {
  let response;
  try { response = await fetch(LOCAL_AGENT_ORIGIN + path, { cache: "no-store", ...options }); }
  catch (error) { if (error.name === "AbortError") throw error; const e = new Error("本机本地接入服务未启动，请运行 machine-dashboard-client 的 local_agent"); e.cause = error; throw e; }
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    const mismatch = data.error === "untrusted dashboard origin" && data.configured_dashboard_url
      ? `本机服务已启动，但绑定的是 ${data.configured_dashboard_url}；当前工作台是 ${location.origin}。请在客户端目录执行：powershell -NoProfile -ExecutionPolicy Bypass -File .\\setup-client.ps1 -DashboardUrl '${location.origin}' -Start`
      : (data.error || "本地接入服务请求失败");
    throw new Error(mismatch);
  }
  return data;
}
