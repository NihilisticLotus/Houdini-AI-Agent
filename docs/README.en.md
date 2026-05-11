# Houdini AI Agent - English Guide

## Overview

Houdini AI Agent is a Houdini 21 Python Panel plugin built with PySide. It is designed to keep AI-assisted scene analysis, node work, image-aware prompting, and future repair automation inside Houdini instead of splitting work across multiple apps.

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

### Vision Companion Flow

Some models are text-only. To avoid losing screenshot support:

- if the selected main model supports vision, attached images go straight to that model
- if the selected main model does **not** support vision, the plugin looks for the first provider marked as `Vision Fallback`
- that fallback provider summarizes the image(s)
- the image summary is injected into the main model prompt

This keeps the interaction model simple:

- one main thinking model
- one optional image-reading companion

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

The plugin does **not** hard-bind to one of these yet. Instead, it now ships an internal vision-fallback layer so the panel remains simple and provider-agnostic.

## Reference Comparison: Houdini-Agent

We also reviewed [Kazama-Suichiku/Houdini-Agent](https://github.com/Kazama-Suichiku/Houdini-Agent) as a product reference. The most useful ideas for our current plugin were:

- clickable node paths in chat
- stronger visual/tool-oriented UI treatment
- clearer capability handling around multimodal models

What we adopted in this milestone:

- clickable Houdini node paths that focus the node in the network editor
- drag-and-drop image input
- explicit provider-level vision and vision-fallback flags

What remains on our roadmap:

- full Ask / Agent / Plan modes
- todo task cards
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
2. Select a node and click `查看选中节点`.
3. Ask the agent to create a node such as `Create a box`.
4. Capture the viewport and confirm the image appears in chat.
5. Paste an image with `Ctrl+V`.
6. Configure:
   - a text-first main model
   - a second multimodal provider marked as `Vision Fallback`
7. Send an image plus a question and confirm:
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
- Tool execution is still intentionally small and safe.
- Repair flows currently focus on code-parameter replacement and validation, not full graph-wide planning.

## Next Steps

See [TODO](E:/Work/Houdini/AI_Agent/TODO.md).
