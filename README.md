# Houdini AI Agent

Houdini AI Agent is a Houdini-native PySide panel plugin focused on keeping AI-assisted scene work inside Houdini. The current milestone delivers a polished front-end workspace with multi-session chat, image attachments, project-aware autosave, a lightweight Houdini adapter for reading scene context, and first-pass support for OpenAI-compatible live model calls.

## Highlights

- Houdini 21.0 Python Panel integration
- Multi-session chat with rename, search, import, export, and delete
- Per-session autosave under `$HIP/Agent`
- Image paste and attachment workflow, including session import/export
- Scene context panel for HIP, network, selection, viewport, and errors
- Mock-safe workflow plus OpenAI-compatible live text/image chat
- Focus mode and collapsible sidebars for a more concentrated workspace

## Repository Layout

- `packages/houdini_ai_agent.json` - Houdini package entry for this workspace
- `houdini/python3.11libs/houdini_ai_agent` - plugin source package
- `houdini/python_panels/houdini_ai_agent.pypanel` - Python Panel registration
- `houdini/toolbar/houdini_ai_agent.shelf` - shelf tools for opening the panel
- `docs/README.en.md` - English usage guide
- `docs/README.zh-CN.md` - 中文使用说明
- `TODO.md` - current roadmap and next milestones

## Quick Start

1. Make sure Houdini 21.0 can see the package file in `packages/houdini_ai_agent.json`.
2. Restart Houdini.
3. Open `Windows > New Pane Tab Type > Python Panel > Houdini AI Agent`, or use the `Houdini AI` shelf.

## Documentation

- [English Guide](E:/Work/Houdini/AI_Agent/docs/README.en.md)
- [中文说明](E:/Work/Houdini/AI_Agent/docs/README.zh-CN.md)
- [TODO](E:/Work/Houdini/AI_Agent/TODO.md)

## Current Status

This repository is currently front-end first:

- The UI, session system, image workflow, and Houdini package integration are in place.
- The panel can read basic Houdini scene context when opened inside Houdini.
- OpenAI-compatible providers can now answer chat requests and selected analysis actions.
- Real node execution orchestration and automatic repair are still planned for the next milestone.
