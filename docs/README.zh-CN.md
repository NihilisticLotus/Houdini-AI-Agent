# Houdini AI Agent - 中文使用说明

## 项目简介

Houdini AI Agent 是一个基于 PySide、运行在 Houdini 21.0 内的面板插件。目标是把 AI 辅助工作流放回 Houdini 内部，让工程分析、节点操作、图片输入、后续的错误修复都尽量在同一个工作区内完成。

## 当前已实现功能

- Houdini 原生 Python Panel 界面
- 多会话能力：
  - 新建
  - 重命名
  - 搜索/过滤
  - 导入
  - 导出
  - 删除
- 会话按单独文件保存到 `$HIP/Agent/sessions`
- 会话中的图片保存到 `$HIP/Agent/images/<conversation_id>/`
- 支持剪贴板图片粘贴（`Ctrl+V`）
- 支持待发送图片和聊天记录图片双击预览
- 支持删除单条消息，以及带确认的清空全部消息
- 支持收起/展开会话栏与工程上下文栏
- 支持专注模式，减少干扰
- 可读取基础 Houdini 上下文：
  - HIP 路径
  - 当前网络
  - 选中节点
  - 视口摘要
  - 错误/警告摘要
- 初步支持 OpenAI-compatible provider：
  - 实时文本对话
  - 带图片的多模态提问
  - 部分分析类工具栏动作
- 支持本机 `Codex Local` provider：
  - 复用这台机器上已安装并已登录的 Codex CLI
  - 不需要你在插件里手工填写 OpenAI API key

## 安装方式

### 方式一：直接使用仓库内 package

仓库已包含：

- `packages/houdini_ai_agent.json`

可让 Houdini 直接读取该 package 文件，或者把它复制到 Houdini 的 packages 目录后，按实际路径修改其中配置。

### 方式二：复制到用户 package 目录

例如放到：

`C:\Users\<你的用户名>\Documents\houdini21.0\packages\`

然后重启 Houdini。

## 打开面板

重启 Houdini 后：

1. 打开 `Windows > New Pane Tab Type > Python Panel`
2. 选择 `Houdini AI Agent`

也可以通过仓库附带的 `Houdini AI` shelf 按钮打开。

## 推荐验证步骤

你可以在 Houdini 中按下面顺序快速验证当前版本：

1. 打开面板，确认右侧工程上下文会刷新。
2. 选中一个节点，点击 `查看选中节点`，确认能看到真实节点路径、类型和参数预览。
3. 点击 `创建节点`：
   - 如果有选中节点，应在其后创建 `OUT_AGENT_PREVIEW`
   - 如果没有选中节点，应创建回退用的预览节点/容器
4. 点击 `捕获视口`，确认：
   - 会生成真实截图文件
   - 聊天区里会出现这张截图
5. 选中一个带有明显代码拼写错误的节点，点击 `修复错误`，测试第一版自动修复流程。
6. 在模型栏选择 `Codex Local`，发送文本或图片消息，验证真实模型回复。
7. 如果你有自己的 OpenAI-compatible provider，也可以在设置中额外配置。

## 会话保存机制

当当前 HIP 文件已经保存过时：

- 会话索引保存到 `$HIP/Agent/session_index.json`
- 每个会话单独保存到 `$HIP/Agent/sessions/<conversation_id>.json`
- 会话图片保存到 `$HIP/Agent/images/<conversation_id>/`

如果当前 HIP 还没有保存，面板仍可正常使用，但工程内自动保存会延后到 HIP 真正落盘后再启用。

## 导入与导出

面板支持导入和导出会话：

- 导出的会话会包含消息内容和图片
- 导入会话时，图片会恢复到当前工程的 Agent 目录中

## 当前阶段说明

当前版本仍然以前端和交互为主，但已经不再是纯 mock：

- `Mock Preview` 仍可作为安全预览模式使用
- `Codex Local` 已可直接复用本机 Codex 登录能力进行真实聊天和图片提问
- OpenAI-compatible provider 仍作为可选高级配置保留
- 会真正修改 Houdini 的工具动作目前仍以预演/建议为主
- 自动分析错误并修复的执行链路还未接入

## 后续计划

- 接入真实模型 provider
- 接入多模态图片识别
- 接入 Houdini 节点创建、参数编辑、连线与 cook
- 接入错误分析与自动修复闭环
- 完善执行日志、工具审计和调试信息
