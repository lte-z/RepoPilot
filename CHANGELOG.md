# 更新日志

RepoPilot 的重要变化会记录在这个文件中。

## 未发布 / Unreleased

## v0.1.1 - 2026-06-08

- 将运行时配置、API Key 和报告迁移到统一的 RepoPilot home，并为每个被分析仓库维护独立 profile，避免污染目标仓库。
- 增加 RepoPilot home 查看与安全清理命令，支持 dry-run、二次确认和 marker 校验。
- 补充长期维护所需的贡献流程、分支策略、PR 规范和 release/tag 策略。
- 扩展 GitHub issue 与 pull request 模板，便于后续维护。
- 为 CI 和发布准备流程增加 Python 包构建冒烟检查。
- 统一 CLI 每轮结束状态，在中断、失败或 provider 未返回 usage 时给出明确提示。
- 清理用户可见文档中的非产品化措辞。

## v0.1.0 - 2026-06-04

- RepoPilot 初始公开版本。
- 支持 CLI-first 的多轮仓库侦察会话。
- 支持基于 MCP 的仓库工具、本地配置管理、Provider 设置、token usage 展示和报告保存。
