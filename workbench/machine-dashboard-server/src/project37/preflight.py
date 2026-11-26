"""Read-only checks for the server-hosted 37 maintenance workflow."""
from pathlib import Path
import os
import subprocess

FIELDS = ("project_path", "data_path", "source_branch", "new_branch", "tag", "data_branch")


def git(repo, *args, timeout=30, check=True):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Git 不可用或检查远端超时") from exc
    if check and result.returncode:
        raise ValueError("Git 检查失败，请检查仓库及 origin 访问权限")
    return result


def root(path, label):
    candidate = Path(path).expanduser()
    if not candidate.is_dir():
        raise ValueError(f"{label}目录不存在")
    result = git(candidate, "rev-parse", "--show-toplevel")
    return Path(result.stdout.strip()).resolve()


def check(payload):
    if not isinstance(payload, dict):
        raise ValueError("请求格式错误")
    values = {}
    for key in FIELDS:
        item = payload.get(key)
        if not isinstance(item, str) or not item.strip() or "\0" in item:
            raise ValueError(f"缺少有效参数：{key}")
        values[key] = item.strip()
    project = root(values["project_path"], "37工程")
    data = root(values["data_path"], "37data工程")
    if project == data or project in data.parents or data in project.parents:
        raise ValueError("两个仓库不能相同或互相包含")
    fbs = data / "fbs"
    if not fbs.is_dir() or not any(fbs.glob("*.fbs")):
        raise ValueError("37data 仓库的 fbs 目录不存在或没有 .fbs 文件")
    for key in ("source_branch", "new_branch", "data_branch"):
        if git(project, "check-ref-format", "--branch", values[key], check=False).returncode:
            raise ValueError(f"分支名称无效：{key}")
    if git(project, "check-ref-format", "refs/tags/" + values["tag"], check=False).returncode:
        raise ValueError("tag 名称无效")
    def remote_ref(repo, ref):
        result = git(repo, "ls-remote", "--exit-code", "origin", ref, timeout=45, check=False)
        if result.returncode not in (0, 2):
            raise ValueError("无法读取远端引用，请检查 origin 和访问权限")
        return any(line.split("\t")[-1] == ref for line in result.stdout.splitlines())
    for repo, ref, label in ((project, "refs/heads/" + values["source_branch"], "37工程原分支"),
                             (data, "refs/heads/" + values["data_branch"], "37data分支"),
                             (project, "refs/tags/" + values["tag"], "新版本内容tag")):
        if not remote_ref(repo, ref):
            raise ValueError(label + "在 origin 不存在")
    newref = "refs/heads/" + values["new_branch"]
    if not git(project, "show-ref", "--verify", "--quiet", newref, check=False).returncode or remote_ref(project, newref):
        raise ValueError("37工程新分支已存在")
    return {"project_root": str(project), "data_root": str(data), "fbs_path": str(fbs)}
