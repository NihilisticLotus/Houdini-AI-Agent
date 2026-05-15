# Houdini AI Agent 中文说明

**[English](README.md)** | **[中文](README_CN.md)**

面向 SideFX Houdini 21 的 AI 助手插件，具备自主多轮 Function Calling、30+ HOM 工具、类脑长期记忆系统、插件钩子系统、用户自定义规则、本地文档 RAG、9 个预置分析技能，以及深色主题中英双语 UI。

基于 **OpenAI Function Calling** 协议，Agent 可以读取节点网络、创建/修改/连接/删除节点、执行 Python 和 Shell 代码、搜索本地文档、创建结构化执行计划、从历史交互中学习、通过插件扩展功能——全部在迭代式 Agent Loop 内完成。集中式 **ToolRegistry** 统一管理核心工具、技能工具和插件工具，并带有模式化访问控制。

## 核心特性

### Agent Loop（代理循环）

AI 在自主 **Agent Loop** 中运行：接收用户请求 → 规划步骤 → 调用工具 → 检查结果 → 持续迭代，直到任务完成。支持三种工作模式：

- **Agent 模式** — 完整访问所有 30+ 工具。AI 可以创建、修改、连接、删除节点，设置参数，执行脚本，保存场景。
- **Ask 模式** — 只读模式。AI 只能查询场景结构、检查参数、搜索文档、提供分析。所有修改类工具被 `ToolRegistry` 模式守卫拦截。
- **Plan 模式** — AI 进入规划阶段：先研究当前场景（只读），通过 `ask_question` 澄清需求，然后生成带 DAG 流程的结构化执行计划。用户审核确认后再开始执行。

```
用户消息 → AI 规划 → 调用工具 → 检查结果 → 继续调用工具 → … → 最终回复
```

- **多轮工具调用** — AI 自主决定调用哪些工具以及调用顺序
- **流式输出** — 实时显示思考过程和回复
- **扩展思考** — 原生支持推理模型（DeepSeek-R1、GLM、Claude 思考标签等）
- **随时中断** — 可随时中断正在运行的 Agent Loop
- **智能上下文管理** — 基于轮次的对话裁剪，永不截断用户/助手消息，只压缩工具结果
- **Todo 任务系统** — 复杂任务自动拆分为可追踪的子任务，实时更新状态
- **长期记忆** — 类脑三层记忆系统（情景/语义/程序性），带奖赏驱动学习和自动反思
- **插件系统** — 通过 `plugins/` 目录的外部社区扩展，支持钩子事件、自定义工具和设置
- **用户规则** — 类似 Cursor Rules 的持久化上下文规则，自动注入到每次 AI 请求中

### 支持的 AI Provider

| Provider | 模型 | 说明 |
|----------|------|------|
| **Codex Local** | 本地 Codex CLI | 复用本机 Codex CLI 登录态，无需 API Key；可选视觉后端 |
| **OpenAI-compatible** | 用户配置 | 任何 OpenAI 兼容端点（DeepSeek、GLM、GPT、Ollama、LM Studio、vLLM 等）；可配置 URL、API Key、模型名、上下文长度、视觉和 FC 支持 |
| **Mock Preview** | 离线模式 | 本地 Mock 模式，无需 AI Provider 即可测试 |

### 视觉 / 图片输入

- **多模态消息** — 为视觉模型附加图片（PNG/JPG/GIF/WebP）
- **粘贴和拖拽** — `Ctrl+V` 从剪贴板粘贴，拖拽图片文件到输入框
- **文件选择器** — 点击 "Img" 按钮从磁盘选择图片
- **图片预览** — 发送前在输入框上方显示缩略图
- **视觉后端路由** — 如果主模型不支持视觉，图片会自动由独立的视觉后端总结
- **模型感知** — 自动检查当前模型是否支持视觉；GLM-5.1 等纯文本模型会被阻止直接输入图片

## 可用工具（30+）

### 场景分析

| 工具 | 描述 |
|------|------|
| `analyze_scene` | 读取当前场景上下文 — 网络结构、选中节点、视口摘要、错误/警告 |
| `inspect_selection` | 读取选中节点路径、类型信息、参数和诊断 |
| `capture_viewport` | 捕获或总结当前场景查看器视口 |

### 节点操作

| 工具 | 描述 |
|------|------|
| `create_node` | 在当前或指定网络中按类型名创建 Houdini 节点 |
| `delete_node` | 按路径删除节点 |
| `copy_node` | 复制/克隆节点到相同或不同网络 |
| `connect_nodes` | 将一个节点的输出连接到另一个节点的输入（支持输入索引控制） |
| `set_parm` | 设置已有节点的单个参数值 |
| `batch_set_parameters` | 批量设置多个节点的相同参数 |
| `set_display_flag` | 设置节点的显示和渲染标志 |
| `apply_code` | 替换可编辑代码参数（VEX/Python）以修复节点错误 |

### 查询与检查

| 工具 | 描述 |
|------|------|
| `get_network_structure` | 获取节点网络拓扑 — 名称、类型、连接、标志、错误指示 |
| `get_node_parameters` | 获取节点所有参数，包括类型、当前值和标志 |
| `list_children` | 列出网络的子节点及类型和标志 |
| `check_errors` | 检查节点的烹饪错误和警告 |
| `get_node_positions` | 获取网络编辑器中节点的位置 |
| `find_nodes_by_param` | 按参数名和可选值匹配搜索节点 |

### 节点布局

| 工具 | 描述 |
|------|------|
| `layout_nodes` | 自动布局节点 — 支持 `auto`、`grid`、`columns` 策略 |

### 代码执行

| 工具 | 描述 |
|------|------|
| `execute_python` | 在 Houdini Python 环境中运行代码（可使用 `hou` 模块） |
| `execute_shell` | 运行系统 Shell 命令（pip、git、ffmpeg 等），带超时和安全检查 |

### 场景操作

| 工具 | 描述 |
|------|------|
| `save_hip` | 保存当前 HIP 文件 |
| `undo_redo` | 在 Houdini 中执行撤销或重做 |

### 文档

| 工具 | 描述 |
|------|------|
| `search_local_doc` | 搜索 Houdini 离线文档（节点、VEX 函数、HOM API、知识库） |

### 计划模式

| 工具 | 描述 |
|------|------|
| `create_plan` | 创建结构化执行计划，包含步骤、依赖和风险评估 |
| `update_plan_step` | 在执行期间更新计划步骤的状态 |
| `ask_question` | 在规划阶段向用户提问以澄清需求 |

### 任务管理

| 工具 | 描述 |
|------|------|
| `add_todo` | 添加紧凑进度任务，用于多步骤执行 |
| `update_todo` | 更新任务状态（pending / in_progress / done / error） |

## 技能系统（9 个分析脚本）

技能是预优化的 Python 脚本，在 Houdini 环境内运行以实现可靠的几何体分析。它们会自动注册到 `ToolRegistry` 中作为 `skill:xxx` 工具。

| 技能 | 描述 |
|------|------|
| `analyze_point_attrib` | 属性统计（min/max/mean/std/NaN/Inf），支持 point/vertex/prim/detail |
| `analyze_normals` | 法线质量检测 — NaN、零长度、未归一化、翻转面 |
| `bounding_box_info` | 包围盒、中心、尺寸、对角线、体积、表面积、纵横比 |
| `connectivity_analysis` | 连通分量分析（片数、每片的点/面数） |
| `compare_attributes` | 两个节点间属性差异对比（新增/删除/类型变化） |
| `find_dead_nodes` | 查找孤立节点和未使用的链末端节点 |
| `trace_dependencies` | 追踪上游依赖或下游影响 |
| `find_attrib_references` | 查找引用给定属性的所有节点（VEX 代码、表达式、字符串参数） |
| `analyze_cook_performance` | 网络级烹饪时间排名、几何体膨胀检测、瓶颈识别 |

## 项目结构

```
Houdini-AI-Agent/
├── packages/
│   └── houdini_ai_agent.json          # Houdini package 入口（HOUDINI_PATH）
├── houdini/
│   ├── python3.11libs/
│   │   └── houdini_ai_agent/          # 主插件包
│   │       ├── __init__.py
│   │       ├── qt.py                  # PySide2/PySide6 兼容层
│   │       ├── adapters/              # Houdini 抽象层
│   │       │   ├── houdini.py         # 真实 Houdini 适配器（hou 模块）
│   │       │   └── mock_houdini.py    # Mock 适配器（Houdini 外测试用）
│   │       ├── core/                  # 核心引擎模块
│   │       │   ├── agent_loop.py      # 多轮 Function Calling 代理循环
│   │       │   ├── openai_compat.py   # 流式 SSE + FC 请求/响应处理
│   │       │   ├── tool_registry.py   # 统一工具注册表（核心/技能/插件工具）
│   │       │   ├── action_runner.py   # 工具执行调度与验证
│   │       │   ├── session.py         # AgentSession — Qt 信号编排
│   │       │   ├── plan_store.py      # 计划规范化、持久化、步骤管理
│   │       │   ├── context_manager.py # 基于轮次的裁剪 + 智能压缩
│   │       │   ├── vision_router.py   # 视觉后端选择（直接/自动/显式）
│   │       │   ├── config.py          # 运行时配置管理
│   │       │   ├── i18n.py            # 双语翻译（中文/英文）
│   │       │   ├── doc_rag.py         # 本地文档 RAG（节点/VEX/HOM）
│   │       │   ├── thread_dispatch.py # HOM 操作的主线程安全
│   │       │   ├── codex_cli.py       # Codex Local CLI 集成
│   │       │   ├── memory_store.py    # 三层 SQLite 记忆（情景/语义/程序性）
│   │       │   ├── embedding.py       # 本地文本嵌入（sentence-transformers / 回退）
│   │       │   ├── reward_engine.py   # 奖赏评分与记忆重要性更新
│   │       │   ├── reflection.py      # 基于规则 + LLM 深度反思模块
│   │       │   ├── growth_tracker.py  # 成长指标与性格特征形成
│   │       │   ├── rules_manager.py   # 用户规则管理器（UI 规则 + 文件规则）
│   │       │   └── hooks/             # 插件钩子系统
│   │       │       ├── hook_manager.py    # HookManager 单例（7 个事件）
│   │       │       ├── plugin_context.py  # PluginContext API（工具、钩子、按钮、设置）
│   │       │       └── plugin_loader.py   # 插件目录扫描与加载器
│   │       ├── skills/                # 预置分析脚本（自动注册为工具）
│   │       │   ├── __init__.py        # 技能注册表与加载器
│   │       │   ├── analyze_point_attrib.py
│   │       │   ├── analyze_normals.py
│   │       │   ├── bounding_box_info.py
│   │       │   ├── compare_attributes.py
│   │       │   ├── connectivity_analysis.py
│   │       │   ├── find_attrib_references.py
│   │       │   ├── find_dead_nodes.py
│   │       │   ├── trace_dependencies.py
│   │       │   └── analyze_cook_performance.py
│   │       └── ui/                    # UI 层
│   │           ├── main_panel.py      # 主 Python Panel 部件
│   │           ├── chat_view.py       # 聊天显示与消息渲染
│   │           ├── context_panel.py   # 场景上下文侧栏
│   │           ├── settings_dialog.py # 设置与 Provider 配置
│   │           ├── style.py           # 主题与 QSS 样式
│   │           └── widgets/           # 可复用 UI 部件
│   │               ├── code_preview.py    # 流式 VEX 代码预览
│   │               ├── node_completer.py  # @节点 自动补全
│   │               ├── param_diff.py      # 参数差异对比（红绿对比）
│   │               ├── token_analytics.py # Token 使用量与成本追踪
│   │               └── tool_result_card.py # 可折叠工具结果卡片
│   ├── python_panels/
│   │   └── houdini_ai_agent.pypanel  # Python Panel 注册
│   └── toolbar/
│       └── houdini_ai_agent.shelf     # Shelf 工具
├── plugins/                           # 社区插件目录
│   └── _example_plugin.py            # 示例插件模板
├── rules/                             # 基于文件的用户规则（*.md、*.txt 自动加载）
│   └── _example.md                    # 示例规则模板
├── scripts/
│   ├── validate.py                    # 一键验证（编译 + 冒烟 + 测试）
│   └── smoke_import.py                # 使用 Mock 适配器的导入冒烟测试
├── tests/                             # 回归测试套件（14 个测试模块）
├── docs/
│   └── README.en.md                   # 详细英文指南
├── README.md                          # 英文说明
├── README_CN.md                       # 本文件
└── TODO.md                            # 开发路线图
```

## 快速开始

### 环境要求

- **Houdini 21+**
- **Python 3.11**（Houdini 21 自带）
- **PySide6**（Houdini 21 自带）

### 安装

1. 克隆或下载本仓库
2. 确保 `packages/houdini_ai_agent.json` 指向正确的仓库路径
   - 默认：`D:/Project/Houdini/Houdini-AI-Agent`
   - 如果放在其他位置，请修改 JSON 文件中的 `HOUDINI_AI_AGENT_ROOT` 路径
3. 将 package 文件（或符号链接）复制到 Houdini packages 目录

### 在 Houdini 中启动

1. 重启 Houdini
2. 打开 `Windows > New Pane Tab Type > Python Panel > Houdini AI Agent`
3. 或使用 `Houdini AI` shelf 按钮

### 配置 Provider

在 Settings 面板中：

1. 选择 Provider 类型（Codex Local、OpenAI-compatible 或 Mock Preview）
2. 对于 OpenAI-compatible Provider：
   - 输入 API URL（如 `https://api.openai.com/v1`）
   - 输入 API Key（或环境变量名如 `OPENAI_API_KEY`）
   - 输入模型名称（如 `gpt-5.2`）
3. 点击 **Test Connection** 验证连接
4. 可选配置独立的视觉后端用于纯文本模型

## 架构

### Agent Loop 流程

```
┌─────────────────────────────────────────────────────────┐
│  用户发送消息                                             │
│  ↓                                                       │
│  系统提示词 + 对话历史 + RAG 文档 + 用户规则              │
│  ↓                                                       │
│  AI 模型（流式）→ 思考过程 + 工具调用                     │
│  ↓                                                       │
│  工具执行器调度每个工具：                                 │
│    - Houdini 工具 → 主线程（BlockingQueued）              │
│    - Shell / 文档 / 技能 → 后台线程                      │
│  ↓                                                       │
│  工具结果 → 以 tool 消息反馈给 AI                         │
│  ↓                                                       │
│  AI 继续（可能调用更多工具或生成最终文本）                │
│  ↓                                                       │
│  循环直到 AI 完成或达到最大迭代次数                       │
└─────────────────────────────────────────────────────────┘
```

### 三层架构

| 层 | 模块 | 职责 |
|---|------|------|
| **适配器** | `houdini.py`、`mock_houdini.py` | HOM 抽象 — 所有 `hou.*` 调用隔离在此 |
| **核心** | `agent_loop`、`tool_registry`、`action_runner`、`session` 等 | 引擎逻辑 — FC 解析、工具调度、记忆、规则、钩子 |
| **UI** | `main_panel`、`chat_view`、`context_panel`、`settings_dialog` | PySide6 面板 — 聊天显示、上下文侧栏、设置 |

### ToolRegistry（工具注册表）

统一管理三种能力来源的集中式工具管理系统：

| 来源 | 描述 |
|------|------|
| **核心** | 内置 Houdini 工具（28+），由 ActionRunner → Adapter 调度 |
| **技能** | 预置分析脚本（9 个），自动注册为 `skill:xxx` |
| **插件** | 社区插件工具，通过 `PluginContext.register_tool()` 注册 |

关键特性：
- **模式化访问控制** — 工具标记允许的模式（`agent`、`ask`、`plan_planning`、`plan_executing`）；模式守卫自动过滤
- **标签分类** — `readonly`、`network`、`geometry`、`system`、`docs`、`task`、`dangerous`
- **启用/禁用** — 单个工具可独立开关；状态持久化到配置
- **线程安全** — 所有注册/查询操作受锁保护
- **OpenAI FC Schema 导出** — `schemas_for_provider()` 返回完整 JSON Schema 数组

### Plan 模式

Plan 模式支持 AI 通过结构化工作流处理复杂任务：

1. **研究** — 使用查询工具进行只读场景调查
2. **澄清** — 通过 `ask_question` 与用户互动问答以消除歧义
3. **计划** — 生成带步骤、依赖和风险评估的结构化执行计划

计划以交互式卡片显示，带确认/取消控件。确认后切换到 Agent 模式按步骤执行。

### 类脑长期记忆系统

使 Agent 能够随时间学习和改进的五模块系统：

| 模块 | 描述 |
|------|------|
| `memory_store.py` | 三层 SQLite 存储 — **情景记忆**（任务经历）、**语义记忆**（抽象规则）、**程序性记忆**（问题解决策略） |
| `embedding.py` | 本地文本嵌入，使用 `sentence-transformers/all-MiniLM-L6-v2`（384 维），回退到字符 n-gram 伪向量 |
| `reward_engine.py` | 多巴胺式奖赏评分 — 成功、效率、新颖性、错误惩罚；驱动记忆重要性的时间衰减 |
| `reflection.py` | 混合反思 — 每次任务后的规则提取 + 定期 LLM 深度反思 |
| `growth_tracker.py` | 滑动窗口指标（错误率、成功率、工具效率）+ 性格特征形成 |

记忆在查询时激活：通过余弦相似度检索相关的情景记忆、语义规则和程序性策略，注入到系统提示词中。

### 插件系统

通过插件架构支持外部社区扩展：

- **HookManager**（单例）— 管理事件注册和调度，支持优先级排序
- **PluginLoader** — 扫描 `plugins/` 目录中的 `.py` 文件，自动加载已启用的插件
- **PluginContext** — 传递给每个插件 `register(ctx)` 函数的 API 对象：
  - `ctx.on(event, callback)` — 注册事件钩子
  - `ctx.register_tool(name, description, schema, handler)` — 注册自定义 AI 可调用工具
  - `ctx.register_button(icon, tooltip, callback)` — 添加工具栏按钮
  - `ctx.get_setting(key)` / `ctx.set_setting(key, value)` — 持久化插件设置
- **7 个钩子事件**：`before_model_request`、`after_model_response`、`before_tool_execution`、`after_tool_execution`、`content_chunk`、`conversation_start`、`conversation_end`

### 用户规则（自定义上下文）

类似 Cursor Rules，用户可以定义持久化上下文，自动注入到每次 AI 请求中：

- **文件规则** — 放在 `rules/` 目录中的 `.md` 和 `.txt` 文件会自动加载
- **UI 规则** — 通过规则编辑器对话框创建和管理（存储在配置中）
- **提示词注入** — 所有启用的规则合并后用 `<user_rules>` 标签包裹，注入到系统提示词

### 上下文管理

- **原生工具消息链**：`assistant(tool_calls)` → `tool(result)` 消息直接传递给模型
- **基于轮次的裁剪**：对话按用户消息分割为轮次；先压缩旧轮次的工具结果，再移除整个轮次
- **永不截断用户/助手消息**：只压缩或移除 `tool` 结果内容
- **图片负载剥离**：旧轮次的 base64 图片替换为文本占位符
- **Token 预算估算**：基于字符的近似估计，用于上下文窗口管理

### 国际化（i18n）

- **双语支持** — 完整的中英文界面，使用 `tr()` 翻译函数
- **动态切换** — 在设置中切换语言；UI 元素和系统提示词即时更新
- **系统提示词适配** — 通过系统提示词规则强制 AI 回复语言

### 线程安全

- Houdini 节点操作**必须**在 Qt 主线程运行 — 通过 `BlockingQueuedConnection` 调度
- 非 Houdini 工具（Shell、文档查找）直接在**后台线程**运行
- 所有 UI 更新使用 Qt 信号实现线程安全的跨线程通信
- 所有单例（`get_embedder()`、`get_reward_engine()` 等）使用 `threading.Lock` 双重检查锁定

### 本地文档索引

`doc_rag.py` 模块提供从捆绑文档的快速查找：

- **nodes.zip** — 节点文档（类型、描述、参数）
- **vex.zip** — VEX 函数签名和描述
- **hom.zip** — HOM 类和方法文档
- **知识库** — Houdini 编程参考

根据用户查询自动注入相关文档到系统提示词。

## 使用示例

**创建散布设置：**
```
用户：创建一个 Box，在上面散布 500 个点，然后把小球拷贝到这些点上。
Agent：[add_todo：规划 4 步]
       [create_node：box]
       [create_node：scatter]
       [set_parm：scatter → npts = 500]
       [create_node：sphere]
       [set_parm：sphere → radius = 0.05]
       [create_node：copytopoints]
       [connect_nodes：box → scatter → sphere → copytopoints]
       [layout_nodes]
完成。创建了 box1 → scatter1 → copytopoints1，500 个点，半径 0.05。
```

**分析几何属性：**
```
用户：/obj/geo1/OUT 有哪些属性？
Agent：[run_skill：analyze_point_attrib，node_path=/obj/geo1/OUT]
该节点有 5 个点属性：P(vector3)、N(vector3)、Cd(vector3)、pscale(float)、id(int)。...
```

**搜索文档：**
```
用户：attribwrangle 节点怎么用？
Agent：[search_local_doc：attribwrangle]
根据文档，Attribute Wrangle 在点、面、顶点或细节上运行 VEX 代码...
```

**执行 Python 代码：**
```
用户：列出场景中所有摄像机。
Agent：[execute_python：import hou; cams = [n.path() for n in hou.node('/obj').children() if n.type().name() == 'cam']; print(cams)]
找到 2 个摄像机：['/obj/cam1'，'/obj/cam2']
```

**规划复杂任务：**
```
用户：我需要一个完整的带侵蚀的地形生成管线。
Agent：[Plan 模式已激活]
       [analyze_scene]
       [ask_question："你需要什么分辨率和范围？"]
       [create_plan：6 步管线，含依赖关系]
       [用户确认计划]
       [正在执行步骤 1/6：创建 HeightField 网格...]
       [正在执行步骤 2/6：添加噪波层...]
       ...
完成。地形管线已创建，含侵蚀，512x512 分辨率。
```

## 本地验证

在 Houdini 中测试前运行仓库验证套件：

```powershell
python scripts/validate.py
```

在 Windows 上，`py -3 scripts/validate.py` 是等效的备选命令。

该脚本会：
1. 编译所有 Python 文件（语法检查）
2. 使用 Mock 适配器运行 `scripts/smoke_import.py`（无需 Houdini）
3. 发现并运行 `tests/` 下的所有测试

## Provider 配置

### Codex Local
- 复用本机 Codex CLI 登录态
- 无需 API Key
- 可作为可选视觉后端

### OpenAI-compatible Providers
- 在 Settings 中输入 API URL、Key 和模型名称
- 支持环境变量名（如 `DEEPSEEK_API_KEY`）
- 可按 Provider 启用/禁用视觉和 Function Calling

### 视觉后端
- **Auto** — 自动选择支持视觉的 Provider
- **Disabled** — 不处理图片
- **指定 Provider** — 使用指定的 Provider 进行图片分析
- **Codex Local** — 显式使用 Codex Local 作为视觉后端

## UI 特性

- Houdini 原生 Python Panel — 无需外部窗口
- 多会话聊天，支持重命名、搜索、导入、导出、删除
- 每个会话独立自动保存到 `$HIP/Agent`
- 场景上下文面板（HIP 路径、网络、选择、视口、错误）
- 回复中的 Houdini 节点路径可点击定位
- 紧凑标签栏用于切换会话
- 高 DPI 感知的 UI 缩放，可通过 `HOUDINI_AI_AGENT_UI_SCALE` 覆盖
- 深色主题，带可折叠思考块和工具结果卡片
- VEX 编辑的流式代码预览
- 参数差异预览（红绿对比）
- Token 分析面板（每次请求的使用量和成本）

## 文档

- [详细英文指南](docs/README.en.md)
- [English README](README.md)
- [开发路线图](TODO.md)

## 致谢

架构和功能灵感来自 [Kazama-Suichiku/Houdini-Agent](https://github.com/Kazama-Suichiku/Houdini-Agent)。

## 许可证

MIT
