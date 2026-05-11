# Houdini AI Agent

Houdini AI Agent is a Houdini-native PySide panel plugin for Houdini 21 that keeps AI-assisted scene work inside Houdini. The plugin already supports multi-session chat, project-aware autosave, image attachments, local Codex login reuse, OpenAI-compatible providers, and real Houdini context/tool execution routed through model planning.

## What It Does Today

- Native Houdini Python Panel UI
- Multi-session chat with rename, search, import, export, and delete
- Per-session autosave under `$HIP/Agent`
- Image paste, attachment, preview, import, and export
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
- Refined panel styling for a more polished Houdini-side tool feel

## Recommended Public Vision MCP Projects We Researched

These are not hard dependencies of the plugin, but they are strong public references for future local or hybrid vision backends:

1. [ColeMurray/moondream-mcp](https://github.com/ColeMurray/moondream-mcp)
   - FastMCP server around Moondream
   - image captioning, VQA, object detection, pointing, batch analysis
   - good fit for a local lightweight vision companion
2. [mrgoonie/human-mcp](https://github.com/mrgoonie/human-mcp)
   - broad multimodal MCP toolkit
   - `eyes_analyze`, `eyes_compare`, document reading, and UI-debugging oriented flows
   - useful reference for richer screenshot and UI analysis workflows
3. [aliargun/mcp-server-gemini](https://github.com/aliargun/mcp-server-gemini)
   - Gemini MCP with direct vision support
   - GitHub search result currently shows `240 stars`
   - strong reference if you want a hosted multimodal MCP route

Right now, the plugin ships an internal **Vision Companion** workflow instead of binding itself to one external MCP implementation. That keeps the panel architecture simpler and lets us swap in a local MCP backend later.

## Repository Layout

- `packages/houdini_ai_agent.json` - Houdini package entry
- `houdini/python3.11libs/houdini_ai_agent/` - plugin source package
- `houdini/python_panels/houdini_ai_agent.pypanel` - Python Panel registration
- `houdini/toolbar/houdini_ai_agent.shelf` - shelf tools
- `docs/README.en.md` - English guide
- `docs/README.zh-CN.md` - 中文说明
- `TODO.md` - roadmap

## Quick Start

1. Make sure Houdini can see `packages/houdini_ai_agent.json`.
2. Restart Houdini.
3. Open `Windows > New Pane Tab Type > Python Panel > Houdini AI Agent`, or use the `Houdini AI` shelf.

## Provider Notes

- `Codex Local`
  - reuses the machine's Codex CLI login
  - does not require manually entering an OpenAI API key
  - currently treated as **text-first**, so screenshots should use a vision fallback provider
- OpenAI-compatible providers
  - can use either an environment variable name or a direct key in Settings
  - if the provider supports vision, it can directly consume attached images
  - if it is marked as `Vision Fallback`, it can serve as the image-reading companion for text-only main models

## Documentation

- [English Guide](E:/Work/Houdini/AI_Agent/docs/README.en.md)
- [中文说明](E:/Work/Houdini/AI_Agent/docs/README.zh-CN.md)
- [TODO](E:/Work/Houdini/AI_Agent/TODO.md)
