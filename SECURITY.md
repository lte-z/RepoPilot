# 安全说明

RepoPilot 是只读优先的本地 Agent。它会读取用户授权的仓库内容，并把运行时配置、API Key 和报告保存在本地 `.repopilot/` 目录中。

## 敏感数据

请不要提交或公开：

- `.repopilot/`
- `.env` 文件或 API Key
- 包含私有仓库内容的报告
- 本机绝对路径、内部服务地址或其他隐私信息

`.gitignore` 已默认忽略 `.repopilot/`、虚拟环境、缓存和常见本地配置文件，但提交前仍应主动检查。

## 权限边界

RepoPilot 使用“父目录白名单 + session repo”模型。工具只能读取当前会话仓库内部内容，并会遵循 `deny_patterns`、`.gitignore`、`.git/info/exclude` 和 Git 标准忽略规则。

默认写入能力仅用于保存 Markdown 报告。第一版不提供命令执行工具，`allow_command_execution` 和 `allowed_commands` 只是后续扩展预留的配置门。

## WebUI

`repopilot web` 是预览版本地 WebUI，默认监听 `127.0.0.1`。不建议将它暴露到公网或共享网络。如需临时访问 WebUI，请只在可信本机环境中运行。

## 报告问题

如果发现安全问题，请在 GitHub issue 中描述最小可复现信息。不要在公开 issue 中粘贴 API Key、私有仓库代码、`.env` 内容或敏感路径。
