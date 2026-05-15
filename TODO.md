# TODO — Houdini-AI-Agent Roadmap

Prioritized development roadmap integrating advantages from both the current project
architecture and the reference project `Kazama-Suichiku/Houdini-Agent` (v1.5.5).

## Reference Audit 2026-05-12 (Updated 2026-05-16)

**Source**: `D:\Project\Houdini\Houdini-Agent` (local), GitHub `Kazama-Suichiku/Houdini-Agent`.

**What we absorbed** from the reference project — agent loop, tool registry, plan manager,
plugin hooks, rules, memory, and Houdini tool layer as separate subsystems:

- Native OpenAI Function Calling with structured tool result feedback
- Four-mode access policy: `agent`, `ask`, `plan_planning`, `plan_executing`
- 30+ tools covering node graph, connections, deletion, layout, parameters
- Local documentation RAG (nodes/vex/hom ZIP + knowledge bases)
- Streaming AI client with SSE parser
- Thread-safe HOM dispatch via `BlockingQueuedConnection`
- Plan mode with structured execution and step tracking
- Brain-inspired memory: episodic/semantic/procedural SQLite + embedding + reward
- Plugin Hook system (7 events) + User Rules (Cursor-style)
- Skills system (9 analysis scripts auto-registered as tools)
- i18n bilingual support + Token optimization (round trimming)

**What we keep from our project** — core/adapters/ui three-layer architecture,
packages/ standard registration, Python Panel host, unittest framework, qt.py
compatibility layer, compact codebase with focused modules.

---

## Completed

### P0 — Foundation Engine

- [x] **P0.1** Refactor `openai_compat.py` — Streaming SSE parser + Function Calling
  - Streaming SSE parser (`text/event-stream`) — content deltas, tool_calls deltas, reasoning/thinking deltas
  - OpenAI Function Calling request payloads with `tools` array from `ToolRegistry.schemas_for_provider()`
  - Multi-message conversation history with role alternation
  - Function Calling response parsing — `finish_reason`, `tool_calls[].id`, structured `AIResponse`
  - Multiple provider support (OpenAI-compatible FC, JSON-mode fallback)
  - Error handling — timeout, retry with exponential backoff, graceful degradation
- [x] **P0.2** Build `agent_loop.py` — Multi-turn Agent Loop
  - Bounded multi-turn loop with configurable max iterations and tool calls per turn
  - Duplicate readonly-tool-call suppression
  - Cancellation support via QThread interrupt flag
  - Tool result compression for context (truncate long outputs)
  - Progress signals for UI (`tool_call_started`, `tool_call_finished`, `loop_iteration`, `final_response`)
  - Compact trace of all tool call/result pairs
- [x] **P0.3** Upgrade `tool_registry.py` — Full Schema + Tags + Modes
  - OpenAI Function Calling JSON Schema format for each tool
  - Tag classification: `readonly`, `network`, `geometry`, `system`, `docs`, `task`, `dangerous`
  - Four-mode policy: `ask`, `agent`, `plan_planning`, `plan_executing`
  - Per-tool enabled/disabled state (persisted in config)
  - Thread-safety classification: `houdini_main_thread`, `background_safe`, `external_process`
  - `schemas_for_provider()` and `validate_args()` methods
  - Thread-safe registry access with `threading.Lock`

### P1 — Core Capabilities

- [x] **P1.1** Expand Houdini Adapters — 30+ HOM Tools
  - Network operations: `connect_nodes`, `delete_node`, `copy_node`, `layout_nodes`, `get_network_structure`, `get_node_parameters`, `check_errors`
  - Parameter operations: `set_node_parameter`, `batch_set_parameters`, `find_nodes_by_param`
  - Scene operations: `get_node_positions`, `set_display_flag`, `save_hip`, `undo_redo`
  - Code execution: `execute_python` (bounded), `execute_shell` (bounded with timeout)
  - Documentation: `search_local_doc`
  - Mock adapter in sync with all real adapter methods
- [x] **P1.2** Upgrade `action_runner.py` — FC Dispatch + Validation
  - Accept `tool_calls` from AI response
  - Route tool calls to adapter methods via `ToolRegistry` lookup
  - Pre-execution schema validation
  - Structured `tool` role messages with `tool_call_id` for FC feedback
- [x] **P1.3** Build `context_manager.py` — Token Budget + Round Trimming
  - Round-based trimming: never truncate `user`/`assistant` messages
  - Image payload stripping from older rounds
  - Token budget estimation (character-based approximation)
  - Long result pagination
  - Defensive shallow-copy of message dicts at function entry
- [x] **P1.4** Build `thread_dispatch.py` — Main-thread Safety
  - Thread classification for all tools
  - Main-thread executor using `BlockingQueuedConnection`
  - Timeout protection for blocking HOM operations
  - Background worker pool for non-HOM operations
- [x] **P1.5** Session Slim-down
  - `AgentSession` as pure orchestration + Qt signal glue
  - Agent loop wired into session as the execution path
  - Fenced-JSON fallback path for providers without FC

### P2 — Important Enhancements

- [x] **P2.1** Build `doc_rag.py` — Local Documentation RAG
  - `Doc/` directory with nodes.zip, vex.zip, hom.zip + knowledge bases
  - Character n-gram index for O(1) lookup
  - `search_local_doc(query, category, limit)` tool
  - Scene-aware retrieval
- [x] **P2.2** Build `i18n.py` — Bilingual Translation
  - `tr(key)` function with language detection
  - Chinese-English dictionary
  - Dynamic language switching
  - System prompt language auto-detection
- [x] **P2.3** Upgrade `plan_store.py` — Structured Plan + Step Tracking
  - Structured plan workflow with phases and steps
  - Plan data model: title, description, steps, dependencies, risks
  - Tools: `create_plan`, `update_plan_step`, `ask_question`
  - Plan persistence to JSON per conversation

### P3 — Nice-to-Have Enhancements

- [x] **P3.1** Build Skills System
  - Skill loader scanning `skills/` directory
  - Auto-register each skill as `skill:xxx` tool in ToolRegistry
  - 9 analysis scripts: `analyze_normals`, `analyze_point_attrib`, `bounding_box_info`, `compare_attributes`, `connectivity_analysis`, `find_attrib_references`, `find_dead_nodes`, `trace_dependencies`, `analyze_cook_performance`
- [x] **P3.2** Enrich UI Widgets
  - Tool result cards — collapsible, with status grouping
  - Parameter diff preview — red/green comparison
  - Token analytics panel — per-request usage and cost
  - Node completer — `@node` mention autocomplete
  - Streaming code preview — partial code display during streaming

### P4 — Extension Ecosystem

- [x] **P4.1** Plugin Hook System
  - `HookManager` with 7 events: `before_model_request`, `after_model_response`, `before_tool_execution`, `after_tool_execution`, `content_chunk`, `conversation_start`, `conversation_end`
  - `PluginLoader` scanning `plugins/` directory
  - `PluginContext` API: register tools, buttons, settings, hooks
  - Plugin sandbox: catch exceptions, isolate failures
- [x] **P4.2** Brain-inspired Memory System
  - `memory_store.py` — three-layer SQLite (episodic, semantic, procedural)
  - `embedding.py` — local vector similarity (sentence-transformers or char n-gram fallback) with thread-safe singleton
  - `reward_engine.py` — score tool execution outcomes with thread-safe singleton
  - `reflection.py` — periodic self-review with thread-safe singleton
  - `growth_tracker.py` — long-term skill/usage progression with thread-safe singleton
- [x] **P4.3** User Rules System
  - `rules_manager.py` — load rules from `rules/` directory + config
  - File-based rules: `rules/*.md` auto-loaded
  - Inject enabled rules into system prompt with `<user_rules>` block
  - Rules injection in all prompt builders (system, agent tool, codex)

### Testing

- [x] 14 test modules covering all major subsystems
- [x] Mode guard regression tests
- [x] Plan persistence and recovery tests
- [x] ActionRunner tests
- [x] PlanStore tests
- [x] VisionRouter tests
- [x] Context manager tests
- [x] Doc RAG tests
- [x] i18n tests
- [x] Memory system tests
- [x] Hook/plugin tests
- [x] Rules tests
- [x] Skills tests
- [x] Thread dispatch tests
- [x] Widget tests
- [x] Non-UI Qt fallback for running core tests outside Houdini
- [x] `scripts/validate.py` — compile + smoke import + unit-test discovery (370 tests passing)

### Bug Fixes (2026-05-16 Audit)

- [x] **CRITICAL**: Fixed dead code in `_build_agent_tool_prompt` — `return (...)` expression made rules injection unreachable; changed to `prompt = (...)` so rules are properly injected
- [x] **MEDIUM**: Added rules injection to `_build_codex_prompt` (was missing entirely)
- [x] **MEDIUM**: Added thread-safe singleton (`threading.Lock` + double-checked locking) to `get_embedder()`, `get_reward_engine()`, `get_growth_tracker()`, `get_reflection_module()`
- [x] **LOW**: Fixed `context_manager.py` mutating caller's message dicts — added defensive shallow-copy
- [x] **LOW**: Fixed TOCTOU race in `hook_manager.py` — moved `_sync_tool_to_registry()` inside lock
- [x] **LOW**: Changed `_apply_decay()` from silent `except Exception: pass` to warning with traceback

---

## Pending / Future Work

### Performance & Reliability

- [ ] Web search integration (Brave/DuckDuckGo auto-fallback)
- [ ] Streaming VEX code preview animation (Cursor Apply-style character-by-character)
- [ ] AuroraBar streaming animation during AI generation
- [ ] Update notification banner (check GitHub Releases)

### Plan Mode Enhancements

- [ ] Three-phase workflow: Research → Clarify → Plan with DAG
- [ ] Plan revision controls before confirmation
- [ ] DAG cycle detection and execution order computation
- [ ] Auto-resume mechanism for premature AI termination

### Memory Enhancements

- [ ] Memory Manager UI (browse, edit, delete, export memories)
- [ ] LLM-powered deep reflection for generating semantic rules
- [ ] Memory search tool for the agent (`search_memory`, `store_note`)

### Plugin Enhancements

- [ ] Plugin Manager UI (enable/disable/reload, per-tool toggles)
- [ ] Decorator API (`@hook`, `@tool`, `@ui_button`) for declarative plugin development
- [ ] Plugin settings UI with auto-generated forms from schema

### Token Optimization

- [ ] tiktoken integration for accurate token counting
- [ ] Per-round token budget tracking
- [ ] Multimodal token estimation (image cost)
- [ ] Cumulative cost display per conversation
- [ ] Provider usage data integration

### Additional HOM Tools

- [ ] `create_wrangle_node` — create Wrangle node with VEX code (point/prim/vertex/volume/detail)
- [ ] `create_nodes_batch` — batch-create nodes with automatic connections
- [ ] `create_network_box` — grouping with semantic color presets
- [ ] `add_nodes_to_box` — add nodes to existing NetworkBox
- [ ] `list_network_boxes` — list all NetworkBoxes with contents
- [ ] `perf_start_profile` / `perf_stop_and_report` — Houdini perfMon profiling
- [ ] `search_node_types` — keyword search for node types
- [ ] `semantic_search_nodes` — natural-language node search
- [ ] `get_node_inputs` — input port info with pre-cached data

### UI Polish

- [ ] User message collapse (> 2 lines auto-fold)
- [ ] Copy button on AI responses
- [ ] Per-message resend/retry
- [ ] Font scaling (`Ctrl+=`/`Ctrl+-`)
- [ ] Input glow animation during AI generation
- [ ] Thinking section default expanded
- [ ] Update notification banner

### Packaging & Release

- [ ] Release packaging script
- [ ] Semantic `VERSION` tracking
- [ ] Changelog workflow
- [ ] Screenshot/demo assets for GitHub releases
- [ ] Optional one-click updater (check GitHub Releases, preserve user data)

---

## Architecture Notes

### Dependency Order

```
P0.3 ToolRegistry ──→ P1.1 Houdini tools ──→ P1.2 ActionRunner
       │                         │
       └──→ P0.1 OpenAI compat ──→ P0.2 Agent Loop ──→ P2.3 Plan upgrade
                                        │
                                        ├──→ P1.3 Context Manager
                                        ├──→ P1.4 Thread Dispatch
                                        └──→ P4.2 Memory System

P0.3 ToolRegistry ──→ P3.1 Skills ──→ P4.1 Plugin System ──→ P4.3 Rules
P0.1 OpenAI compat ──→ Token Optimization
```

### Key Files Summary

| File | Status | Notes |
|------|--------|-------|
| `core/openai_compat.py` | ✅ Done | Streaming SSE + FC request/response |
| `core/agent_loop.py` | ✅ Done | Multi-turn Function Calling loop |
| `core/tool_registry.py` | ✅ Done | Full schema + tags + modes + thread-safe |
| `adapters/houdini.py` | ✅ Done | 30+ HOM methods |
| `adapters/mock_houdini.py` | ✅ Done | In sync with houdini.py |
| `core/action_runner.py` | ✅ Done | FC dispatch + validation |
| `core/context_manager.py` | ✅ Done | Round trimming + smart compression |
| `core/thread_dispatch.py` | ✅ Done | Main-thread safety |
| `core/session.py` | ✅ Done | Slim orchestration + Qt signals |
| `core/plan_store.py` | ✅ Done | Structured plan + step tracking |
| `core/doc_rag.py` | ✅ Done | Local documentation RAG |
| `core/i18n.py` | ✅ Done | Bilingual translation |
| `core/memory_store.py` | ✅ Done | Three-layer SQLite memory |
| `core/embedding.py` | ✅ Done | Local text embedding |
| `core/reward_engine.py` | ✅ Done | Reward scoring |
| `core/reflection.py` | ✅ Done | Rule-based + LLM reflection |
| `core/growth_tracker.py` | ✅ Done | Growth metrics |
| `core/rules_manager.py` | ✅ Done | User rules (file + UI) |
| `core/hooks/` | ✅ Done | Plugin hook system (3 files) |
| `core/skills/` | ✅ Done | 9 analysis scripts |
| `ui/widgets/` | ✅ Done | 5 UI widgets |
| `tests/` | ✅ Done | 14 test modules, 370 tests passing |
