# TODO

## Next Priority

- Add a bundled local vision backend option inspired by `moondream-mcp`, so image fallback can run without a remote API
- Expand tool action coverage:
  - connect nodes
  - set parameters
  - create subnet / geometry containers with intent-aware defaults
  - toggle display / render flags
- Make repair planning multi-step:
  - inspect
  - propose
  - execute
  - validate
  - retry when safe

## Vision and Multimodal

- Support explicit provider capability presets for:
  - text-only
  - text + vision
  - vision-only companion
- Add image understanding cache per conversation so repeated screenshots do not re-spend tokens unnecessarily
- Add OCR-focused fallback mode for screenshots dominated by text or error logs
- Evaluate direct integration patterns inspired by:
  - `ColeMurray/moondream-mcp`
  - `mrgoonie/human-mcp`
  - `aliargun/mcp-server-gemini`

## Houdini Execution

- Expose richer HOM actions through the model-planning layer
- Add safe parameter diff preview before destructive edits
- Add undo-group snapshots for every tool execution
- Add structured node graph summaries for large scenes
- Add viewport object picking / selection grounding when screenshots are used

## UI and Workflow

- Add richer visual chips for:
  - current provider
  - current model
  - vision mode
  - active thinking level
- Add per-message resend
- Add session pinning / favorites
- Add collapsible execution groups for long repair runs
- Add optional compact mode for smaller Houdini layouts

## Reliability

- Add provider compatibility tests for more OpenAI-compatible APIs
- Add request/response fixtures for action-planning JSON validation
- Add telemetry for cancellation, fallback vision use, and provider errors
- Add defensive parsing for providers that return JSON wrapped in prose

## Packaging

- Add release packaging script
- Add changelog workflow
- Add screenshot / demo asset pipeline for GitHub releases
- Publish a tagged release once the next Houdini validation pass is complete
