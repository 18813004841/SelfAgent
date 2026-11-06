from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .checks import run_compile, unity_runtime_findings
from .config import ReviewConfig
from .git import GitRepository
from .model_service import LocalModelClient, ModelServiceError
from .models import CheckResult, Finding
from .rules import load_matching

logger = logging.getLogger("code-review.pipeline")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    log_dir = Path(__file__).resolve().parent / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [feature=code-review] %(levelname)s %(message)s"))
    logger.addHandler(handler)
    file_handler = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [feature=code-review] %(levelname)s %(message)s"))
    logger.addHandler(file_handler)
    logger.propagate = False


class ReviewPipeline:
    def __init__(self, config: ReviewConfig, progress: Callable[..., None] | None = None, log: Callable[..., None] | None = None, cancel: Callable[[], bool] | None = None) -> None:
        self.config = config
        self.root = Path(config.project["path"]).resolve()
        self.repo = GitRepository(self.root, config.project.get("remote", "origin"))
        self.progress_callback = progress or (lambda **_: None)
        self.log_callback = log or (lambda **_: None)
        self.cancel_callback = cancel or (lambda: False)
        self.step_total = 10
        self.step = 0

    def _ensure_running(self) -> None:
        if self.cancel_callback():
            raise RuntimeError("代码检查已终止")

    def _step(self, message: str, **details: Any) -> None:
        self._ensure_running()
        self.step += 1
        logger.info("step.begin name=%s details=%s", message, details)
        self.progress_callback(current=self.step, total=self.step_total, message=message, **details)
        self.log_callback(kind="pipeline", message=message, **details)

    def _done(self, message: str, **details: Any) -> None:
        details.setdefault("result", "成功")
        logger.info("step.end name=%s details=%s", message, details)
        self.progress_callback(current=self.step, total=self.step_total, message=f"{message}执行完毕", **details)
        self.log_callback(kind="pipeline", message=f"{message}执行完毕", **details)

    def load_previous_sha(self, state_path: Path) -> str | None:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
        return state.get("last_successful_sha")

    def collect_diff(self, old: str, current: str) -> tuple[list[str], str]:
        files = self.repo.changed_files(old, current)
        diff = self.repo.diff(old, current) or ""
        if files and not diff.strip():
            raise RuntimeError("Git 检测到变更文件，但未读取到具体 Diff，已停止模型检查")
        return files, diff

    def validate_changed_files(self, files: list[str]) -> list[str]:
        errors = []
        for rel in files:
            path = self.root / rel
            if path.is_file():
                try: path.read_text(encoding="utf-8", errors="strict")
                except UnicodeError as exc: errors.append(f"{rel}: 编码错误 {exc}")
        return errors

    def split_diff(self, diff: str, files: list[str], chunk_size: int = 12000) -> list[dict[str, Any]]:
        chunks = []
        for file_part in re.split(r"(?=^diff --git )", diff, flags=re.MULTILINE):
            if not file_part.strip():
                continue
            match = re.search(r"^diff --git a/(.+?) b/(.+)$", file_part, re.MULTILINE)
            file_name = match.group(2) if match else ""
            chunk_files = [file_name] if file_name else files
            chunks.extend({"files": chunk_files, "diff": file_part[i:i + chunk_size]} for i in range(0, len(file_part), chunk_size))
        return chunks or [{"files": files, "diff": diff}]

    @staticmethod
    def parse_model_json(content: str) -> dict[str, Any]:
        text = content.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise json.JSONDecodeError("model response is not an object", text, 0)
        return parsed

    @staticmethod
    def format_review_prompt(chunk: dict[str, Any], rules: list[dict[str, Any]], file_context: str = "") -> str:
        # Use a fence longer than any fence in the source so code stays intact.
        def fenced(text: str, language: str = "") -> str:
            fence = "`" * max(3, max((len(m.group()) + 1 for m in re.finditer(r"`+", text)), default=3))
            return f"{fence}{language}\n{text}\n{fence}"

        sections = ["# 代码变更检查", "请依据以下 Skill 审查变更，返回 JSON：findings、open_questions、test_gaps。先看 Diff，再依据完整文件判断生命周期、性能、架构和项目规范。",
                    "## 变更文件", "\n".join(f"- {path}" for path in chunk["files"]),
                    "## 代码差异", "保留 Git diff 行号区间；+ 为新增，- 为删除，空格为上下文。", fenced(chunk["diff"], "diff"),
                    "## 完整变更文件", file_context or "无 C# 变更文件", "## 检查 Skill"]
        for rule in rules:
            sections.extend([f"### {rule.get('path', 'Skill')}", fenced(rule.get("content", ""), "markdown")])
        return "\n\n".join(sections)

    def build_file_context(self, files: list[str], limit: int = 80000) -> tuple[str, int]:
        sections=[]; count=0
        for rel in files:
            if not rel.lower().endswith(".cs"): continue
            path=self.root/rel
            if not path.is_file(): continue
            text=path.read_text(encoding="utf-8", errors="replace")
            if len(text)>limit: text=text[:limit]+"\n# ... 文件过大，已截断"
            sections.append(f"### {rel}\n```csharp\n{text}\n```"); count+=1
        return "\n\n".join(sections), count
    def run(self) -> CheckResult:
        # Reset the existing stream at task start, including repeated runs in one process.
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename).name == "pipeline.log":
                handler.acquire()
                try:
                    handler.flush()
                    if handler.stream is not None:
                        handler.stream.seek(0)
                        handler.stream.truncate()
                finally:
                    handler.release()
        self.step = 0
        started = time.perf_counter()
        logger.info("review.begin project=%s branch=%s", self.config.project.get("name"), self.config.project.get("branch"))
        executed_at = datetime.now().isoformat(timespec="seconds")
        branch = str(self.config.project.get("branch", "unknown"))
        safe_project = re.sub(r"[^A-Za-z0-9._-]+", "-", self.root.name) or "project"
        safe_branch = re.sub(r"[^A-Za-z0-9._-]+", "-", branch) or "branch"
        storage_root = Path(__file__).resolve().parents[1] / "data" / f"{safe_project}-{safe_branch}"
        storage_root.mkdir(parents=True, exist_ok=True)
        state_path = storage_root / "state.json"
        sequence_path = storage_root / "execution-sequence.json"
        try:
            sequence = json.loads(sequence_path.read_text(encoding="utf-8")) if sequence_path.is_file() else {}
        except (OSError, json.JSONDecodeError):
            sequence = {}
        sequence_number = int(sequence.get("next", 1))
        execution_id = f"{safe_project}-{safe_branch}-{sequence_number:04d}"
        sequence_path.parent.mkdir(parents=True, exist_ok=True)
        sequence_path.write_text(json.dumps({"next": sequence_number + 1}, indent=2), encoding="utf-8")
        self._step("同步 Git 分支")
        current, operations = self.repo.sync_with_trace(self.config.project["branch"])
        self._done("同步 Git 分支", operations=operations, current_sha=current)
        old = self.load_previous_sha(state_path)
        if not old:
            # 首次执行从“昨天的定时执行时间”开始，避免把更早历史重复送检。
            try:
                hour, minute = (int(x) for x in str(self.config.raw.get("schedule", {}).get("time", "04:00")).split(":", 1))
            except (TypeError, ValueError):
                hour, minute = 4, 0
            yesterday = datetime.now() - timedelta(days=1)
            yesterday = yesterday.replace(hour=hour, minute=minute, second=0, microsecond=0)
            old = self.repo.initial_sha(before=yesterday)
        old_info = self.repo.commit_summary(old) if old else {"sha": None}
        self._step("读取上次检查 SHA", **old_info)
        self._done("读取上次检查 SHA", **old_info)
        if old == current:
            logger.info("review.skipped sha=%s reason=no-new-commit", current)
            return CheckResult("skipped", old, current, execution_id=execution_id, executed_at=executed_at)
        self._step("读取 Diff 内容")
        files, diff = self.collect_diff(old, current)
        diff_path = storage_root / "reports" / execution_id / "changes.diff"
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text(diff, encoding="utf-8")
        self._done("读取 Diff 内容", files=len(files), diff_chars=len(diff), diff_path=str(diff_path))
        self._step("检查变更文件", files=len(files))
        validation_errors = self.validate_changed_files(files)
        self._done("检查变更文件", errors=validation_errors, files=len(files))
        result = CheckResult("failed", old, current, files, execution_id=execution_id, executed_at=executed_at)
        result.warnings.extend(validation_errors)
        self._step("检查 Runtime 代码中的 Editor 引用")
        result.findings.extend(Finding(**x) for x in unity_runtime_findings(self.root, files, self.config.checks.get("editor_markers", ["UnityEditor", "/Editor/", "\\Editor\\"])))
        self._done("检查 Runtime 代码中的 Editor 引用", findings=len(result.findings))
        self._step("读取代码检查 Skill")
        skill_paths=self.config.checks.get("skill_paths") or []; rules = load_matching(self.root, files, skill_paths); missing=[item for item in skill_paths if not Path(item).expanduser().exists()]
        self._done("读取代码检查 Skill", skills=len(rules), paths=[rule["path"] for rule in rules], missing=missing)
        if not rules and skill_paths:
            result.warnings.append("已配置 Skill 路径，但没有读取到 SKILL.md")
            result.agent_status = "unavailable"; result.status = "error"
        self._step("执行编译检查")
        compile_result = run_compile(self.root, self.config.checks.get("compile_command"))
        if compile_result: result.tool_results.append(compile_result)
        self._done("执行编译检查", result=compile_result or "未配置编译命令")
        self._step("切分代码内容")
        chunks = self.split_diff(diff, files); context_files = len({file for chunk in chunks for file in chunk["files"] if str(file).lower().endswith(".cs")})
        self._done("切分代码内容", chunks=len(chunks), context_files=context_files)
        self._step("发送代码切片和 Skill 给模型", chunks=len(chunks))
        try:
            client = LocalModelClient(self.config.model_service.get("api_url", "http://127.0.0.1:8765/v1"), self.config.model_service.get("model", "gpt-5.6-sol"), self.config.model_service.get("timeout_seconds", 120), self.config.model_service.get("max_output_tokens", 2000))
            findings = []
            if not rules:
                chunks = []
            for index, chunk in enumerate(chunks, 1):
                file_context, _ = self.build_file_context(chunk["files"]); prompt = self.format_review_prompt(chunk, rules, file_context)
                prompt_path = diff_path.parent / f"model-input-{index:03d}.md"
                prompt_path.write_text(prompt, encoding="utf-8")
                self.progress_callback(current=self.step, total=self.step_total, message="发送模型检查代码切片", chunk=index, chunks=len(chunks), diff_chars=len(chunk["diff"]), prompt_path=str(prompt_path))
                messages = [{"role": "system", "content": "你是 Unity C# 代码审查器，严格按照 Skill 检查完整变更文件。只输出 JSON，包含 findings、open_questions、test_gaps。"}, {"role": "user", "content": prompt}]
                parsed = None
                last_error = None
                for attempt in range(1, 7):
                    self._ensure_running()
                    try:
                        content = client.complete(messages)
                        parsed = self.parse_model_json(content)
                        items = parsed.get("findings") or []
                        if any(isinstance(item, dict) and not str(item.get("message") or "").strip() for item in items):
                            raise ValueError("模型返回的问题 message 为空")
                        if attempt > 1:
                            self.log_callback(kind="pipeline", message="模型切片重试成功", chunk=index, attempt=attempt)
                        break
                    except (ModelServiceError, json.JSONDecodeError, OSError, ValueError) as exc:
                        last_error = exc
                        logger.warning("model.chunk_failed chunk=%s attempt=%s/6 error=%s", index, attempt, exc)
                        self.log_callback(kind="pipeline", message="模型切片请求失败", chunk=index, attempt=attempt, max_attempts=6, error=str(exc))
                        if attempt < 6:
                            self.progress_callback(current=self.step, total=self.step_total, message="模型请求重试", chunk=index, attempt=attempt + 1, max_attempts=6)
                if parsed is None:
                    raise ModelServiceError(f"切片 {index} 重试 5 次后仍失败: {last_error}")
                findings.extend(parsed.get("findings", [])); result.tool_results.append({"name":"model-review","chunk":index,"open_questions":parsed.get("open_questions",[]),"test_gaps":parsed.get("test_gaps",[])})
            self._done("发送代码切片和 Skill 给模型", chunks=len(chunks), findings=len(findings))
            if rules:
                result.agent_status = "passed"
            for item in findings: result.findings.append(Finding("agent", item.get("severity", "medium"), item.get("message", ""), item.get("file"), item.get("line"), item.get("rule"), item.get("suggestion"), item.get("confidence")))
        except (ModelServiceError, json.JSONDecodeError, OSError) as exc:
            result.agent_status = "unavailable"
            result.warnings.append(f"模型服务不可用或返回格式无效: {exc}")
            result.status = "error"
        if compile_result and compile_result["status"] == "failed": result.status = "failed"
        if result.agent_status == "passed" and result.status != "error":
            result.status = "failed" if any(f.severity in {"critical", "high"} for f in result.findings) else "passed"
        self._step("汇总并保存检查结果")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        if result.status == "passed": state_path.write_text(json.dumps({"last_successful_sha": current, "checked_at": datetime.now().isoformat()}, indent=2), encoding="utf-8")
        report_dir = storage_root / "reports"; report_dir.mkdir(parents=True, exist_ok=True)
        report = report_dir / f"{current}.json"; report.write_text(json.dumps(result.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"); result.report_path = str(report)
        current_info = self.repo.commit_summary(current)
        elapsed = round(time.perf_counter() - started, 3)
        logger.info("review.summary sha=%s author=%s subject=%s status=%s findings=%d elapsed_seconds=%s", current_info.get("sha"), current_info.get("author"), current_info.get("subject"), result.status, len(result.findings), elapsed)
        self.log_callback(kind="result", message="检查结果", sha=current_info.get("sha"), author=current_info.get("author"), subject=current_info.get("subject"), status=result.status, findings=len(result.findings), elapsed_seconds=elapsed)
        for index, finding in enumerate(result.findings, 1):
            if finding.source == "agent":
                cause = "Skill规范"
                rule = finding.rule or "模型未标注具体条款"
            else:
                cause = "流程固定规则"
                rule = finding.rule or finding.source
            logger.info("review.issue index=%s file=%s line=%s severity=%s cause=%s rule=%s message=%s", index, finding.file, finding.line, finding.severity, cause, rule, finding.message)
            self.log_callback(kind="result", message="检查问题", index=index, sha=current_info.get("sha"), author=current_info.get("author"), file=finding.file, line=finding.line, severity=finding.severity, cause=cause, rule=rule, detail=finding.message, suggestion=finding.suggestion)
        logger.info("review.end status=%s current_sha=%s findings=%d agent_status=%s", result.status, current, len(result.findings), result.agent_status)
        return result
