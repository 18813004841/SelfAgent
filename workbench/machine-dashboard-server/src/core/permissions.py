MODULES = {
    "overview": "总览", "scheduler": "定时任务", "tasks": "任务", "calendar": "日程",
    "docs": "文档", "manage": "管理", "settings": "设置", "code-review": "代码检查",
    "central-server": "中央服务器", "openai-agent": "OpenAiAgent", "local-codex": "本地 Codex",
}
ROLES = {"user": "普通用户", "advanced": "高级用户", "developer": "开发者", "admin": "管理员"}
ROLE_LEVEL = {"user": 1, "advanced": 2, "developer": 3, "admin": 4}
ROLE_MODULES = {
    "user": set(MODULES) - {"central-server", "openai-agent"},
    "advanced": set(MODULES) - {"central-server", "openai-agent"},
    "developer": set(MODULES),
    "admin": set(MODULES),
}
def role_at_least(user, role): return bool(user and ROLE_LEVEL.get(user.get("role", "user"), 1) >= ROLE_LEVEL[role])
def modules_for_role(role): return sorted(ROLE_MODULES.get(role, ROLE_MODULES["user"]))
ALL_MODULES = tuple(MODULES)
API_MODULES = {
    "/api/machines": "overview", "/api/processes": "overview", "/api/health": "overview",
    "/api/scheduler": "scheduler", "/api/scheduler-tasks": "scheduler", "/api/schedules": "scheduler",
    "/api/tools": "manage", "/api/central-server": "central-server", "/api/central-client": "central-server",
    "/api/openai-agent": "openai-agent", "/api/local-codex": "local-codex", "/api/settings": "settings",
    "/api/code-review": "code-review", "/api/scheduler-tasks/code-review": "code-review",
}
def module_for_path(path):
    if path.startswith("/pages/"):
        return path[len("/pages/"):].split(".", 1)[0]
    if path.startswith("/pages/users"):
        return "manage"
    if path.startswith("/api/auth") or path.startswith("/api/users") or path == "/api/modules": return None
    for prefix, module in API_MODULES.items():
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "-"): return module
    return None
