# Houdini AI Agent 中文说明

Houdini AI Agent 是一个基于 PySide 的 Houdini 21 原生面板插件，目标是把 AI 辅助的场景分析、节点操作、图片理解和后续自动修复尽量都留在 Houdini 内完成。

## 当前能力

- Houdini 原生 Python Panel
- 多会话聊天：
  - 新建
  - 重命名
  - 搜索 / 过滤
  - 导入
  - 导出
  - 删除
- 会话自动保存到 `$HIP/Agent`
- 图片粘贴、拖拽上传、预览、导入、导出
- 回复中的 Houdini 节点路径可点击并自动定位
- 工程上下文面板：
  - HIP 路径
  - 当前网络
  - 当前选中节点
  - 当前视口摘要
  - 错误 / 警告摘要
- Provider 支持：
  - `Codex Local`
  - 自定义 OpenAI-compatible provider
  - `Mock Preview`
- 模型规划后可触发的 Houdini 动作：
  - 场景分析
  - 选中节点检查
  - 视口捕获
  - 节点创建
  - 代码参数修复写回

## 本次新增

- 内置 **视觉兜底** 工作流
  - 如果当前主模型不支持视觉，插件会先用设置中标记为 `Vision Fallback` 的 provider 读取图片
  - 视觉 provider 会输出图片摘要
  - 再把摘要交给主模型继续推理
- 设置页新增能力开关：
  - `Vision`
  - `Vision Fallback`
- 参考 [Kazama-Suichiku/Houdini-Agent](https://github.com/Kazama-Suichiku/Houdini-Agent) 补强了两类非常实用的交互：
  - 聊天内容里的节点路径点击跳转
  - 图片拖拽上传

## 参考 Houdini-Agent 后，我们的结论

那个项目最值得参考的，不只是工具数量，而是产品层的设计方式：

- 对只读分析和修改执行有更清晰的边界
- 对视觉模型能力处理更明确
- 聊天不是纯文本，而是更偏工具型工作区
- 回复内容里有更多“可操作”的交互细节

我们这边这次已经吸收并落地的部分：

- 节点路径点击定位
- 图片拖拽上传
- 更明确的视觉能力与视觉兜底机制

目前仍落后于它的部分：

- 完整的 Ask / Agent / Plan 模式
- Todo 任务卡与执行 DAG
- 插件管理器 / 规则编辑器 / 记忆管理器
- 更广泛的 HOM 工具覆盖，比如连线、删除、复制、布局节点

## 我们当前识别出的几个问题

1. 之前对“无视觉模型”的处理不够稳  
   现在已经修复为主模型 + 视觉 companion 的双层工作流。

2. 聊天区交互感偏弱  
   现在已经补上节点路径点击定位和图片拖拽上传。

3. 中文文档位置不符合长期维护习惯  
   现在中文说明移动到根目录，文件名为 `README_CN.md`。

## 调研过的公开视觉 MCP 方向

以下是这次调研中比较值得继续参考的公开项目：

1. [ColeMurray/moondream-mcp](https://github.com/ColeMurray/moondream-mcp)
   - 轻量本地视觉方向很合适
2. [mrgoonie/human-mcp](https://github.com/mrgoonie/human-mcp)
   - 截图分析、界面对比、文档读取能力都比较强
3. [aliargun/mcp-server-gemini](https://github.com/aliargun/mcp-server-gemini)
   - 适合云端视觉能力路线，当前 GitHub 搜索结果约 240 stars

当前插件没有直接硬绑定某一个外部 MCP，而是先实现了内部的视觉兜底层，后面我们可以再接成本地 Moondream 或其他视觉后端。

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

## 文档

- [English Guide](E:/Work/Houdini/AI_Agent/docs/README.en.md)
- [README_CN](E:/Work/Houdini/AI_Agent/README_CN.md)
- [TODO](E:/Work/Houdini/AI_Agent/TODO.md)
