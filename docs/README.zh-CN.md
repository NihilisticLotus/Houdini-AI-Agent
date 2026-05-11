# Houdini AI Agent 中文说明

## 概述

Houdini AI Agent 是一个基于 PySide 的 Houdini 21 Python Panel 插件。目标是把 AI 辅助的场景分析、节点操作、图片理解和后续自动修复，尽量都留在 Houdini 内完成，而不是来回切换多个软件。

## 当前已经支持的能力

### 会话与工作区

- Houdini 原生 Python Panel
- 多会话管理：
  - 新建
  - 重命名
  - 搜索 / 过滤
  - 导入
  - 导出
  - 删除
- 会话自动保存到 `$HIP/Agent/sessions`
- 会话图片保存到 `$HIP/Agent/images/<conversation_id>/`
- 支持图片粘贴 `Ctrl+V`
- 支持待发送图片预览
- 支持会话图片双击放大查看
- 支持删除单条消息
- 支持清空整个会话消息并二次确认

### AI Provider 层

- `Codex Local`
  - 复用本机已经登录的 Codex CLI
  - 不需要单独填写 OpenAI API Key
- 自定义 OpenAI-compatible provider
  - 可以填写环境变量名
  - 也可以直接填写 API Key
  - 可以设置默认模型
  - 可以设置默认思考档位
  - 可以标记是否支持视觉
  - 可以标记是否作为视觉兜底 provider
- `Mock Preview`
  - 纯前端 / 离线预览模式

### Houdini 上下文与动作

- 读取：
  - HIP 路径
  - 当前网络
  - 当前选中节点
  - 当前视口信息
  - 当前网络错误 / 警告摘要
- 模型规划后可触发的动作：
  - `analyze_scene`
  - `inspect_selection`
  - `capture_viewport`
  - `create_node`
  - `apply_code`

## 新增：视觉兜底工作流

有些模型只有文本能力，没有视觉能力。现在插件内部已经加入一层 **Vision Companion**：

1. 如果当前主模型支持视觉，图片直接发给主模型
2. 如果当前主模型不支持视觉，插件会查找第一个勾选了 `Vision Fallback` 的 provider
3. 这个视觉 provider 先读取图片，生成简洁的图片说明
4. 再把这段图片说明注入给主模型继续推理

这样可以保持结构简单：

- 一个主推理模型
- 一个可选的图片理解 companion

也更符合前面确定的第一性原理：

- 模型负责判断和规划
- 插件负责执行和上下文收集

## 我们调研过的公开视觉 MCP 参考项目

下面这些 GitHub 项目都适合作为后续更强视觉后端的参考：

1. [ColeMurray/moondream-mcp](https://github.com/ColeMurray/moondream-mcp)
   - 基于 Moondream 的 FastMCP 视觉服务
   - 支持图片描述、问答、目标检测、坐标定位、批量分析
   - 很适合作为轻量本地视觉 companion 方向
2. [mrgoonie/human-mcp](https://github.com/mrgoonie/human-mcp)
   - 多模态 MCP 工具集
   - 包含 `eyes_analyze`、`eyes_compare`
   - 很适合截图排错、界面对比、文档读取这类工作流
3. [aliargun/mcp-server-gemini](https://github.com/aliargun/mcp-server-gemini)
   - Gemini 视觉 MCP
   - 当前 GitHub 搜索结果显示约 `240 stars`
   - 适合走云端视觉能力路线

当前插件还没有把这些外部 MCP 直接绑死进主流程，而是先内置了视觉兜底层，保证面板架构更稳、切换成本更低。

## 安装

### 方式一：使用仓库自带 package

仓库已经包含：

- `packages/houdini_ai_agent.json`

让 Houdini 能读取这个 package 文件，或者复制到 Houdini 的 packages 目录后改成你的实际路径。

### 方式二：复制到用户 packages 目录

例如：

`C:\Users\<你的用户名>\Documents\houdini21.0\packages\`

然后重启 Houdini。

## 打开面板

重启 Houdini 后：

1. 打开 `Windows > New Pane Tab Type > Python Panel`
2. 选择 `Houdini AI Agent`

也可以使用仓库自带的 `Houdini AI` shelf。

## 推荐验证步骤

1. 打开面板，确认右侧工程上下文能刷新
2. 选中一个节点，点击 `查看选中节点`
3. 直接输入：
   - `帮我创建一个 box`
4. 点击 `捕获视口`，确认截图出现在聊天区
5. 使用 `Ctrl+V` 粘贴图片
6. 在设置里配置：
   - 一个主文本模型
   - 一个支持视觉、并勾选 `Vision Fallback` 的 provider
7. 发送图片和问题，确认即使主模型本身不支持视觉，也能理解截图内容

## 会话保存位置

当当前 HIP 已经保存时：

- 索引：`$HIP/Agent/session_index.json`
- 会话：`$HIP/Agent/sessions/<conversation_id>.json`
- 图片：`$HIP/Agent/images/<conversation_id>/`

如果 HIP 还没保存，面板仍然可用，但项目内自动保存会等到 HIP 真正落盘后再启用。

## 当前限制

- 视觉兜底目前基于第二个 provider，还不是内置的本地 Moondream Runtime
- 工具执行仍然偏保守，优先安全和可验证
- 自动修复目前重点还是代码参数替换与校验，还没有扩展到整张节点图的复杂修复规划

## 下一步

请看 [TODO](E:/Work/Houdini/AI_Agent/TODO.md)。
