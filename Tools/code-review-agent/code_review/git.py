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
        logging.getLogger("code-review.pipeline").info("git.command args=%s", ["git", *args])
        p = subprocess.run(["git", *args], cwd=self.root, encoding="utf-8", errors="replace", capture_output=True, timeout=60)
        stderr = p.stderr or ""
        stdout = p.stdout or ""
        if p.returncode:
            logging.getLogger("code-review.pipeline").error("git.failed returncode=%s stderr=%s", p.returncode, stderr.strip())
            raise GitError(stderr.strip() or stdout.strip() or "git command failed")
        logging.getLogger("code-review.pipeline").info("git.completed output_length=%s", len(stdout))
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
        operations = [f"git checkout {branch}"]
        self.run("checkout", branch)
        remotes = self.run("remote").splitlines()
        if self.remote in remotes:
            operations.extend([f"git fetch {self.remote} {branch}", f"git pull --ff-only {self.remote} {branch}"])
            self.run("fetch", self.remote, branch)
            self.run("pull", "--ff-only", self.remote, branch)
        operations.append("git rev-parse HEAD")
        return self.run("rev-parse", "HEAD"), operations

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
