# 设置读取和保存示例

以下 feature_module 为占位业务模块，实施时替换为真实模块和持久化函数。

## HTML 片段

```html
<input id="feature-name" />
<button type="button" id="feature-save">保存</button>
<span id="feature-message" role="status"></span>
```

## 页面 JS

```javascript
import { createPageScope } from "../shared/page-scope.js";
let scope;
export async function mount() {
  scope = createPageScope();
  const name = document.getElementById("feature-name");
  const button = document.getElementById("feature-save");
  const message = document.getElementById("feature-message");
  async function request(url, options) {
    const response = await scope.fetch(url, options);
    const data = await response.json();
    if (!response.ok || !data.ok) throw Error(data.error || "请求失败");
    return data.config;
  }
  function render(config) { name.value = config.name; }
  button.onclick = async () => {
    button.disabled = true;
    message.textContent = "正在保存…";
    try {
      render(await request("/api/feature/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.value.trim() }),
      }));
      message.textContent = "已保存";
    } catch (error) { message.textContent = error.message; }
    finally { button.disabled = false; }
  };
  button.disabled = true;
  try { render(await request("/api/feature/config")); }
  catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; }
}
export function unmount() { scope?.dispose(); }
```

## view.py

```python
from . import router

@router.route("GET", "/api/feature/config")
@router.route("POST", "/api/feature/config")
def handle(ctx):
    from feature_module import read_config, save_config
    if ctx.method == "GET":
        config = read_config()
    else:
        name = ctx.body.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("名称不能为空")
        config = save_config(name=name.strip())
    ctx.request.send_json(200, {"ok": True, "config": config})
    return True
```

save_config 应持久化并返回实际配置。将此 view 导入 src/view/routes.py；新页面还需登记 app.js 的页面标题和模块。

## 当前工程对照

可查看工作台的 web/pages/code-review.html、web/assets/js/pages/code-review.js、src/view/code_review_view.py、src/schedulers/code_review_scheduler.py。接口由 src/server.py 构造 ViewContext 后经 src/view/router.py 分发；业务工具实际入口位于 workbench/machine-dashboard-server/tools/code-review-agent。对照其分层，不照搬具体业务参数或现有缺陷。
