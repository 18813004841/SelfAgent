MODULES = {
    "overview": "总览", "scheduler": "定时任务", "tasks": "任务", "frontend": "前端模块",
    "store": "商城", "manage": "管理", "settings": "设置", "code-review": "代码检查",
    "central-server": "中央服务器", "openai-agent": "OpenAiAgent", "local-codex": "本地 Codex", "server-maintenance": "服务器开发维护",
}
ROLES = {"user": "普通用户", "advanced": "高级用户", "developer": "开发者", "admin": "管理员"}
ROLE_LEVEL = {"user": 1, "advanced": 2, "developer": 3, "admin": 4}
ROLE_MODULES = {
    "user": set(MODULES) - {"central-server", "openai-agent", "server-maintenance"},
    "advanced": set(MODULES) - {"central-server", "openai-agent", "server-maintenance"},
    "developer": set(MODULES),
    "admin": set(MODULES),
}
def role_at_least(user, role): return bool(user and ROLE_LEVEL.get(user.get("role", "user"), 1) >= ROLE_LEVEL[role])
def modules_for_role(role): return sorted(ROLE_MODULES.get(role, ROLE_MODULES["user"]))
ALL_MODULES = tuple(MODULES)
API_MODULES = {
    "/api/machines": "overview", "/api/processes": "overview", "/api/health": "overview",
    "/api/scheduler": "scheduler", "/api/scheduler-tasks": "scheduler", "/api/schedules": "scheduler",
    "/api/jenkins": "manage", "/api/tools": "manage", "/api/central-server": "central-server", "/api/central-client": "central-server",
    "/api/openai-agent": "openai-agent", "/api/local-codex": "local-codex", "/api/server-maintenance": "server-maintenance", "/api/settings": "settings",
    "/api/code-review": "code-review", "/api/scheduler-tasks/code-review": "code-review",
    "/api/package-error-analysis": "frontend",
}
def module_for_path(path):
    if path in {"/pages/jenkins.html", "/api/jenkins", "/api/jenkins/register"}:
        return None
    if path.startswith("/pages/"):
        page = path[len("/pages/"):].split(".", 1)[0]
        # 用户中心属于登录后的基础账号功能，不依赖业务模块权限。
        if page == "profile":
            return None
        if page in {"jenkins", "jenkins-koa"}:
            return "manage"
        if page in {"store", "skin-store"}:
            return "store"
        # Codex task detail is part of the local-codex feature.  It is a
        # separate page fragment, but must use the same module permission as
        # the task list; otherwise opening a task is rejected with 403.
        if page == "project-37-maintenance":
            return "server-maintenance"
        if page == "local-codex-task":
            return "local-codex"
        if page in {"package-error-analysis", "package-error-analysis-task"}:
            return "frontend"
        return page
    if path.startswith("/pages/users"):
        return "manage"
    if path.startswith("/api/auth") or path.startswith("/api/users") or path == "/api/modules": return None
    for prefix, module in API_MODULES.items():
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "-"): return module
    return None
