const roleNames = { user: "普通用户", advanced: "高级用户", developer: "开发者", admin: "管理员" };
export async function mount() {
  const msg = document.querySelector("#profile-msg");
  try {
    const response = await fetch("/api/auth/session", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || !data.user) throw new Error("登录状态已失效");
    const user = data.user;
    document.querySelector("#profile-username").textContent = user.username;
    document.querySelector("#profile-display").textContent = user.display_name || "—";
    document.querySelector("#profile-role").textContent = roleNames[user.role] || user.role;
  } catch (error) {
    msg.textContent = error.message;
  }
  document.querySelector("#profile-logout").onclick = async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const response = await fetch("/api/auth/logout", { method: "POST" });
      if (!response.ok) throw new Error("退出登录失败");
      location.reload();
    } catch (error) {
      button.disabled = false;
      msg.textContent = error.message;
    }
  };
}
export function unmount() {}
