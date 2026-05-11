# Houdini AI Agent

Houdini AI Agent is a Houdini-native PySide panel plugin for Houdini 21. It keeps AI-assisted scene work inside Houdini with multi-session chat, project-aware autosave, image attachments, local Codex login reuse, OpenAI-compatible providers, and model-planned Houdini actions.

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
- Model-planned Houdini actions:
  - scene analysis
  - selection inspection
  - viewport capture
  - node creation
  - code-parameter repair application
- Cancellable background requests
- UI language follow for button-triggered actions

## New in This Milestone

- Built-in **vision fallback routing**
  - If the current main model is text-only, attached images are first summarized by a separate provider marked as `Vision Fallback` in Settings.
  - The image summary is then injected into the main model prompt, so text-only models can still work with screenshots and viewport captures.
- Provider capability flags in Settings:
  - `Vision`
  - `Vision Fallback`
- Chat quality improvements inspired by [Kazama-Suichiku/Houdini-Agent](https://github.com/Kazama-Suichiku/Houdini-Agent)
  - clickable Houdini node paths inside replies
  - drag-and-drop image attachment support
  - stronger tool-panel visual styling

## What We Learned From Houdini-Agent

After reviewing [Kazama-Suichiku/Houdini-Agent](https://github.com/Kazama-Suichiku/Houdini-Agent), the strongest ideas were not only about having more tools, but about product shape:

- clearer distinction between read-only analysis and mutating actions
- more explicit model and vision capability handling
- better in-chat affordances such as clickable node paths
- a stronger “tool surface” feel instead of plain chat

We adopted the parts that fit our current architecture cleanly:

- clickable node path navigation
- drag-and-drop image upload
- richer provider capability handling for vision

Still missing compared with that project:

- full Ask / Agent / Plan mode system
- todo task cards and execution DAGs
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

Right now, the plugin ships an internal **Vision Companion** workflow instead of binding itself to one external MCP implementation. That keeps the panel architecture simpler and lets us swap in a local MCP backend later.

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
  - currently treated as text-first, so screenshots should use a vision fallback provider
- OpenAI-compatible providers
  - can use either an environment variable name or a direct key in Settings
  - if the provider supports vision, it can directly consume attached images
  - if it is marked as `Vision Fallback`, it can serve as the image-reading companion for text-only main models

## Documentation

- [English Guide](E:/Work/Houdini/AI_Agent/docs/README.en.md)
- [中文说明](E:/Work/Houdini/AI_Agent/README_CN.md)
- [TODO](E:/Work/Houdini/AI_Agent/TODO.md)
