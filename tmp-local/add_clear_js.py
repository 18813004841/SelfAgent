from pathlib import Path
js = Path('workbench/machine-dashboard-server/web/assets/js/pages/code-review.js')
source = js.read_text(encoding='utf-8')
anchor = 'const runButton = document.getElementById("review-run");'
block = '''const clearButton = document.getElementById("review-clear-history");
  if (clearButton)
    clearButton.onclick = async () => {
      const projectPath = document.getElementById("review-project-path").value.trim();
      const branch = document.getElementById("review-branch").value.trim();
      if (!confirm("确定清空该工程和分支的历史检查结果？")) return;
      msg.hidden = false;
      msg.textContent = "正在清空历史...";
      clearButton.disabled = true;
      try {
        const response = await fetch("/api/scheduler-tasks/code-review/clear-history", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_path: projectPath, branch, schedule_id: taskId }),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw Error(data.error || "清空失败");
        msg.textContent = "历史检查结果已清空";
        if (data.task) render(data.task);
      } catch (error) {
        msg.textContent = "清空失败：" + error.message;
      } finally {
        clearButton.disabled = false;
      }
    };
  '''
if 'review-clear-history' not in source:
    if anchor not in source:
        raise SystemExit('js anchor missing')
    js.write_text(source.replace(anchor, block + anchor, 1), encoding='utf-8', newline='\n')
print('js ok')
