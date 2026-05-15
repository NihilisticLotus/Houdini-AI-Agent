# Houdini AI Agent

**[English](README.md)** | **[中文](README_CN.md)**

An AI-powered assistant for SideFX Houdini 21, featuring autonomous multi-turn Function Calling, 30+ HOM tools, a brain-inspired long-term memory system, a plugin hook system for community extensions, user-defined context rules, local documentation RAG, 9 pre-built analysis skills, and a dark UI with bilingual support.

Built on the **OpenAI Function Calling** protocol, the agent can read node networks, create/modify/connect/delete nodes, run Python and shell code, search local documentation, create structured execution plans, learn from past interactions, and be extended via plugins — all within an iterative agent loop. A centralized **ToolRegistry** unifies core tools, skills, and plugin tools with mode-based access control.

## Core Features

### Agent Loop

The AI operates in an autonomous **agent loop**: it receives a user request, plans the steps, calls tools, inspects results, and iterates until the task is complete. Three modes are available:

- **Agent mode** — Full access to all 30+ tools. The AI can create, modify, connect, and delete nodes, set parameters, execute scripts, and save the scene.
- **Ask mode** — Read-only. The AI can only query scene structure, inspect parameters, search documentation, and provide analysis. All mutating tools are blocked by a `ToolRegistry` mode guard.
- **Plan mode** — The AI enters a planning phase: it researches the current scene (read-only), clarifies requirements via `ask_question`, then generates a structured execution plan with DAG flow. The user reviews and confirms before execution begins.

```
User request → AI plans → call tools → inspect results → call more tools → … → final reply
```

- **Multi-turn tool calling** — the AI decides which tools to call and in what order
- **Streaming output** — real-time display of thinking process and responses
- **Extended Thinking** — native support for reasoning models (DeepSeek-R1, GLM, Claude with thinking tags)
- **Stop anytime** — interrupt the running agent loop at any point
- **Smart context management** — round-based conversation trimming that never truncates user/assistant messages, only compresses tool results
- **Todo task system** — complex tasks are broken into tracked subtasks with live status updates
- **Long-term memory** — brain-inspired three-layer memory system (episodic, semantic, procedural) with reward-driven learning and automatic reflection
- **Plugin system** — external community extensions via `plugins/` directory with hook events, custom tools, and settings
- **User Rules** — Cursor-style persistent context rules that are automatically injected into every AI request

### Supported AI Providers

| Provider | Models | Notes |
|----------|--------|-------|
| **Codex Local** | Local Codex CLI | Reuses the machine's Codex CLI login; no API key needed; optional vision backend |
| **OpenAI-compatible** | User-configurable | Any OpenAI-compatible endpoint (DeepSeek, GLM, GPT, Ollama, LM Studio, vLLM, etc.); configurable URL, API Key, model name, context limit, vision & FC support |
| **Mock Preview** | Offline | Local mock mode for testing without an AI provider |

### Vision / Image Input

- **Multimodal messages** — attach images (PNG/JPG/GIF/WebP) to your messages for vision-capable models
- **Paste & drag-drop** — `Ctrl+V` paste from clipboard, drag image files into the chat input
- **File picker** — click the "Img" button to select images from disk
- **Image preview** — thumbnails displayed above the input box before sending
- **Vision backend routing** — if the main model is text-only, images are automatically summarized by a separate vision backend
- **Model-aware** — automatically checks if the current model supports vision; text-only models like GLM-5.1 are blocked from direct image input

## Available Tools (30+)

### Scene Analysis

| Tool | Description |
|------|-------------|
| `analyze_scene` | Read current scene context — network structure, selected nodes, viewport summary, errors/warnings |
| `inspect_selection` | Read selected node paths, type information, parameters, and diagnostics |
| `capture_viewport` | Capture or summarize the current Scene Viewer viewport |

### Node Operations

| Tool | Description |
|------|-------------|
| `create_node` | Create a Houdini node by type name in the current or specified network |
| `delete_node` | Delete a node by its path |
| `copy_node` | Copy/clone a node to the same or another network |
| `connect_nodes` | Connect output of one node to input of another (with input index control) |
| `set_parm` | Set a single parameter value on an existing node |
| `batch_set_parameters` | Set the same parameter across multiple nodes |
| `set_display_flag` | Set display and render flags on a node |
| `apply_code` | Replace an editable code parameter (VEX/Python) to repair a node error |

### Query & Inspection

| Tool | Description |
|------|-------------|
| `get_network_structure` | Get node network topology — names, types, connections, flags, error indicators |
| `get_node_parameters` | Get all parameters of a node with type, current value, and flags |
| `list_children` | List child nodes of a network with type and flags |
| `check_errors` | Check cooking errors and warnings for a node |
| `get_node_positions` | Get node positions in the network editor |
| `find_nodes_by_param` | Search nodes by parameter name and optional value match |

### Node Layout

| Tool | Description |
|------|-------------|
| `layout_nodes` | Auto-layout nodes — supports `auto`, `grid`, and `columns` strategies |

### Code Execution

| Tool | Description |
|------|-------------|
| `execute_python` | Run Python code in Houdini's Python environment (`hou` module available) |
| `execute_shell` | Run system shell commands (pip, git, ffmpeg, etc.) with timeout and safety checks |

### Scene Operations

| Tool | Description |
|------|-------------|
| `save_hip` | Save the current HIP file |
| `undo_redo` | Perform undo or redo in Houdini |

### Documentation

| Tool | Description |
|------|-------------|
| `search_local_doc` | Search Houdini offline documentation (nodes, VEX functions, HOM API, knowledge base) |

### Plan Mode

| Tool | Description |
|------|-------------|
| `create_plan` | Create a structured execution plan with steps, dependencies, and risk assessment |
| `update_plan_step` | Update a plan step's status during execution |
| `ask_question` | Ask the user a clarification question during the planning phase |

### Task Management

| Tool | Description |
|------|-------------|
| `add_todo` | Add a compact progress task for multi-step runs |
| `update_todo` | Update task status (pending / in_progress / done / error) |

## Skills System (9 Analysis Scripts)

Skills are pre-optimized Python scripts that run inside the Houdini environment for reliable geometry analysis. They are automatically registered in the `ToolRegistry` as `skill:xxx` tools.

| Skill | Description |
|-------|-------------|
| `analyze_point_attrib` | Attribute statistics (min/max/mean/std/NaN/Inf) for point/vertex/prim/detail |
| `analyze_normals` | Normal quality detection — NaN, zero-length, non-normalized, flipped faces |
| `bounding_box_info` | Bounding box, center, size, diagonal, volume, surface area, aspect ratio |
| `connectivity_analysis` | Connected components analysis (piece count, point/prim per piece) |
| `compare_attributes` | Diff attributes between two nodes (added/removed/type-changed) |
| `find_dead_nodes` | Find orphan and unused end-of-chain nodes |
| `trace_dependencies` | Trace upstream dependencies or downstream impacts |
| `find_attrib_references` | Find all nodes referencing a given attribute (VEX code, expressions, string params) |
| `analyze_cook_performance` | Network-wide cook-time ranking, geometry inflation detection, bottleneck identification |

## Project Structure

```
Houdini-AI-Agent/
├── packages/
│   └── houdini_ai_agent.json          # Houdini package entry (HOUDINI_PATH)
├── houdini/
│   ├── python3.11libs/
│   │   └── houdini_ai_agent/          # Main plugin package
│   │       ├── __init__.py
│   │       ├── qt.py                  # PySide2/PySide6 compatibility layer
│   │       ├── adapters/              # Houdini abstraction layer
│   │       │   ├── houdini.py         # Real Houdini adapter (hou module)
│   │       │   └── mock_houdini.py    # Mock adapter for testing outside Houdini
│   │       ├── core/                  # Core engine modules
│   │       │   ├── agent_loop.py      # Multi-turn Function Calling agent loop
│   │       │   ├── openai_compat.py   # Streaming SSE + FC request/response handling
│   │       │   ├── tool_registry.py   # Unified ToolRegistry (core/skill/plugin tools)
│   │       │   ├── action_runner.py   # Tool execution dispatch with validation
│   │       │   ├── session.py         # AgentSession — Qt signal orchestration
│   │       │   ├── plan_store.py      # Plan normalization, persistence, step management
│   │       │   ├── context_manager.py # Round-based trimming + smart compression
│   │       │   ├── vision_router.py   # Vision backend selection (direct/auto/explicit)
│   │       │   ├── config.py          # Runtime configuration management
│   │       │   ├── i18n.py            # Bilingual translation (Chinese/English)
│   │       │   ├── doc_rag.py         # Local documentation RAG (nodes/VEX/HOM)
│   │       │   ├── thread_dispatch.py # Main-thread safety for HOM operations
│   │       │   ├── codex_cli.py       # Codex Local CLI integration
│   │       │   ├── memory_store.py    # Three-layer SQLite memory (episodic/semantic/procedural)
│   │       │   ├── embedding.py       # Local text embedding (sentence-transformers / fallback)
│   │       │   ├── reward_engine.py   # Reward scoring & memory importance updates
│   │       │   ├── reflection.py      # Rule-based + LLM deep reflection module
│   │       │   ├── growth_tracker.py  # Growth metrics & personality trait formation
│   │       │   ├── rules_manager.py   # User Rules manager (UI rules + file rules)
│   │       │   └── hooks/             # Plugin hook system
│   │       │       ├── hook_manager.py    # HookManager singleton (7 events)
│   │       │       ├── plugin_context.py  # PluginContext API (tools, hooks, buttons, settings)
│   │       │       └── plugin_loader.py   # Plugin directory scanner & loader
│   │       ├── skills/                # Pre-built analysis scripts (auto-registered as tools)
│   │       │   ├── __init__.py        # Skill registry & loader
│   │       │   ├── analyze_point_attrib.py
│   │       │   ├── analyze_normals.py
│   │       │   ├── bounding_box_info.py
│   │       │   ├── compare_attributes.py
│   │       │   ├── connectivity_analysis.py
│   │       │   ├── find_attrib_references.py
│   │       │   ├── find_dead_nodes.py
│   │       │   ├── trace_dependencies.py
│   │       │   └── analyze_cook_performance.py
│   │       └── ui/                    # UI layer
│   │           ├── main_panel.py      # Main Python Panel widget
│   │           ├── chat_view.py       # Chat display & message rendering
│   │           ├── context_panel.py   # Scene context sidebar
│   │           ├── settings_dialog.py # Settings & provider configuration
│   │           ├── style.py           # Theme & QSS styles
│   │           └── widgets/           # Reusable UI widgets
│   │               ├── code_preview.py    # Streaming VEX code preview
│   │               ├── node_completer.py  # @node mention autocomplete
│   │               ├── param_diff.py      # Parameter diff (red/green comparison)
│   │               ├── token_analytics.py # Token usage & cost tracking
│   │               └── tool_result_card.py # Collapsible tool result cards
│   ├── python_panels/
│   │   └── houdini_ai_agent.pypanel  # Python Panel registration
│   └── toolbar/
│       └── houdini_ai_agent.shelf     # Shelf tools
├── plugins/                           # Community plugins directory
│   └── _example_plugin.py            # Example plugin template
├── rules/                             # File-based user rules (*.md, *.txt auto-loaded)
│   └── _example.md                    # Example rule template
├── scripts/
│   ├── validate.py                    # One-command validation (compile + smoke + test)
│   └── smoke_import.py                # Import smoke test with mock adapter
├── tests/                             # Regression test suite (14 test modules)
│   ├── test_action_runner.py
│   ├── test_context_manager.py
│   ├── test_core_state.py
│   ├── test_doc_rag.py
│   ├── test_hooks.py
│   ├── test_i18n.py
│   ├── test_memory.py
│   ├── test_plan_store.py
│   ├── test_rules.py
│   ├── test_skills.py
│   ├── test_text_encoding.py
│   ├── test_thread_dispatch.py
│   ├── test_vision_router.py
│   └── test_widgets.py
├── docs/
│   └── README.en.md                   # Detailed English guide
├── README.md                          # This file
├── README_CN.md                       # Chinese documentation
└── TODO.md                            # Development roadmap
```

## Quick Start

### Requirements

- **Houdini 21+**
- **Python 3.11** (bundled with Houdini 21)
- **PySide6** (bundled with Houdini 21)

### Installation

1. Clone or download this repository
2. Ensure `packages/houdini_ai_agent.json` points to the correct repository path
   - Default: `D:/Project/Houdini/Houdini-AI-Agent`
   - If placed elsewhere, update the `HOUDINI_AI_AGENT_ROOT` path in the JSON file
3. Copy the package file (or a symlink) to your Houdini packages directory

### Launch in Houdini

1. Restart Houdini
2. Open `Windows > New Pane Tab Type > Python Panel > Houdini AI Agent`
3. Or use the `Houdini AI` shelf button

### Configure Provider

In the Settings panel:

1. Select a provider type (Codex Local, OpenAI-compatible, or Mock Preview)
2. For OpenAI-compatible providers:
   - Enter the API URL (e.g. `https://api.openai.com/v1`)
   - Enter the API key (or an environment variable name like `OPENAI_API_KEY`)
   - Enter the model name (e.g. `gpt-5.2`)
3. Click **Test Connection** to verify
4. Optionally configure a separate vision backend for text-only models

## Architecture

### Agent Loop Flow

```
┌─────────────────────────────────────────────────────────┐
│  User sends message                                      │
│  ↓                                                       │
│  System prompt + conversation history + RAG docs         │
│  + User Rules                                            │
│  ↓                                                       │
│  AI model (streaming) → thinking + tool_calls            │
│  ↓                                                       │
│  Tool executor dispatches each tool:                     │
│    - Houdini tools → main thread (BlockingQueued)        │
│    - Shell / doc / skills → background thread            │
│  ↓                                                       │
│  Tool results → fed back to AI as tool messages          │
│  ↓                                                       │
│  AI continues (may call more tools or produce final text)│
│  ↓                                                       │
│  Loop until AI finishes or max iterations reached        │
└─────────────────────────────────────────────────────────┘
```

### Three-Layer Architecture

| Layer | Modules | Responsibility |
|-------|---------|---------------|
| **Adapters** | `houdini.py`, `mock_houdini.py` | HOM abstraction — all `hou.*` calls isolated here |
| **Core** | `agent_loop`, `tool_registry`, `action_runner`, `session`, … | Engine logic — FC parsing, tool dispatch, memory, rules, hooks |
| **UI** | `main_panel`, `chat_view`, `context_panel`, `settings_dialog` | PySide6 panel — chat display, context sidebar, settings |

### ToolRegistry

A centralized tool management system that unifies three capability sources:

| Source | Description |
|--------|-------------|
| **Core** | Built-in Houdini tools (28+), dispatched by ActionRunner → Adapter |
| **Skill** | Pre-built analysis scripts (9), auto-registered as `skill:xxx` |
| **Plugin** | Community plugin tools, registered via `PluginContext.register_tool()` |

Key features:
- **Mode-based access control** — tools tagged with allowed modes (`agent`, `ask`, `plan_planning`, `plan_executing`); mode guards automatically filter
- **Tag classification** — `readonly`, `network`, `geometry`, `system`, `docs`, `task`, `dangerous`
- **Enable/disable** — individual tools can be toggled on/off; state persisted in config
- **Thread-safe** — all registration/query operations are lock-protected
- **OpenAI FC schema export** — `schemas_for_provider()` returns full JSON Schema arrays

### Plan Mode

Plan mode enables the AI to tackle complex tasks through a structured workflow:

1. **Research** — Read-only scene investigation using query tools
2. **Clarify** — Interactive Q&A with the user via `ask_question` when ambiguity exists
3. **Plan** — Generate a structured execution plan with steps, dependencies, and risk assessment

The plan is displayed as an interactive card with confirm/cancel controls. Confirming a plan switches to Agent mode and executes the steps sequentially.

### Brain-inspired Long-term Memory System

A five-module system that enables the agent to learn and improve over time:

| Module | Description |
|--------|-------------|
| `memory_store.py` | Three-layer SQLite storage — **Episodic** (task experiences), **Semantic** (abstracted rules), **Procedural** (problem-solving strategies) |
| `embedding.py` | Local text embedding using `sentence-transformers/all-MiniLM-L6-v2` (384-dim) with fallback to character n-gram pseudo-vectors |
| `reward_engine.py` | Dopamine-inspired reward scoring — success, efficiency, novelty, error penalty; drives memory importance with time decay |
| `reflection.py` | Hybrid reflection — rule-based extraction after every task + periodic LLM deep reflection |
| `growth_tracker.py` | Rolling-window metrics (error rate, success rate, tool efficiency) + personality trait formation |

Memory is activated at query time: relevant episodic memories, semantic rules, and procedural strategies are retrieved via cosine similarity and injected into the system prompt.

### Plugin System

The agent supports external community extensions via a plugin architecture:

- **HookManager** (singleton) — manages event registration and dispatch with priority ordering
- **PluginLoader** — scans the `plugins/` directory for `.py` files, auto-loads enabled plugins
- **PluginContext** — API object passed to each plugin's `register(ctx)` function:
  - `ctx.on(event, callback)` — register event hooks
  - `ctx.register_tool(name, description, schema, handler)` — register custom AI-callable tools
  - `ctx.register_button(icon, tooltip, callback)` — add toolbar buttons
  - `ctx.get_setting(key)` / `ctx.set_setting(key, value)` — persistent per-plugin settings
- **7 hook events**: `before_model_request`, `after_model_response`, `before_tool_execution`, `after_tool_execution`, `content_chunk`, `conversation_start`, `conversation_end`

### User Rules (Custom Context)

Similar to Cursor Rules, users can define persistent context that is automatically injected into every AI request:

- **File Rules** — `.md` and `.txt` files placed in the `rules/` directory are auto-loaded
- **UI Rules** — created and managed via the Rules Editor dialog (stored in config)
- **Prompt injection** — all enabled rules are merged and wrapped in `<user_rules>` tags, injected into the system prompt

### Context Management

- **Native tool message chain**: `assistant(tool_calls)` → `tool(result)` messages passed directly to the model
- **Round-based trimming**: Conversations split into rounds (by user messages); older rounds' tool results compressed first, then entire rounds removed
- **Never truncate user/assistant**: Only `tool` result content is compressed or removed
- **Image payload stripping**: Base64 images from older rounds replaced with text placeholders
- **Token budget estimation**: Character-based approximation for context window management

### Internationalization (i18n)

- **Bilingual support** — full Chinese/English interface with `tr()` translation function
- **Dynamic switching** — change language in settings; UI elements and system prompts update instantly
- **System prompt adaptation** — AI reply language enforced via system prompt rules

### Thread Safety

- Houdini node operations **must** run on the Qt main thread — dispatched via `BlockingQueuedConnection`
- Non-Houdini tools (shell, doc lookup) run directly in the **background thread**
- All UI updates use Qt signals for thread-safe cross-thread communication
- All singletons (`get_embedder()`, `get_reward_engine()`, etc.) use double-checked locking with `threading.Lock`

### Local Documentation Index

The `doc_rag.py` module provides fast lookup from bundled documentation:

- **nodes.zip** — Node documentation (type, description, parameters)
- **vex.zip** — VEX function signatures and descriptions
- **hom.zip** — HOM class and method docs
- **Knowledge bases** — Houdini programming references

Relevant docs are automatically injected into the system prompt based on the user's query.

## Usage Examples

**Create a scatter setup:**
```
User: Create a box, scatter 500 points on it, and copy small spheres to the points.
Agent: [add_todo: plan 4 steps]
       [create_node: box]
       [create_node: scatter]
       [set_parm: scatter → npts = 500]
       [create_node: sphere]
       [set_parm: sphere → radius = 0.05]
       [create_node: copytopoints]
       [connect_nodes: box → scatter → sphere → copytopoints]
       [layout_nodes]
Done. Created box1 → scatter1 → copytopoints1 with a sphere template. 500 points, radius 0.05.
```

**Analyze geometry attributes:**
```
User: What attributes does /obj/geo1/OUT have?
Agent: [run_skill: analyze_point_attrib, node_path=/obj/geo1/OUT]
The node has 5 point attributes: P(vector3), N(vector3), Cd(vector3), pscale(float), id(int). ...
```

**Search documentation:**
```
User: How do I use the attribwrangle node?
Agent: [search_local_doc: attribwrangle]
Based on the documentation, Attribute Wrangle runs VEX code on points, primitives, vertices, or details...
```

**Execute Python code:**
```
User: List all cameras in the scene.
Agent: [execute_python: import hou; cams = [n.path() for n in hou.node('/obj').children() if n.type().name() == 'cam']; print(cams)]
Found 2 cameras: ['/obj/cam1', '/obj/cam2']
```

**Plan a complex task:**
```
User: I need a complete terrain generation pipeline with erosion.
Agent: [Plan mode activated]
       [analyze_scene]
       [ask_question: "What resolution and extent do you need?"]
       [create_plan: 6-step pipeline with dependencies]
       [User confirms plan]
       [Executing step 1/6: Create heightfield grid...]
       [Executing step 2/6: Add noise layer...]
       ...
Done. Terrain pipeline created with erosion, 512x512 resolution.
```

## Local Validation

Run the repository validation suite before testing in Houdini:

```powershell
python scripts/validate.py
```

On Windows, `py -3 scripts/validate.py` is an equivalent fallback.

The script:
1. Compiles all Python files (syntax check)
2. Runs `scripts/smoke_import.py` with the mock adapter (no Houdini needed)
3. Discovers and runs all tests under `tests/`

## Provider Configuration

### Codex Local
- Reuses the machine's Codex CLI login
- No API key needed
- Can act as an optional vision backend

### OpenAI-compatible Providers
- Enter API URL, key, and model name in Settings
- Supports environment variable names (e.g. `DEEPSEEK_API_KEY`)
- Enable/disable Vision and Function Calling per provider

### Vision Backend
- **Auto** — automatically selects a vision-capable provider
- **Disabled** — no image processing
- **Specific provider** — use a designated provider for image analysis
- **Codex Local** — explicitly use Codex Local as vision backend

## UI Features

- Native Houdini Python Panel — no external window
- Multi-session chat with rename, search, import, export, delete
- Per-session autosave under `$HIP/Agent`
- Scene context panel (HIP path, network, selection, viewport, errors)
- Clickable Houdini node paths in replies
- Compact tab strip for session switching
- High-DPI-aware UI scaling with `HOUDINI_AI_AGENT_UI_SCALE` override
- Dark theme with collapsible thinking blocks and tool result cards
- Streaming code preview for VEX edits
- Parameter diff preview (red/green comparison)
- Token analytics panel (per-request usage and cost)

## Documentation

- [Detailed English Guide](docs/README.en.md)
- [中文说明](README_CN.md)
- [Development Roadmap](TODO.md)

## Credits

Architecture and feature inspiration from [Kazama-Suichiku/Houdini-Agent](https://github.com/Kazama-Suichiku/Houdini-Agent).

## License

MIT
