#!/usr/bin/env python3
"""验证工作台页面登记和静态资源可访问性。"""
from __future__ import annotations
import os, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
web = root / "workbench" / "machine-dashboard-server" / "web"
import socket
with socket.socket() as reservation:
    reservation.bind(("127.0.0.1", 0))
    port = str(reservation.getsockname()[1])
env = {**os.environ, "LOCALAPPDATA": tempfile.mkdtemp(prefix="selfagent-web-"), "MACHINE_DASHBOARD_PORT": port, "PYTHONPATH": str(root / "workbench" / "machine-dashboard-server" / "src")}
proc = subprocess.Popen([sys.executable, str(root / "workbench" / "machine-dashboard-server" / "src" / "server.py")], cwd=root / "workbench" / "machine-dashboard-server", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def get(path: str) -> bytes:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as response:
        assert response.status == 200, (path, response.status)
        return response.read()
try:
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            get("/api/health"); break
        except Exception:
            time.sleep(.2)
    else: raise RuntimeError("workbench did not become healthy")
    pages = sorted(p.stem for p in (web / "pages").glob("*.html"))
    for page in pages:
        get(f"/pages/{page}.html")
    assets = ["/assets/js/app.js", "/assets/js/shared/page-scope.js"] + [
        "/assets/js/pages/" + p.name for p in sorted((web / "assets" / "js" / "pages").glob("*.js"))
    ]
    for asset in assets:
        get(asset)
    page_scripts = sorted((web / "assets" / "js" / "pages").glob("*.js"))
    for script in page_scripts:
        source = script.read_text(encoding="utf-8")
        if "createPageScope" in source:
            assert "export function unmount" in source and "scope?.dispose()" in source, script
        if "addEventListener(" in source and "selectionchange" in source:
            assert "removeEventListener" in source, script
        if "setInterval(" in source:
            assert "scope.setInterval" in source or "const setInterval = (...args) => scope.setInterval" in source, script
        # Mutating page actions must expose a duplicate-submit guard.
        if 'method: "POST"' in source and "disabled" in source:
            assert "finally" in source or ".disabled = false" in source, script
    settings_source = (web / "assets/js/pages/settings.js").read_text(encoding="utf-8")
    assert "choose.disabled = true" in settings_source
    assert "localApi(\"/api/settings/storage\"" in settings_source
    assert "finally" in settings_source and "choose.disabled = false" in settings_source
    task_html = (web / "pages/local-codex-task.html").read_text(encoding="utf-8")
    task_source = (web / "assets/js/pages/local-codex-task.js").read_text(encoding="utf-8")
    assert 'id="codex-task-cancel"' in task_html
    assert '/api/local-codex/task/cancel' in task_source
    assert 'cancel.hidden = item.status !== "running"' in task_source
    scope_source = (web / "assets/js/shared/page-scope.js").read_text(encoding="utf-8")
    assert "controller.abort()" in scope_source and "clearInterval" in scope_source
    assert proc.poll() is None, "workbench exited during web validation"
    print(f"web resource validation passed: pages={len(pages)} assets={len(assets)}")
finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
