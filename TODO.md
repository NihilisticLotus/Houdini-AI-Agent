# TODO

This roadmap folds in the strongest ideas found while comparing this project with
`Kazama-Suichiku/Houdini-Agent`. The goal is not to copy that plugin wholesale,
but to absorb the durable product and engineering patterns that fit this codebase:
mode-based safety, a real tool registry, multi-turn tool execution, structured
plans, richer Houdini operations, better documentation retrieval, and a stronger
tool-surface UI.

## Reference Audit 2026-05-12

Source reviewed: `https://github.com/Kazama-Suichiku/Houdini-Agent`.

The reference project is valuable less because every feature should be copied,
and more because it has clearer product boundaries:

- it treats the agent loop, tool registry, plan manager, plugin hooks, rules,
  memory, and Houdini tool layer as separate subsystems instead of one large
  chat/session object
- it exposes provider-native Function Calling schemas and keeps fenced JSON only
  as a compatibility fallback
- it separates `ask`, `agent`, `plan_planning`, and `plan_executing` policies,
  which is stricter than the current three-mode model
- it has a much broader Houdini operation surface: node graph queries, node
  creation, connection, deletion, parameter edits, layout, NetworkBoxes,
  performance profiling, documentation lookup, shell/Python execution, and
  reusable skills
- it has concrete context-size controls: tool-result compression, doc/web
  caching, and image-payload stripping for older turns
- it has stronger extension seams through plugin hooks, user rules, tool
  toggles, and skill registration

The parts to absorb first are the architectural contracts, not the full feature
count: native tool-call flow, strict mode-state policy, durable plan state,
uniform tool result objects, local Houdini documentation retrieval, and a
minimal plugin/rules path after the registry is stable.

## Current Project Gaps Found In This Audit

- Text encoding and localization are not rigorous enough
  - several UI/test strings currently appear as mojibake in source output
  - fix encoding before adding more bilingual UI, otherwise tests will freeze
    corrupted text as expected behavior
  - add a small encoding smoke test that scans Python, Markdown, and QSS files
    for replacement characters and common mojibake markers
- `AgentSession` is carrying too many responsibilities
  - model calls, action parsing, plan normalization, plan execution, todo state,
    image routing, session storage, and repair prompting all live in one class
  - split out `ActionRunner`, `PlanStore`, `ConversationStore`, and
    `VisionRouter` before the next large feature lands
- Tool calling is still ad hoc
  - `openai_compat.py` can read `tool_calls`, but requests do not yet send
    provider-native `tools` schemas or feed structured tool results back through
    the provider protocol
  - current fenced-JSON parsing should become fallback only
  - every action needs schema validation before execution, not only loose
    `dict.get()` extraction
- Plan mode is only half strict
  - `Plan` currently means both "draft a plan" and "plan exists", while the
    reference separates planning and executing policy states
  - confirmed execution should carry a frozen plan snapshot, approved tool list,
    dependency ordering, and per-step result contract
  - plan execution should support revise/regenerate and explicit blocked-state
    recovery, not only sequential auto-continue
- HOM mutation safety needs a stronger contract
  - all mutating tools should return `success`, `message`, `created_paths`,
    `changed_paths`, `warnings`, `errors`, and optional `undo_label`
  - broad or destructive tools need confirmation gates and before/after
    summaries
  - parameter edits need scalar/tuple/expression handling plus "unchanged"
    detection before creating undo noise
- Main-thread boundaries are implicit
  - classify every tool as Houdini-main-thread, background-safe, or external
    process
  - dispatch HOM mutations through one main-thread executor and keep doc/web
    lookups off the UI thread
- Context management is too shallow for long runs
  - add round-based trimming that preserves user/assistant intent and compresses
    old tool outputs
  - strip or summarize old image payloads before sending future turns
  - paginate long node-parameter, docs, shell, Python, and profiling results
- Houdini coverage is narrow compared with the reference
  - current executable surface is mostly analyze/inspect/capture/create/set/apply
  - prioritize connect/delete/copy/layout/network summary/check errors before
    higher-risk shell or Python execution
- Extensibility should wait for contracts
  - do not add plugin hooks until tool schemas, mode guards, result objects, and
    config persistence are stable
  - when added, plugins should register tools through the same registry and be
    removable without leaving stale disabled-tool config

## Completed in This Pass

- Added a first-pass `ToolRegistry`
  - centralizes the current action schemas for `analyze_scene`, `inspect_selection`, `capture_viewport`, `create_node`, `set_parm`, and `apply_code`
  - exposes mode-aware tool filtering for prompts, toolbar actions, and model-planned actions
  - maps toolbar aliases such as `create_nodes` and `fix_error` to their underlying tools
- Added visible `Ask / Agent / Plan` work modes
  - persisted work mode in app config
  - disabled or blocked mutating tools in `Ask` and `Plan`
  - kept supported scene edits available in `Agent`
- Added first-pass Plan cards
  - model responses in Plan mode can normalize into structured plans
  - chat renders plan steps, risks, and confirm / cancel controls
  - confirming a plan switches to Agent mode and executes steps sequentially
- Added bounded tool self-repair
  - failed model-planned tool actions can queue a follow-up diagnosis prompt
  - retry count is capped to prevent endless repair loops
- Added runtime selection persistence
  - provider, model, thinking level, and work mode are restored across panel sessions
- Added DPI-aware UI scaling
  - core panel, chat, settings, context panel, and stylesheet dimensions now use shared scaling helpers
  - `HOUDINI_AI_AGENT_UI_SCALE` can override automatic detection
- Compact Houdini panel chrome and conversation navigation
  - removed the left conversation sidebar in favor of a compact tab strip above the chat transcript
  - reduced tab height, tab width, and tab font size for smaller Houdini panes
  - moved the scene-context fold handle onto the splitter boundary between the chat workspace and right context panel
  - kept the fold handle reachable after the context panel is collapsed
  - hide Houdini's Python Panel host toolbar through `hou.PythonPanel.showToolbar(False)` when available
- Improved chat and HOM execution ergonomics
  - `Enter` sends; `Alt+Enter` inserts a newline
  - plan messages have a dedicated role and card UI
  - node display/render flags are applied defensively so unsupported flags do not fail the whole creation action
  - added a first narrow parameter-write path through `set_parm` on explicit node path + parm name targets
- Hardened plan and task state
  - active plans are now stored per conversation and restored from autosave/imported session JSON
  - plan cards refresh as steps move through in-progress, completed, blocked, paused, cancelled, and completed states
  - added internal `add_todo` / `update_todo` task tools with compact todo chips above the transcript
  - added core regression tests for mode guards, plan persistence, and todo persistence
  - added a narrow non-UI Qt fallback so core smoke tests can run outside Houdini when PySide is unavailable
- Started the priority cleanup from the reference audit
  - added a UTF-8 / mojibake smoke test for repository text files
  - verified the visible PowerShell mojibake is an output-display issue rather
    than wholesale UTF-8 corruption in the files
  - extracted vision backend selection into `VisionRouter`
  - added focused tests for direct vision routing, text-only model guards,
    non-Codex Auto companion routing, and unready provider status messages
  - extracted model-requested action dispatch into `ActionRunner`
  - introduced a first-pass normalized `ToolResult` shape with `success`,
    `events`, `created_paths`, `changed_paths`, `warnings`, and `errors`
  - added action-runner tests for legacy adapter result normalization, error
    detection, missing adapter methods, parameter-write validation, and todo dispatch
  - extracted plan shaping and in-memory state rules into `PlanStore`
  - added plan-store tests for plan normalization, text step extraction,
    interrupted-execution recovery, plan-message syncing, and pending-plan
    rebuilding
  - improved plan title fallback so description-only steps render with useful
    labels instead of generic `Step N`
  - added pre-dispatch action validation so malformed model actions do not call
    adapter / HOM methods
  - added `scripts/validate.py` as the one-command local validation entry point:
    compile plugin code, run smoke import, and run unit-test discovery
  - documented the local validation command in the README and English guide

## Next Priority

- Clean up source encoding and localization debt
  - keep the new encoding smoke test green
  - normalize line endings and editor settings so UTF-8 text is not misread by
    Windows shells or contributors' editors
  - centralize user-facing Chinese / English strings instead of scattering mixed
    literals through session and adapter code
- Extract session responsibilities before adding another major workflow
  - continue shrinking model action parsing now that execution is in
    `ActionRunner`
  - continue moving plan execution state transitions into `PlanStore`; plan
    shaping and storage helpers are already extracted
  - move conversation file IO and image materialization into a `ConversationStore`
  - continue shrinking the new `VisionRouter` seam as provider capability probes
    and MCP / Skill vision modes are implemented
  - keep `AgentSession` as orchestration and Qt signal glue
- Harden the new mode and plan workflow
  - add revise / regenerate controls before confirmation
  - show richer execution progress directly on the plan card, including elapsed timing and tool result summaries
  - add explicit `plan_planning` and `plan_executing` policy states if the current three-mode model becomes too coarse
  - freeze approved plan data before execution so later model replies cannot
    silently rewrite the plan
  - validate `depends_on` and block cycles before execution starts
  - add regression tests proving Ask and Plan cannot mutate the Houdini scene
- Extend `ToolRegistry` beyond the first-pass wrapper
  - add richer tags such as `readonly`, `network`, `geometry`, `system`, `docs`, `vision`, `task`, and `dangerous`
  - persist per-tool enabled / disabled state in the plugin config
  - expose tool metadata for settings UI, prompt summaries, trace cards, and future plugin tools
  - build schema validation on top of the new `ActionRunner` / `ToolResult`
    seam before registering many more HOM tools
  - promote the current `ActionRunner` field checks into registry-owned schema
    validation once tool schemas become formal JSON Schema
  - classify tools by execution boundary: `houdini_main_thread`,
    `background_safe`, `external_process`
  - add intent-aware tool subsets only after the registry has tests
- Replace the current one-shot action JSON flow with a bounded multi-turn tool loop
  - support provider-native OpenAI-compatible Function Calling when available
  - keep the existing fenced-JSON action parser as fallback for models without Function Calling
  - continue after tool results until the task is complete or a tool / iteration limit is reached
  - preserve cancellation, UI responsiveness, and the existing background worker model
  - add duplicate readonly-tool-call suppression to prevent loops
  - record every tool call / result pair as a compact trace that can be
    replayed in tests
- Build the next Houdini tool slice conservatively
  - add `connect_nodes`, `delete_node`, `copy_node`, `layout_nodes`,
    `check_errors`, and `get_network_structure` before shell/Python tools
  - wrap each mutation in an undo group and return created/changed paths
  - broaden the current `set_parm` path to handle tuples, expressions, and
    unchanged-value detection before adding batch parameter edits
  - add mock-adapter parity tests for every new tool before wiring it into the
    model prompt
- Extend lightweight todo cards for multi-step runs
  - add direct user controls for clearing or archiving todos per conversation
  - add optional completed-task history expansion
- Make repair planning multi-step
  - inspect
  - propose
  - execute
  - validate
  - retry when safe
  - stop with a clear blocker instead of repeating the same failed edit
  - include structured failure categories so the bounded self-repair prompt knows whether to retry, ask, or stop

## Reference Plugin Advantages To Absorb

- Tool architecture
  - extend the current `ToolRegistry` so core tools, future skills, and future plugin tools share one schema and one access-control path
  - refine mode-specific tool filtering for `agent`, `ask`, `plan_planning`, and `plan_executing`
  - add tool metadata for UI lists, tool disabling, and safer prompts
  - add intent-aware tool subsets later, but only after the registry is stable
- Agent loop
  - support streaming tool-call progress instead of waiting for one final model response
  - feed compressed tool results back to the model for the next iteration
  - distinguish Houdini main-thread tools from background-safe tools
  - execute readonly independent queries in a batch where possible
  - add maximum iterations, maximum tool calls, and same-call loop guards
- Plan mode
  - promote the current inline plan response handling into explicit `create_plan`, `update_plan_step`, and `ask_question` tools
  - store one active plan per conversation under the session storage directory
  - show plan phases, steps, dependencies, expected results, risks, and fallback notes
  - include a DAG / flow representation for step dependencies
  - add user approve / reject / revise controls before mutating execution
  - add auto-resume detection when a plan has pending steps but the model tries to finish early
- Safety and reversibility
  - add a confirmation gate for destructive or broad tools such as delete, batch set, shell, Python execution, and save
  - add undo snapshots for every mutating HOM operation, not only the current create / fix paths
  - add `Undo All` / `Keep All` style batch operation controls for multi-step execution
  - add before / after network snapshots so Python, skill, and copy tools can still produce undo checkpoints
  - add parameter diff previews for scalar, tuple, expression, and multiline VEX changes
  - skip undo snapshots when a parameter value is unchanged
- Context and token management
  - add round-based context trimming that preserves user / assistant intent while compressing tool results
  - strip older base64 image payloads from conversation history and keep images only for the current vision round
  - paginate long tool results such as node parameters, docs, shell output, Python output, and performance reports
  - cache repeated documentation and web lookups per session
  - estimate image token cost and show warnings when attached images make the request too large
- Documentation and knowledge retrieval
  - add a lightweight local Houdini doc index inspired by the reference `Doc` / `doc_rag.py` flow
  - index node docs, VEX functions, HOM classes / methods, and project-bundled knowledge snippets
  - add `search_local_doc` and `get_houdini_node_doc` tools before broad web search
  - add scene-aware retrieval that uses selected node types and current errors to enrich doc queries
  - add a small SideFX Labs / HeightField / COP / MPM knowledge path only if the repository can package it cleanly
- Extensibility
  - add a minimal plugin hook system after ToolRegistry lands
  - support hook events for before / after model request, before / after tool execution, content chunk, conversation start, and conversation end
  - allow plugins to register tools, buttons, and settings through a narrow API
  - add a Plugin Manager UI with enable / disable / reload and per-tool toggles
  - add a user skill directory for reliable local analysis scripts
- User rules and memory
  - add Cursor-style persistent user rules
  - support both UI-managed rules and file rules from a `rules/` directory
  - inject enabled rules into the system prompt with a clearly delimited block
  - add a small memory store only after the agent loop and tool logging are stable
  - start with searchable semantic notes and explicit user approval before automatic learning
- UI polish
  - add a richer progress log with collapsible thinking, tool calls, tool results, and elapsed timing
  - add copy buttons on assistant replies
  - add per-message resend / retry
  - add compact token / cost / model usage chips when provider usage data is available
  - add font scaling controls and persist the setting
  - add a persisted compact-layout preference after the current manual chrome reductions settle
  - add better IME handling for PySide2 / PySide6, especially CJK input on Windows and macOS
  - add `@node` mention autocomplete from the current network
  - add a streaming VEX / Python code preview before applying generated code
  - add embedded Python Shell and System Shell result widgets only if they stay compact inside Houdini

## Houdini Tool Coverage

- Expand tool action coverage
  - `create_wrangle_node` with explicit VEX code and run-over mapping
  - `create_nodes_batch` with optional automatic connections
  - connect nodes
  - delete nodes
  - copy / duplicate nodes
  - layout nodes
  - set parameters
  - batch set parameters
  - create subnet / geometry containers with intent-aware defaults
  - toggle display / render flags
  - save HIP
  - undo / redo
  - read network structure with connection input labels
  - list children with flags
  - get detailed node parameters, status, flags, errors, inputs, and outputs
  - search nodes by parameter value
  - get node input-port info from a cache of common nodes
  - verify and summarize the network after edits
  - create / add / list NetworkBoxes
  - get node positions for layout verification
  - performance profiling through `hou.perfMon` plus a fast cook-time analysis skill
  - run bounded Houdini Python snippets with timeout and stop support
  - optionally run bounded system shell commands with timeout and explicit safety warnings
- Add NetworkBox-aware scene summaries
  - fold large networks by NetworkBox name, comment, node count, and top node types
  - allow drilling into a specific NetworkBox for detailed node and connection data
  - show cross-box connections separately
- Add automatic layout workflows
  - strategies: `auto`, `grid`, `columns`
  - recommended sequence: create nodes, connect, verify, layout, then group into NetworkBoxes
- Add precise node-path handling
  - collect node path maps from tool results
  - auto-resolve unique bare node names such as `box1` into full paths in replies
  - avoid rewriting paths inside code blocks

## Vision and Multimodal

- Add a bundled local vision backend option inspired by `moondream-mcp`, so image fallback can run without a remote API
- Extend the new vision-backend abstraction beyond provider/Codex routing
  - `MCP` vision backend execution
  - `Skill` vision backend execution
  - backend capability discovery and health checks
- Support explicit provider capability presets for
  - text-only
  - text + vision
  - vision-only companion
- Add a provider capability registry seeded with known model families
  - `glm-5.1` / `glm-5-turbo` as text-only
  - GPT / Claude / Gemini vision-capable families
  - user overrides with a visible warning when the model name conflicts with the selected capability
- Add UI tests for the intended routing matrix
  - active `Codex Local` + image uses Codex directly
  - active `glm-5.1` + Auto never invokes Codex implicitly
  - active `glm-5.1` + explicit Codex vision backend uses Codex as companion
- Add automatic provider capability probes so the plugin can verify whether a model really accepts images instead of relying only on manual flags
- Add image understanding cache per conversation so repeated screenshots do not re-spend tokens unnecessarily
- Add OCR-focused fallback mode for screenshots dominated by text or error logs
- Add current-round-only image payload handling inspired by `Houdini-Agent`
  - keep attached image data only in the newest user turn sent to a vision model
  - replace older image payloads with plain text references / summaries
  - warn when a non-vision provider is selected and no explicit companion backend is available
- Add viewport capture options
  - resolution presets up to 1920x1080
  - save-to-file for text-only models
  - base64 return only when a vision-capable backend will actually consume it
- Evaluate direct integration patterns inspired by
  - `ColeMurray/moondream-mcp`
  - `mrgoonie/human-mcp`
  - `aliargun/mcp-server-gemini`

## Houdini Execution

- Expose richer HOM actions through the model-planning layer
- Add safe parameter diff preview before destructive edits
- Add undo-group snapshots for every tool execution
- Add structured node graph summaries for large scenes
- Add viewport object picking / selection grounding when screenshots are used
- Add main-thread dispatch boundaries
  - Houdini HOM mutations run on the Qt main thread
  - web, docs, shell, and non-HOM tasks run in background workers
  - avoid `processEvents()` reentrancy during blocking Houdini tool execution
- Add timeout and stop-event protection for long-running Python, shell, and cook operations
- Add cook-deadlock prevention checks before forcing scene evaluation from an agent loop
- Add structured result objects for every tool
  - `success`
  - `message`
  - `created_paths`
  - `changed_paths`
  - `warnings`
  - optional undo snapshot id

## UI and Workflow

- Evolve the current collapsible thought block into a richer Codex-style progress log with step updates and elapsed timing
- Add richer visual chips for
  - current provider
  - current model
  - vision mode
  - active thinking level
- Add collapsible tool result cards with clearer success / warning / error grouping
- Add per-message resend
- Add session pinning / favorites
- Add collapsible execution groups for long repair runs
- Add optional compact mode presets for smaller Houdini layouts
- Add mode switcher near the input area
  - Ask / Agent / Plan segmented control
  - mode-specific color / tooltip / safety hint
- Add plan viewer cards
  - phases
  - step dependency DAG
  - approve / reject / revise buttons
  - live progress updates while executing
- Add tool result cards
  - collapsible details
  - success / warning / error grouping
  - copied command / code snippets
  - clickable node paths
- Add parameter diff widgets
  - red / green scalar diffs
  - collapsed multiline code diffs with preview height
  - one-click undo for a single pending change
- Add code preview widgets for generated VEX / Python
  - show partial streaming code before execution when provider streaming is available
  - replace preview with diff or tool result after execution
- Add node context bar and `@node` autocomplete
  - current selection
  - recent nodes from tool results
  - keyboard navigation: up / down / enter / tab / escape
- Add copy buttons and auto-collapse for long user messages
- Add font scaling and QSS-driven theme tokens instead of scattered inline styling
- Add update notification banner only after release packaging exists

## Reliability

- Add provider compatibility tests for more OpenAI-compatible APIs
- Add request/response fixtures for action-planning JSON validation
- Add telemetry for cancellation, fallback vision use, and provider errors
- Add defensive parsing for providers that return JSON wrapped in prose
- Add Function Calling compatibility matrix
  - OpenAI-compatible native tool calls
  - Anthropic-style tool-use adapters when routed through compatible relays
  - JSON-mode fallback for providers without tool calls
  - provider-specific reasoning / thinking field parsing
- Add robust streaming parser tests
  - content deltas
  - tool call argument deltas
  - reasoning / thinking deltas
  - malformed or concatenated JSON tool arguments
- Add mode-guard tests
  - Ask cannot call mutating tools
  - Plan planning cannot mutate the scene
  - Plan execution can update steps and call approved tools
  - disabled tools are hidden and rejected at execution time
- Add long-output pagination tests for docs, node params, Python, shell, and profiling
- Add undo snapshot restore tests for nested container nodes
- Add CJK / IME regression notes for PySide2 and PySide6
- Add smoke tests for running outside Houdini with the mock adapter and inside Houdini with `hython`

## Packaging

- Add release packaging script
- Add changelog workflow
- Add screenshot / demo asset pipeline for GitHub releases
- Publish a tagged release once the next Houdini validation pass is complete
- Add semantic `VERSION` tracking
- Add an optional one-click updater design
  - check GitHub Releases, not a branch file
  - cache ETags / release metadata
  - preserve user config, session cache, plugins, rules, and training data during update
  - show a lightweight banner instead of interrupting startup
- Add plugin development docs once the plugin hook system exists
- Add training-data export only after the agent loop records stable tool traces
