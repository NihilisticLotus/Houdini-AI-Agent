# TODO

## Next Priority

- Add a bundled local vision backend option inspired by `moondream-mcp`, so image fallback can run without a remote API
- Add explicit `Ask / Agent / Plan` work modes inspired by `Houdini-Agent`
  - `Ask` = read-only
  - `Agent` = normal execution
  - `Plan` = plan first, confirm later
- Expand tool action coverage:
  - connect nodes
  - delete nodes
  - copy / duplicate nodes
  - layout nodes
  - set parameters
  - create subnet / geometry containers with intent-aware defaults
  - toggle display / render flags
- Add lightweight todo cards for multi-step runs
- Make repair planning multi-step:
  - inspect
  - propose
  - execute
  - validate
  - retry when safe

## Vision and Multimodal

- Extend the new vision-backend abstraction beyond provider/Codex routing:
  - `MCP` vision backend execution
  - `Skill` vision backend execution
  - backend capability discovery and health checks
- Support explicit provider capability presets for:
  - text-only
  - text + vision
  - vision-only companion
- Add a provider capability registry seeded with known model families:
  - `glm-5.1` / `glm-5-turbo` as text-only
  - GPT / Claude / Gemini vision-capable families
  - user overrides with a visible warning when the model name conflicts with the selected capability
- Add automatic provider capability probes so the plugin can verify whether a model really accepts images instead of relying only on manual flags
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

- Evolve the current collapsible thought block into a richer Codex-style progress log with step updates and elapsed timing
- Add richer visual chips for:
  - current provider
  - current model
  - vision mode
  - active thinking level
- Add collapsible tool result cards with clearer success / warning / error grouping
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
