# Houdini AI Agent 中文说明

**[English](README.md)** | **[中文](README_CN.md)**

Houdini AI Agent 是一个面向 Houdini 21 的原生 PySide 面板插件。它的目标很直接：把多会话 AI 对话、工程上下文读取、图片输入、模式化规划、节点操作和错误修复尽量留在 Houdini 内完成。

> 本地 package 说明：仓库里的 `packages/houdini_ai_agent.json` 当前指向 `D:/Project/Houdini/Houdini-AI-Agent`。如果仓库放在其他位置，请修改该 package 文件，或复制一份调整后的 package 到 Houdini packages 目录。

## 当前能力

- Houdini 原生 Python Panel
- 多会话聊天
  - 新建
  - 重命名
  - 搜索 / 过滤
  - 导入
  - 导出
  - 删除
- 每个会话独立自动保存到 `$HIP/Agent`
- 图片粘贴、拖拽上传、缩略图预览、双击大图查看、导入导出
- 回复中的 Houdini 节点路径可点击并自动定位
- 工程上下文面板
  - HIP 路径
  - 当前网络
  - 选中节点
  - 视口摘要
  - 错误 / 警告摘要
- Provider 支持
  - `Codex Local`
  - 自定义 OpenAI-compatible provider
  - `Mock Preview`
- 输入区旁边的 `Ask / Agent / Plan` 工作模式
  - `Ask`：只读问答和检查，不修改场景
  - `Agent`：允许执行当前支持的 Houdini 修改
  - `Plan`：先生成可确认计划，再切换执行
- 第一版模式感知 `ToolRegistry`
  - 集中维护当前工具 schema
  - 同时约束工具栏按钮和模型规划动作
  - 在 Ask / Plan 模式下阻止节点创建、代码写回等修改动作
- 结构化计划卡片
  - 显示目标、步骤、风险和依赖提示
  - 支持确认执行 / 取消计划
  - 确认后自动切换到 Agent 模式按步骤执行
- 模型规划后可执行的 Houdini 动作
  - 场景分析
  - 选中节点检查
  - 视口捕获
  - 节点创建
  - 代码参数修复写回
- 后台请求可取消，Houdini 不会被同步阻塞
- 按钮触发动作会自动跟随当前界面语言
- 记住上次选择的 provider、模型、思考级别和工作模式
- 支持随 Houdini / 系统 DPI 缩放界面，也可用 `HOUDINI_AI_AGENT_UI_SCALE` 覆盖

## 本次修复与补强

- 工作模式与工具策略
  - 新增 `Ask / Agent / Plan` 模式选择器，放在模型和思考级别旁边
  - `Ask` 和 `Plan` 会在代码层阻止会修改 Houdini 场景的工具
  - `Agent` 保留节点创建、代码参数修复等当前支持的执行动作
  - 工具栏按钮会根据模式自动禁用，并给出对应提示
- Plan 工作流
  - Plan 模式下模型先返回结构化计划，而不是直接执行修改
  - 聊天中渲染计划卡片，展示步骤、风险、依赖和确认按钮
  - 确认计划后会切换到 Agent 模式，并按步骤逐个执行
- 执行可靠性
  - 工具执行失败时，插件可触发有限次数的自我修复请求，让模型分析失败原因并返回修正后的动作 JSON
  - 创建节点时会更稳妥地设置 display / render flag，不再因为某类节点不支持对应 flag 就中断整个创建流程
- 界面与交互
  - UI 尺寸和样式会随 DPI 缩放，可通过 `HOUDINI_AI_AGENT_UI_SCALE` 手动覆盖
  - 输入框改为 `Enter` 发送、`Alt+Enter` 换行
  - 会自动恢复上次使用的 provider、模型、思考级别和工作模式
- 思考过程展示修复
  - 不再直接暴露大段原始 JSON
  - 改为可折叠的简洁“思考过程”块
  - 内容更接近 Codex 风格的步骤摘要，而不是内部结构转储
- 视觉链路修复
  - `Codex Local` 只在显式选择为视觉后端时用于读图，不再被 Auto 模式隐式调用
  - 如果当前主 provider 本身就是 `Codex Local`，即使视觉模式是 Auto，也会直接把图片交给 Codex Local
  - `glm-5.1` 等已知纯文本模型会被阻止直接读图，即使旧配置里误勾了视觉能力
  - 如果主模型是文本模型，插件会自动寻找可用的非 Codex 视觉后端 provider
  - 如果某个模型回复看起来像“没收到图片”，插件会自动尝试走视觉兜底重试
- 视觉设置
  - `Vision`
  - `Auto Fallback`
  - 独立的视觉后端模式：Auto、Disabled、指定 Provider、显式 Codex Local、MCP 预留、Skill 预留

## 参考 Houdini-Agent 后我们吸收的方向

参考 [Kazama-Suichiku/Houdini-Agent](https://github.com/Kazama-Suichiku/Houdini-Agent) 之后，我们认为最值得借鉴的不是单纯“工具更多”，而是这些产品思路：

- 只读分析和修改执行边界更清晰
- 视觉能力和模型能力表达更明确
- 聊天内容本身更像工具界面，而不只是文字窗口
- 可点击、可继续操作的交互更强

它的视觉实现是“当前模型优先”的：

- 通过模型特性表标记哪些模型支持图片，`glm-5.1` / `glm-5-turbo` 被标记为非视觉模型
- 只有当前模型支持视觉时，输入层才构造 `text + image_url` 多模态消息
- 旧轮次图片会从上下文中剥离，避免 base64 图片撑爆上下文
- 视口截图也只在当前模型支持视觉时注入给模型

已经吸收并落地的部分：

- 第一版 `Ask / Agent / Plan` 模式区分
- 集中的工具注册表和模式守卫
- 修改前可确认的 Plan 卡片
- 节点路径点击跳转
- 图片拖拽上传
- 更明确的视觉能力与视觉兜底机制
- 更简洁的可折叠思考过程
- 主 provider 优先的图片路由：当前 provider 是 Codex Local 时直接读图；否则 Auto 只找非 Codex 视觉 provider

目前仍落后于该项目的部分：

- Plan 持久化、计划修订控件和执行 DAG
- Todo 任务卡
- 插件管理器 / 规则编辑器 / 记忆管理器
- 更广泛的 HOM 工具覆盖，例如连线、删除、复制、布局、参数批量修改

## 公开视觉 MCP 参考

以下项目目前作为我们后续本地或混合视觉后端的重点参考：

1. [ColeMurray/moondream-mcp](https://github.com/ColeMurray/moondream-mcp)
   - 适合轻量本地视觉能力
2. [mrgoonie/human-mcp](https://github.com/mrgoonie/human-mcp)
   - 适合截图分析、文档读取、界面对比
3. [aliargun/mcp-server-gemini](https://github.com/aliargun/mcp-server-gemini)
   - 适合云端视觉能力接入

当前插件没有强绑定某一个外部 MCP，而是先实现了内部的 Vision Companion 工作流。这样可以先把插件跑稳，后续再无缝切换到本地视觉 MCP。

## 仓库结构

- `packages/houdini_ai_agent.json` - Houdini package 入口
- `houdini/python3.11libs/houdini_ai_agent/` - 插件源码
- `houdini/python_panels/houdini_ai_agent.pypanel` - Python Panel 注册
- `houdini/toolbar/houdini_ai_agent.shelf` - shelf 工具
- `docs/README.en.md` - 英文说明
- `README_CN.md` - 中文说明
- `TODO.md` - 路线图

## 快速开始

1. 确保 Houdini 能读取 `packages/houdini_ai_agent.json`
2. 重启 Houdini
3. 打开 `Windows > New Pane Tab Type > Python Panel > Houdini AI Agent`

## Provider 说明

- `Codex Local`
  - 复用本机 Codex CLI 登录态
  - 不需要手动填写 OpenAI API key
  - 作为当前主 provider 时会直接读图；作为 GLM 等文本模型的 companion 时必须在视觉后端里显式选择
- OpenAI-compatible providers
  - 可以填写环境变量名，也可以直接填写 key
  - 如果 provider 支持视觉，可以直接读取图片
  - `glm-5.1` 这类纯文本模型应只作为主聊天模型；需要读图时请另配一个多模态视觉后端
- 视觉后端
  - Auto 只会选择通过模型能力检查的非 Codex provider
  - 指定 Provider 适合把 `glm-5.1` 主模型和一个多模态读图模型组合使用
  - Codex Local 只有在显式选择时才会被调用

## 文档

- [English Guide](docs/README.en.md)
- [README_CN](README_CN.md)
- [TODO](TODO.md)
