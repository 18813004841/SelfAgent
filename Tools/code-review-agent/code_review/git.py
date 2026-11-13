from __future__ import annotations

import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class GitError(RuntimeError): pass


class GitRepository:
    def __init__(self, root: Path, remote: str = "origin") -> None:
        self.root, self.remote = root.resolve(), remote

    def run(self, *args: str) -> str:
        command = ["git", *args]
        logger = logging.getLogger("code-review.pipeline")
        logger.info("git.command args=%s", command)
        try:
            completed = subprocess.run(command, cwd=self.root, encoding="utf-8", errors="replace", capture_output=True, timeout=60)
        except subprocess.TimeoutExpired as exc:
            detail = ""
            for value in (exc.stderr, exc.stdout):
                if not value:
                    continue
                detail = value if isinstance(value, str) else value.decode("utf-8", "replace")
                detail = detail.strip()
                if detail:
                    break
            message = "git " + " ".join(args) + " 超时（60秒）"
            if detail:
                message += "：" + detail
            logger.error("git.timeout command=%s detail=%s", command, detail)
            raise GitError(message) from exc
        stderr = completed.stderr or ""
        stdout = completed.stdout or ""
        if completed.returncode:
            detail = stderr.strip() or stdout.strip() or "git command failed"
            logger.error("git.failed command=%s returncode=%s detail=%s", command, completed.returncode, detail)
            raise GitError("git " + " ".join(args) + " 失败（退出码 %s）：%s" % (completed.returncode, detail))
        logger.info("git.completed command=%s output_length=%s", command, len(stdout))
        return stdout.strip()

    def sync(self, branch: str) -> str:
        self.run("checkout", branch)
        # A local-only clone is valid for the review service. Fetch/pull only
        # when the configured remote exists; otherwise inspect the current
        # local branch without pretending network access is required.
        remotes = self.run("remote").splitlines()
        if self.remote in remotes:
            self.run("fetch", self.remote, branch)
            self.run("pull", "--ff-only", self.remote, branch)
        return self.run("rev-parse", "HEAD")

    def sync_with_trace(self, branch: str) -> tuple[str, list[str]]:
        operations: list[str] = []

        def execute(*args: str) -> str:
            operations.append("git " + " ".join(args))
            try:
                return self.run(*args)
            except GitError as exc:
                reason = str(exc) + chr(10) + "已执行操作：" + "; ".join(operations)
                raise GitError(reason) from exc

        execute("checkout", branch)
        remotes = self.run("remote").splitlines()
        if self.remote in remotes:
            execute("fetch", self.remote, branch)
            execute("pull", "--ff-only", self.remote, branch)
        return execute("rev-parse", "HEAD"), operations

    def commit_summary(self, sha: str) -> dict[str, str]:
        return {"sha": sha, "subject": self.run("show", "-s", "--format=%s", sha), "author": self.run("show", "-s", "--format=%an", sha), "date": self.run("show", "-s", "--format=%aI", sha)}

    def blame_line(self, sha: str, file_path: str, line: int) -> dict[str, str] | None:
        """Return the commit and author that last changed a source line."""
        if not file_path or not isinstance(line, int) or line < 1:
            return None
        try:
            relative = Path(file_path)
            if relative.is_absolute():
                relative = relative.resolve().relative_to(self.root)
            output = self.run("blame", "--porcelain", f"-L{line},{line}", sha, "--", relative.as_posix())
        except (GitError, ValueError, OSError):
            return None
        header = output.splitlines()[0].split() if output else []
        if not header:
            return None
        author = next((item[7:] for item in output.splitlines()[1:] if item.startswith("author ")), None)
        return {"sha": header[0], "author": author or "未知"}

    def current_sha(self) -> str: return self.run("rev-parse", "HEAD")

    def initial_sha(self, before: datetime | None = None, days: int = 7, hour: int = 4) -> str:
        target = before or (datetime.now() - timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
        return self.run("rev-list", "-1", f"--before={target.isoformat()}", "HEAD") or self.run("rev-list", "--max-parents=0", "HEAD")

    def changed_files(self, old_sha: str, current_sha: str) -> list[str]:
        out = self.run("-c", "core.quotepath=false", "diff", "--name-only", old_sha, current_sha, "--")
        return [x for x in out.splitlines() if x]

    def diff(self, old_sha: str, current_sha: str, context: int = 20) -> str:
        return self.run("-c", "core.quotepath=false", "diff", "--no-ext-diff", "--no-textconv", "--no-color", f"--unified={context}", old_sha, current_sha, "--")
