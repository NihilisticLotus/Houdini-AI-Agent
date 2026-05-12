# Houdini AI Agent

**[English](README.md)** | **[中文](README_CN.md)**

Houdini AI Agent is a Houdini-native PySide panel plugin for Houdini 21. It keeps AI-assisted scene work inside Houdini with multi-session chat, project-aware autosave, image attachments, optional Codex login reuse, OpenAI-compatible providers, separate vision backend routing, and mode-aware model-planned Houdini actions.

> Local package note: the checked-in package file currently points `HOUDINI_AI_AGENT_ROOT` at `D:/Project/Houdini/Houdini-AI-Agent`. If you install the repository elsewhere, update `packages/houdini_ai_agent.json` or place an adjusted copy in your Houdini packages directory.

## Current Capabilities

- Native Houdini Python Panel UI
- Multi-session chat with rename, search, import, export, and delete
- Per-session autosave under `$HIP/Agent`
- Image paste, drag-drop, attachment, preview, import, and export
- Clickable Houdini node paths inside replies
- Scene context panel for:
  - HIP path
  - current network
  - selected nodes
  - viewport summary
  - warning/error summary
- Live providers:
  - `Codex Local` using the local Codex CLI login on the same machine
  - custom OpenAI-compatible providers
  - `Mock Preview` offline mode
- Ask / Agent / Plan work modes beside the composer:
  - `Ask` keeps tools read-only
  - `Agent` can execute supported Houdini edits
  - `Plan` creates a confirmable plan before scene mutation
- First-pass mode-aware `ToolRegistry` for toolbar and model-planned actions
- Structured plan cards with confirm / cancel controls and sequential Agent execution
- Model-planned Houdini actions:
  - scene analysis
  - selection inspection
  - viewport capture
  - node creation
  - code-parameter repair application
- Cancellable background requests
- UI language follow for button-triggered actions
- Last provider, model, thinking level, and work mode persistence
- High-DPI-aware UI scaling with `HOUDINI_AI_AGENT_UI_SCALE` override

## New in This Milestone

- First-pass **mode and tool policy layer**
  - `ToolRegistry` now centralizes the current action schemas and the mode policy used in prompts, toolbar buttons, and model-requested actions.
  - `Ask` and `Plan` block scene-changing actions such as node creation and code application; `Agent` keeps those actions available.
  - Toolbar buttons now disable or report clearly when the current mode does not allow the mapped tool.
- First-pass **Plan workflow**
  - Plan mode asks the model for a structured plan instead of immediately mutating the Houdini scene.
  - Plans render as chat cards with ordered steps, risk notes, and confirm / cancel buttons.
  - Confirming a plan switches to Agent mode and executes the steps one at a time, with trace messages for each step.
- Execution reliability and UI polish
  - Failed model-planned tool calls can trigger a bounded self-repair follow-up so the model can diagnose the failed action and retry with corrected JSON.
  - Provider, model, thinking level, and work mode are restored across panel sessions.
  - UI dimensions now scale with Houdini / OS DPI, and can be overridden with `HOUDINI_AI_AGENT_UI_SCALE`.
  - The old left session sidebar was removed; conversations now live in a compact tab strip above the chat transcript.
  - The right scene-context panel folds from a slim handle on the splitter between the chat workspace and context panel.
  - The Python Panel host toolbar is hidden on creation through Houdini's `hou.PythonPanel.showToolbar(False)` API to reclaim vertical space.
  - Chat input now sends with `Enter` and inserts a newline with `Alt+Enter`.
  - Houdini display / render flags are set defensively so unsupported node types do not break node creation.
- Built-in **vision backend routing**
  - If the current main model is text-only, attached images can be summarized by a separate vision backend in Settings.
  - The image summary is then injected into the main model prompt, so text-only models can still work with screenshots and viewport captures.
  - `Codex Local` is optional and can act as one vision backend, but the plugin no longer treats it as a required default.
- Provider capability flags in Settings:
  - `Vision`
  - `Auto Fallback`
- Chat quality improvements inspired by [Kazama-Suichiku/Houdini-Agent](https://github.com/Kazama-Suichiku/Houdini-Agent)
  - clickable Houdini node paths inside replies
  - drag-and-drop image attachment support
  - stronger tool-panel visual styling
- Vision routing improvements
  - `Codex Local` is available as an optional vision companion instead of an implied default
  - if the active provider itself is `Codex Local`, attached images are sent directly to Codex Local even while vision mode is `Auto`
  - known text-only models such as `glm-5.1` are blocked from direct image input even if an old config accidentally marked them as vision-capable
  - if a provider replies as if no image was received, the plugin can retry through the resolved vision backend
  - thought display is now concise and collapsible instead of exposing raw planning JSON

## What We Learned From Houdini-Agent

After reviewing [Kazama-Suichiku/Houdini-Agent](https://github.com/Kazama-Suichiku/Houdini-Agent), the strongest ideas were not only about having more tools, but about product shape:

- clearer distinction between read-only analysis and mutating actions
- more explicit model and vision capability handling
- better in-chat affordances such as clickable node paths
- a stronger “tool surface” feel instead of plain chat

Its vision implementation is model-first:

- a model feature registry marks models such as `glm-5.1` as non-vision and GPT / Claude / Gemini families as vision-capable
- the input layer only builds multimodal `text + image_url` content when the current model supports vision
- older image payloads are stripped from conversation history to avoid base64 context bloat
- viewport screenshots are injected only when the active model supports vision

We adopted the parts that fit our current architecture cleanly:

- first-pass Ask / Agent / Plan mode separation
- a central tool registry for current Houdini actions and mode guards
- confirmable Plan cards before mutating execution
- clickable node path navigation
- drag-and-drop image upload
- richer provider capability handling for vision
- primary-provider-first image routing: if the current provider is `Codex Local`, images go directly to Codex Local; otherwise `Auto` only searches non-Codex vision providers

Still missing compared with that project:

- persistent Plan state, plan revision controls, and execution DAGs
- todo task cards for multi-step runs
- plugin manager / rules editor / memory manager
- broader HOM tool coverage such as connect, delete, copy, and layout nodes

## Recommended Public Vision MCP References

These are not hard dependencies of the plugin, but they are strong public references for future local or hybrid vision backends:

1. [ColeMurray/moondream-mcp](https://github.com/ColeMurray/moondream-mcp)
   - FastMCP server around Moondream
   - image captioning, VQA, object detection, pointing, batch analysis
2. [mrgoonie/human-mcp](https://github.com/mrgoonie/human-mcp)
   - broad multimodal MCP toolkit
   - `eyes_analyze`, `eyes_compare`, document reading, and UI-debugging oriented flows
3. [aliargun/mcp-server-gemini](https://github.com/aliargun/mcp-server-gemini)
   - Gemini MCP with direct vision support
   - GitHub search result currently shows about `240 stars`

Right now, the plugin ships an internal **Vision Companion** workflow instead of binding itself to one external MCP implementation. The main chat model and the vision backend are now separate roles, which makes it easier to add MCP or skill-based image understanding later.

## Repository Layout

- `packages/houdini_ai_agent.json` - Houdini package entry
- `houdini/python3.11libs/houdini_ai_agent/` - plugin source package
- `houdini/python_panels/houdini_ai_agent.pypanel` - Python Panel registration
- `houdini/toolbar/houdini_ai_agent.shelf` - shelf tools
- `docs/README.en.md` - English guide
- `README_CN.md` - Chinese guide
- `TODO.md` - roadmap

## Quick Start

1. Make sure Houdini can see `packages/houdini_ai_agent.json`.
2. Restart Houdini.
3. Open `Windows > New Pane Tab Type > Python Panel > Houdini AI Agent`, or use the `Houdini AI` shelf.

## Provider Notes

- `Codex Local`
  - reuses the machine's Codex CLI login
  - does not require manually entering an OpenAI API key
  - can act as an optional vision backend when you want local Codex image understanding
- OpenAI-compatible providers
  - can use either an environment variable name or a direct key in Settings
  - if the provider supports vision, it can directly consume attached images
  - text-only models such as `glm-5.1` should stay as the main chat model only; pair them with a separate multimodal provider when image understanding is needed
- Vision backend
  - can be `Auto`, `Disabled`, a specific provider, or `Codex Local`
  - `Auto` only considers non-Codex providers that pass the model-aware vision check
  - `Codex Local` is used directly when it is the active provider, or as a companion only when explicitly selected as the vision backend
  - future `MCP` and `Skill` modes are reserved in Settings so the config shape is ready for those backends

## Documentation

- [English Guide](docs/README.en.md)
- [中文说明](README_CN.md)
- [TODO](TODO.md)
