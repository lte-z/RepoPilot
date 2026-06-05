"""Local FastAPI WebUI for RepoPilot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from .agent import Mode, analyze_repository
from .config import load_config, with_report_dir
from .settings_store import ensure_repo_profile, runtime_paths
from .permissions import PathGuard
from .tools.repository import SaveReportInput, repo_save_report


app = FastAPI(title="RepoPilot")


class AnalyzeRequest(BaseModel):
    repo_path: str
    mode: Mode
    task: str | None = None
    offline: bool = False
    save: bool = False


HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RepoPilot</title>
  <style>
    :root { color-scheme: dark; font-family: "JetBrains Mono", "Microsoft YaHei", monospace; }
    body { margin: 0; background: #111318; color: #e6e8ee; }
    main { max-width: 1180px; margin: 0 auto; padding: 28px; }
    header { display: flex; justify-content: space-between; align-items: baseline; gap: 20px; }
    h1 { margin: 0; font-size: 34px; }
    .muted { color: #9aa3b2; }
    .panel { border: 1px solid #293040; background: #181c24; border-radius: 8px; padding: 18px; margin-top: 18px; }
    .grid { display: grid; grid-template-columns: 1.2fr 180px 1fr auto; gap: 12px; align-items: end; }
    label { display: grid; gap: 6px; font-size: 13px; color: #bac2d3; }
    input, select, button { border-radius: 6px; border: 1px solid #3a4356; background: #0f1218; color: #edf1f8; padding: 10px 12px; font: inherit; }
    button { background: #89b4fa; color: #111318; border: 0; cursor: pointer; font-weight: 700; }
    button:disabled { opacity: .5; cursor: wait; }
    pre { white-space: pre-wrap; word-break: break-word; line-height: 1.55; }
    .timeline { display: grid; gap: 8px; }
    .call { border-left: 3px solid #a6e3a1; padding-left: 10px; color: #cdd6f4; }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>RepoPilot</h1>
        <div class="muted">只读优先的代码仓库入职侦察 Agent</div>
      </div>
      <div class="muted">MCP · CLI · WebUI</div>
    </header>
    <section class="panel">
      <div class="grid">
        <label>仓库路径<input id="repo" value="." placeholder="输入位于 readable_roots 下的仓库路径"></label>
        <label>模式<select id="mode"><option>overview</option><option>runbook</option><option>module-map</option><option>task-brief</option><option>deep-scan</option></select></label>
        <label>任务文本<input id="task" placeholder="task-brief 模式使用"></label>
        <label><span>&nbsp;</span><button id="run">分析</button></label>
      </div>
      <label style="margin-top:12px; display:flex; align-items:center; gap:8px;"><input id="offline" type="checkbox" checked> 离线模式</label>
    </section>
    <section class="panel">
      <h2>工具调用</h2>
      <div id="timeline" class="timeline muted">等待运行。</div>
    </section>
    <section class="panel">
      <h2>报告</h2>
      <pre id="report">等待输出。</pre>
    </section>
  </main>
  <script>
    const run = document.querySelector("#run");
    run.addEventListener("click", async () => {
      run.disabled = true;
      document.querySelector("#timeline").textContent = "运行中...";
      document.querySelector("#report").textContent = "";
      const payload = {
        repo_path: document.querySelector("#repo").value,
        mode: document.querySelector("#mode").value,
        task: document.querySelector("#task").value || null,
        offline: document.querySelector("#offline").checked,
        save: true
      };
      try {
        const res = await fetch("/api/analyze", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "分析失败");
        document.querySelector("#timeline").innerHTML = data.tool_calls.map(c => `<div class="call"><b>${c.name}</b> · ${c.duration_ms} ms<br>${c.preview}</div>`).join("") || "无工具调用。";
        document.querySelector("#report").textContent = data.markdown;
      } catch (err) {
        document.querySelector("#timeline").textContent = String(err);
      } finally {
        run.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML


@app.post("/api/analyze")
async def api_analyze(request: AnalyzeRequest) -> dict[str, Any]:
    try:
        result = await analyze_repository(request.mode, request.repo_path, request.task, offline=request.offline)
        saved = None
        if request.save:
            filename = f"{Path(result.repo_path).name}-{result.mode}.md"
            profile = ensure_repo_profile(result.repo_path)
            config = with_report_dir(load_config(), profile.reports_dir)
            saved = repo_save_report(SaveReportInput(filename=filename, content=result.markdown), config)
        return {
            "mode": result.mode,
            "repo_path": result.repo_path,
            "markdown": result.markdown,
            "offline": result.offline,
            "saved": saved,
            "tool_calls": [call.__dict__ for call in result.tool_calls],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/recent-repos")
async def api_recent_repos() -> dict[str, Any]:
    config = load_config()
    return {"readable_roots": config.permissions.readable_roots}


@app.get("/api/reports/{name}", response_class=PlainTextResponse)
async def api_report(name: str) -> str:
    safe_name = Path(name).name
    repos_dir = runtime_paths().repos_dir
    if repos_dir.exists():
        for reports_dir in sorted(repos_dir.glob("*/reports")):
            path = reports_dir / safe_name
            if path.is_file():
                return path.read_text(encoding="utf-8")

    config = load_config()
    guard = PathGuard(config, config.project_root, validate_session=False)
    path = guard.resolve_write_path(safe_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="报告不存在")
    return path.read_text(encoding="utf-8")
