# Houdini AI Agent - English Guide

## Overview

Houdini AI Agent is a Houdini 21 Python Panel plugin built with PySide. It is designed to keep AI-assisted scene analysis, node work, image-aware prompting, mode-aware planning, and repair automation inside Houdini instead of splitting work across multiple apps.

Local package note: the checked-in package file currently points `HOUDINI_AI_AGENT_ROOT` at `D:/Project/Houdini/Houdini-AI-Agent`. If you install the repository elsewhere, update `packages/houdini_ai_agent.json` or place an adjusted copy in your Houdini packages directory.

## Current Feature Set

### Workspace and Sessions

- Native Houdini Python Panel
- Multiple conversations with:
  - create
  - rename
  - search/filter
  - import
  - export
  - delete
- Per-conversation autosave under `$HIP/Agent/sessions`
- Conversation-local images under `$HIP/Agent/images/<conversation_id>/`
- Pending image preview and image double-click preview
- Single-message deletion
- Confirmed clear-all for a conversation

### AI Provider Layer

- `Codex Local`
  - reuses the local Codex CLI login on the same machine
  - no manual OpenAI API key entry required
- Custom OpenAI-compatible providers
  - direct API key field or environment variable name
  - configurable default model
  - configurable default thinking level
  - configurable vision capability
  - configurable vision fallback role
- `Mock Preview`
  - safe offline UI/testing mode
- Separate vision backend routing
  - the main chat model can stay text-only
  - image understanding can come from another provider or optional `Codex Local`
  - future `MCP` and `Skill` modes already have reserved config entries in Settings
- Last selected provider, model, thinking level, and work mode are persisted in the app config.

### Work Modes and Tool Policy

- `Ask`
  - read-only answers, scene analysis, selection inspection, and viewport capture
  - mutating toolbar actions and model actions are blocked in code
- `Agent`
  - normal execution mode for supported scene edits
  - currently allows node creation and supported code-parameter repair
- `Plan`
  - asks the model for a structured plan first
  - renders the plan as an in-chat card with confirm / cancel controls
  - confirmation switches to Agent mode and executes steps sequentially
- `ToolRegistry`
  - centralizes the current action schemas
  - filters tools by mode for prompts, toolbar buttons, and model-planned actions
  - is intentionally small in this pass so the existing action set is guarded before adding broader HOM coverage

### Houdini Context and Actions

- Reads:
  - HIP path
  - current network
  - selected nodes
  - viewport summary
  - network error/warning summary
- Model-planned execution can currently trigger:
  - `analyze_scene`
  - `inspect_selection`
  - `capture_viewport`
  - `create_node`
  - `apply_code`
- Failed model-planned tool calls can trigger a bounded self-repair prompt, allowing the model to diagnose the failed HOM action and return a corrected action before giving up.

### UI and Workflow Polish

- High-DPI-aware dimensions and stylesheet values with optional `HOUDINI_AI_AGENT_UI_SCALE` override
- Mode picker beside provider / model / thinking controls
- Plan cards with ordered steps, dependency notes, risks, confirm, and cancel controls
- Enter sends chat messages; `Alt+Enter` inserts a newline
- Defensive display / render flag setting during node creation so unsupported node classes do not abort the whole action

### Vision Companion Flow

Some models are text-only. To avoid losing screenshot support:

- if the selected main model supports vision, attached images go straight to that model
- if the selected main model does **not** support vision, the plugin resolves a separate vision backend
- that backend summarizes the image(s)
- the image summary is injected into the main model prompt

This keeps the interaction model simple:

- one main thinking model
- one optional image-reading companion

Recent reliability improvements:

- `Codex Local` is optional and no longer implied as the default fallback
- when the active provider is `Codex Local`, images are sent directly to Codex Local even in `Auto` vision mode
- model-aware checks treat `glm-5.1` and similar text-only models as unable to read images, even when older saved settings contain a stale vision flag
- if a provider answers as if no image arrived, the plugin can retry through the resolved vision backend
- the collapsible thought block is now concise rather than exposing raw planning JSON

## Recommended Public Vision MCP References

We researched public GitHub projects that are good references for stronger future vision backends:

1. [ColeMurray/moondream-mcp](https://github.com/ColeMurray/moondream-mcp)
   - FastMCP server for Moondream
   - captioning, VQA, object detection, visual pointing, batch analysis
2. [mrgoonie/human-mcp](https://github.com/mrgoonie/human-mcp)
   - large multimodal MCP toolkit
   - includes `eyes_analyze` and `eyes_compare`
   - strong reference for screenshot-debugging workflows
3. [aliargun/mcp-server-gemini](https://github.com/aliargun/mcp-server-gemini)
   - Gemini MCP with vision support
   - GitHub search result currently shows `240 stars`

The plugin does **not** hard-bind to one of these yet. Instead, it now ships an internal vision-backend layer so the panel remains simple and provider-agnostic.

## Reference Comparison: Houdini-Agent

We also reviewed [Kazama-Suichiku/Houdini-Agent](https://github.com/Kazama-Suichiku/Houdini-Agent) as a product reference. The most useful ideas for our current plugin were:

- clickable node paths in chat
- stronger visual/tool-oriented UI treatment
- clearer capability handling around multimodal models

The reference implementation keeps image input tied to the selected model. It uses a model feature registry to mark models such as `glm-5.1` as non-vision, builds OpenAI-style multimodal `text + image_url` content only when the selected model supports vision, strips older base64 image payloads from history, and injects viewport screenshots only for vision-capable models. This plugin follows that primary-model-first principle, then adds an optional companion backend for text-only main models.

What we adopted in this milestone:

- first-pass Ask / Agent / Plan mode separation
- a small `ToolRegistry` with mode-based action filtering
- confirmable Plan cards and sequential Agent execution after confirmation
- clickable Houdini node paths that focus the node in the network editor
- drag-and-drop image input
- explicit provider-level vision and vision-fallback flags
- direct Codex Local image routing when Codex Local is the active provider

What remains on our roadmap:

- persistent Plan state, plan revision controls, and execution DAGs
- todo task cards for multi-step runs
- broader HOM tool coverage
- richer plugin and rule management surfaces

## Installation

### Option 1 - Package in this repository

This repository already includes:

- `packages/houdini_ai_agent.json`

Point Houdini to that package file, or copy it into your Houdini packages directory and update the path if needed.

### Option 2 - User package directory

Copy or link the package file into your Houdini packages directory, for example:

`C:\Users\<YourUser>\Documents\houdini21.0\packages\`

Then restart Houdini.

## Opening the Panel

After restarting Houdini:

1. Open `Windows > New Pane Tab Type > Python Panel`
2. Choose `Houdini AI Agent`

You can also use the included `Houdini AI` shelf.

## Recommended Validation Inside Houdini

1. Open the panel and confirm the context panel updates.
2. Switch to `Ask` mode and confirm mutating toolbar buttons are disabled while analysis / selection / viewport tools remain available.
3. Switch to `Agent` mode, select a node, and click `查看选中节点`.
4. Ask the agent to create a node such as `Create a box`.
5. Switch to `Plan` mode, request a small multi-step scene change, and confirm that a plan card appears before execution.
6. Confirm the plan and verify that the panel switches to `Agent` mode and executes the steps sequentially.
7. Capture the viewport and confirm the image appears in chat.
8. Paste an image with `Ctrl+V`.
9. Configure:
   - a text-first main model such as `glm-5.1`
   - a separate multimodal vision backend, or `Codex Local` if you want to use it
   - keep `glm-5.1` out of the vision backend target list because it is a text model
10. Send an image plus a question and confirm:
   - the request stays responsive
   - the image is still understood even though the main model is text-only

## Session Storage

When the current HIP file is saved:

- session index: `$HIP/Agent/session_index.json`
- conversations: `$HIP/Agent/sessions/<conversation_id>.json`
- images: `$HIP/Agent/images/<conversation_id>/`

If the HIP file is still unsaved, the panel remains usable, but project-local autosave waits until the HIP exists on disk.

## Current Limits

- The vision fallback currently uses a second provider, not a bundled local Moondream runtime yet.
- Tool execution is still intentionally small and guarded by the first-pass registry.
- Plan cards are session-local runtime objects for now; persistent plan state and revision controls are still on the roadmap.
- Repair flows can retry failed tool calls, but they still focus on code-parameter replacement and validation rather than full graph-wide planning.

## Next Steps

See [TODO](../TODO.md).
