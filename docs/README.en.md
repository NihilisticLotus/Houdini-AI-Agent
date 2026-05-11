# Houdini AI Agent - English Guide

## Overview

Houdini AI Agent is a Houdini panel plugin built with PySide for Houdini 21.0. The goal is to provide an AI-assisted workspace directly inside Houdini, so scene inspection, node creation, image-aware prompting, and future automatic error repair can all happen without leaving the DCC.

## Current Features

- Native Houdini Python Panel UI
- Multiple conversations with:
  - create
  - rename
  - search/filter
  - import
  - export
  - delete
- Per-conversation storage under `$HIP/Agent/sessions`
- Conversation images copied into `$HIP/Agent/images/<conversation_id>/`
- Clipboard image paste support (`Ctrl+V`) when the clipboard contains an image
- Image preview for pending attachments and message images
- Single-message deletion and clear-all confirmation
- Collapsible conversation sidebar and project-context sidebar
- Focus mode for centering on chat work
- Basic Houdini context reading:
  - HIP path
  - current network
  - selected nodes
  - viewport summary
  - warning/error summary
- First-pass OpenAI-compatible provider support for:
  - live text chat
  - image-aware chat requests
  - live scene-analysis style actions
- Local `Codex Local` provider support:
  - reuses the Codex CLI installed and signed in on the same machine
  - does not require manually entering an OpenAI API key in the plugin

## Installation

### Option 1 - Workspace package

This repository already includes:

- `packages/houdini_ai_agent.json`

Point Houdini to this package file, or copy it into your Houdini packages directory and update the path if needed.

### Option 2 - User package directory

Copy or link the package file to your Houdini user package directory, for example:

`C:\Users\<YourUser>\Documents\houdini21.0\packages\`

Then restart Houdini.

## Opening the Panel

After Houdini restarts:

1. Open `Windows > New Pane Tab Type > Python Panel`
2. Choose `Houdini AI Agent`

You can also use the included shelf tool from the `Houdini AI` shelf.

## Recommended Validation Inside Houdini

To verify the current milestone quickly inside Houdini:

1. Open the panel and confirm the right-side context updates.
2. Select a node and click `查看选中节点` to verify real node path/type/parameter preview.
3. Click `创建节点`:
   - with a node selected, it should create `OUT_AGENT_PREVIEW` after the selection
   - with nothing selected, it should create a fallback preview node/container
4. Click `捕获视口` and confirm that:
   - a screenshot file is written
   - the screenshot appears in the chat area as an attached image
5. Select a node with an obvious typo in a code/snippet parameter and click `修复错误` to test the first-pass auto-fix flow.
6. Select `Codex Local` in the model bar and send a text or image prompt to verify live model replies.
7. If you prefer, you can still configure an OpenAI-compatible provider in Settings as an optional advanced path.

## Session Storage

When the current HIP file has already been saved:

- session index is stored under `$HIP/Agent/session_index.json`
- each conversation is stored individually under `$HIP/Agent/sessions/<conversation_id>.json`
- images are copied under `$HIP/Agent/images/<conversation_id>/`

If the HIP file has not been saved yet, the panel still works, but project-local autosave is deferred until the HIP file exists on disk.

## Import and Export

The panel supports importing and exporting conversations.

- Exported conversations include message content and images
- Imported conversations restore images into the project-local Agent directory when applicable

## What Is Mocked Today

The current build is still front-end first, but it is no longer fully mocked. Today:

- `Mock Preview` remains available as a safe offline mode
- `Codex Local` is now the preferred live-provider path when Codex CLI is installed and signed in
- OpenAI-compatible providers can handle live chat and image-aware prompts
- toolbar actions that would modify Houdini are still preview-only
- automatic node repair logic is not connected yet

## Planned Next Steps

- Provider adapters for real API calls
- Multimodal model support
- Houdini node creation and parameter editing tools
- Error analysis and automatic repair loop
- Better execution audit trail and tool telemetry
