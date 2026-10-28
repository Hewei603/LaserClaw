# Codex exec 订阅接入

LaserClaw 2.0 在首页 Agent 配置提供两种接入方式：

- **API Key**：沿用原有 OpenAI、Anthropic 和其他兼容服务商配置。
- **Codex exec（ChatGPT 订阅）**：调用后端电脑安装的官方 Codex CLI，复用 CLI 的 ChatGPT 登录，不需要向 LaserClaw 提供模型 API Key。

## 开始使用

1. 在运行 LaserClaw 后端的电脑安装官方 Codex CLI。Windows 可以使用 npm 安装：npm install -g @openai/codex。也可指定已安装的 codex.exe。
2. 在同一操作系统用户的终端执行 codex login，选择 ChatGPT 登录。用 codex login status 确认显示 ChatGPT。
3. 打开 LaserClaw 首页，在 Agent 配置中把接入方式改为 Codex exec（ChatGPT 订阅）。
4. 模型默认是 gpt-6.1-sol；点击“刷新登录状态”，再点击“测试连接”。连接测试会调用真实模型，使用少量订阅额度，并验证该模型确实可用。
5. 点击“保存并应用”。后续 Agent、实验计划、图片分析、需求提取、报告和对话摘要使用 Codex exec，无需重启。升级代码后的旧后端进程仍需重启一次。

高级设置可以填写 Codex 可执行文件路径、每轮等待上限（30–1800 秒，默认300秒）和推理强度。自动发现优先选择 Windows 原生 codex.exe；官方 npm 包装脚本通过 Node.js 启动，不拼接 shell 命令。不同模型支持的推理强度以实际调用为准。

## 订阅与配置

Codex exec 使用当前登录账户的 Codex 订阅额度，仍受套餐限额约束。LaserClaw 记录 CLI 返回的 token 使用量，但不套用 API 单价，也不显示“免费无限使用”。选择这个方式时，子进程不继承 OPENAI_API_KEY 或 CODEX_API_KEY，并要求 ChatGPT 登录；CLI 使用 API Key 登录时会显示明确提示。

LaserClaw 不读取或保存 CLI 的 OAuth token，也不修改用户的全局 Codex 配置。登录、续期和账户切换交给 Codex CLI。后端在 Docker、远程服务器或其他系统用户下运行时，需要在那个运行环境安装 CLI 并完成登录；浏览器所在电脑的登录不会自动传到服务器。

首页保存的配置位于原有 AGENT_SETTINGS_FILE（默认上传目录中的 .agent-settings.json）。切换接入方式会保留各 API 服务商已保存的密钥、模型和接口地址。

可通过环境变量配置：

    AI_PROVIDER=codex_exec
    CODEX_EXEC_MODEL=gpt-6.1-sol
    CODEX_EXEC_PATH=
    CODEX_EXEC_TIMEOUT_SECONDS=300
    CODEX_EXEC_REASONING_EFFORT=medium

## Agent 与物理工具如何衔接

每轮 codex exec 在独立临时目录接收任务、历史上下文、真实工具结果和必要图片，通过 --output-schema 返回结构化动作。LaserClaw 校验工具名与参数，执行原有元件库、知识检索、ABCD 数值仿真、扫描和工程保存工具，再把实际结果交给下一轮。最终结论引用数据库记录的真实工具调用ID。

Codex 的临时调用使用只读沙箱，关闭本适配器不需要的 shell、补丁与多 Agent 功能，不加载用户 config.toml 或项目 AGENTS.md。文件修改和实验数据保存仍走 LaserClaw 原有业务工具。CLI 退出成功、收到 turn.completed 且取得有效结构化结果后，才接收该轮输出。临时图片和输出随调用结束清理。

CLI 缺失、登录失效、限流、模型不可用和超时均显示错误；不会悄悄降级到 Mock，也不会自动改走 API 计费。工作台已完成的工具结果仍可用于继续任务。

## 验证

自动测试覆盖配置持久化、API profile保留、图片传入、实际工具执行、结构化响应、超时及取消、登录与额度错误、未知工具拒绝以及订阅用量计费标记。

真实登录验收在临时数据库运行，不修改已有实验案例：

    cd backend
    .venv\Scripts\python.exe scripts\validate_codex_exec_live.py

它会使用当前账户的订阅额度，验证连接、图片输入、Agent调用实际物理内核、保存证据与报告生成，证据输出到 output/validation/codex-exec-live.json。

官方参考：[Codex非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)、[Codex登录方式](https://learn.chatgpt.com/docs/auth)。
