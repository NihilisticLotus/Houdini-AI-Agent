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

The current build is intentionally front-end first. That means:

- chat replies are mock responses
- execution traces are simulated
- real multimodal model calls are not connected yet
- automatic node repair logic is not connected yet

## Planned Next Steps

- Provider adapters for real API calls
- Multimodal model support
- Houdini node creation and parameter editing tools
- Error analysis and automatic repair loop
- Better execution audit trail and tool telemetry

