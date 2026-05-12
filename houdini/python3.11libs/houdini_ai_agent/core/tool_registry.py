"""Tool registry and work-mode policy for the Houdini agent."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Dict, FrozenSet, Iterable, List, Mapping, Tuple


WORK_MODE_ASK = "ask"
WORK_MODE_AGENT = "agent"
WORK_MODE_PLAN = "plan"
WORK_MODE_ORDER = (WORK_MODE_ASK, WORK_MODE_AGENT, WORK_MODE_PLAN)
VALID_WORK_MODES = frozenset(WORK_MODE_ORDER)


@dataclass(frozen=True)
class WorkModeMeta:
    key: str
    label: str
    description: str
    prompt_instruction: str


WORK_MODES: Dict[str, WorkModeMeta] = {
    WORK_MODE_ASK: WorkModeMeta(
        key=WORK_MODE_ASK,
        label="Ask",
        description="Read-only answers and inspection tools. Scene-changing tools are blocked.",
        prompt_instruction=(
            "Current mode is Ask. You may use read-only tools for context, but you must not create nodes, "
            "edit parameters, apply code, cook fixes, or otherwise mutate the Houdini scene. If the user asks "
            "for a change, explain what would be done and ask them to switch to Agent mode to execute it."
        ),
    ),
    WORK_MODE_AGENT: WorkModeMeta(
        key=WORK_MODE_AGENT,
        label="Agent",
        description="Tools may inspect the scene and execute supported Houdini changes.",
        prompt_instruction=(
            "Current mode is Agent. You may use the available tools when they directly satisfy the request. "
            "Prefer the smallest safe action and report what actually executed."
        ),
    ),
    WORK_MODE_PLAN: WorkModeMeta(
        key=WORK_MODE_PLAN,
        label="Plan",
        description="Plan first. Read-only tools are allowed; scene-changing tools are blocked.",
        prompt_instruction=(
            "Current mode is Plan. Produce a concrete plan before any scene mutation. You may use read-only "
            "tools for context, but do not return mutating actions. For requested edits, return an empty actions "
            "array with a concise step-by-step plan and the confirmation needed to run it in Agent mode."
        ),
    ),
}


@dataclass(frozen=True)
class ToolMeta:
    name: str
    label: str
    description: str
    schema: Mapping[str, object]
    adapter_method: str = ""
    toolbar_actions: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()
    modes: FrozenSet[str] = field(default_factory=lambda: frozenset({WORK_MODE_AGENT}))


class ToolRegistry:
    """Small registry inspired by Houdini-Agent's mode-aware tool registry."""

    def __init__(self, tools: Iterable[ToolMeta] = ()):
        self._tools: Dict[str, ToolMeta] = {}
        self._toolbar_aliases: Dict[str, str] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: ToolMeta) -> None:
        self._tools[tool.name] = tool
        for action in tool.toolbar_actions:
            self._toolbar_aliases[action] = tool.name

    def normalize_mode(self, mode: str) -> str:
        normalized = (mode or WORK_MODE_AGENT).strip().lower()
        return normalized if normalized in VALID_WORK_MODES else WORK_MODE_AGENT

    def canonical_name(self, tool_or_action: str) -> str:
        key = (tool_or_action or "").strip().lower()
        return self._toolbar_aliases.get(key, key)

    def toolbar_tool_name(self, action: str) -> str:
        return self._toolbar_aliases.get((action or "").strip().lower(), "")

    def get(self, tool_or_action: str) -> ToolMeta | None:
        return self._tools.get(self.canonical_name(tool_or_action))

    def has_tool(self, tool_or_action: str) -> bool:
        return self.get(tool_or_action) is not None

    def is_tool_allowed(self, mode: str, tool_or_action: str) -> bool:
        tool = self.get(tool_or_action)
        if tool is None:
            return False
        return self.normalize_mode(mode) in tool.modes

    def is_toolbar_action_allowed(self, mode: str, action: str) -> bool:
        tool_name = self.toolbar_tool_name(action)
        if not tool_name:
            return True
        return self.is_tool_allowed(mode, tool_name)

    def tools_for_mode(self, mode: str) -> List[ToolMeta]:
        normalized = self.normalize_mode(mode)
        return [tool for tool in self._tools.values() if normalized in tool.modes]

    def action_names_for_mode(self, mode: str) -> List[str]:
        return [tool.name for tool in self.tools_for_mode(mode)]

    def mode_label(self, mode: str) -> str:
        return WORK_MODES[self.normalize_mode(mode)].label

    def mode_description(self, mode: str) -> str:
        return WORK_MODES[self.normalize_mode(mode)].description

    def mode_instruction(self, mode: str) -> str:
        return WORK_MODES[self.normalize_mode(mode)].prompt_instruction

    def tool_label(self, tool_or_action: str) -> str:
        tool = self.get(tool_or_action)
        if tool is None:
            return self.canonical_name(tool_or_action) or tool_or_action
        return tool.label

    def block_reason(self, mode: str, tool_or_action: str) -> str:
        tool_label = self.tool_label(tool_or_action)
        mode_label = self.mode_label(mode)
        return f"{mode_label} mode does not allow {tool_label}. Switch to Agent mode to run scene-changing tools."

    def format_action_schema(self, mode: str, indent: str = "  ") -> str:
        tools = self.tools_for_mode(mode)
        lines = [f'{indent}"actions": [']
        for index, tool in enumerate(tools):
            suffix = "," if index < len(tools) - 1 else ""
            lines.append(f"{indent}  {json.dumps(tool.schema, ensure_ascii=False)}{suffix}")
        lines.append(f"{indent}]")
        return "\n".join(lines)

    def format_tool_summary(self, mode: str) -> str:
        tools = self.tools_for_mode(mode)
        if not tools:
            return "- No executable tools are available in this mode."
        return "\n".join(f"- {tool.name} [{', '.join(tool.tags)}]: {tool.description}" for tool in tools)


def get_default_tool_registry() -> ToolRegistry:
    all_modes = frozenset(WORK_MODE_ORDER)
    task_modes = frozenset(WORK_MODE_ORDER)
    agent_only = frozenset({WORK_MODE_AGENT})
    return ToolRegistry(
        [
            ToolMeta(
                name="analyze_scene",
                label="Analyze Scene",
                description="Read the current scene context and summarize structure, risks, and next steps.",
                schema={"action": "analyze_scene"},
                adapter_method="analyze_scene",
                toolbar_actions=("analyze_scene",),
                tags=("readonly", "context"),
                modes=all_modes,
            ),
            ToolMeta(
                name="inspect_selection",
                label="Inspect Selection",
                description="Read selected node paths, type information, parameters, and diagnostics.",
                schema={"action": "inspect_selection"},
                adapter_method="inspect_selection",
                toolbar_actions=("inspect_selection",),
                tags=("readonly", "selection"),
                modes=all_modes,
            ),
            ToolMeta(
                name="capture_viewport",
                label="Capture Viewport",
                description="Capture or summarize the current Scene Viewer without changing the Houdini scene.",
                schema={"action": "capture_viewport"},
                adapter_method="capture_viewport_preview",
                toolbar_actions=("capture_viewport",),
                tags=("readonly", "vision"),
                modes=all_modes,
            ),
            ToolMeta(
                name="add_todo",
                label="Add Todo",
                description="Add a compact internal progress task for multi-step runs. This changes only the chat UI state.",
                schema={
                    "action": "add_todo",
                    "title": "short task title",
                    "detail": "optional detail",
                    "status": "pending|in_progress|done|error",
                },
                tags=("task", "ui", "readonly_scene"),
                modes=task_modes,
            ),
            ToolMeta(
                name="update_todo",
                label="Update Todo",
                description="Update a compact progress task by id or title. This changes only the chat UI state.",
                schema={
                    "action": "update_todo",
                    "id": "todo id if known",
                    "title": "existing title fallback",
                    "status": "pending|in_progress|done|error",
                    "detail": "optional replacement detail",
                },
                tags=("task", "ui", "readonly_scene"),
                modes=task_modes,
            ),
            ToolMeta(
                name="create_node",
                label="Create Node",
                description="Create a Houdini node in the current or requested network.",
                schema={
                    "action": "create_node",
                    "node_type": "box|grid|sphere|null|attribwrangle|...",
                    "node_name": "",
                    "parent_path": "",
                },
                adapter_method="create_node",
                toolbar_actions=("create_nodes",),
                tags=("write", "node", "geometry"),
                modes=agent_only,
            ),
            ToolMeta(
                name="apply_code",
                label="Apply Code",
                description="Replace an editable code parameter to repair a supported node error.",
                schema={
                    "action": "apply_code",
                    "target_node": "/obj/geo1/attribwrangle1",
                    "code_parm": "snippet",
                    "code": "full replacement code",
                },
                adapter_method="apply_code_to_fix_target",
                toolbar_actions=("fix_error",),
                tags=("write", "code", "dangerous"),
                modes=agent_only,
            ),
            ToolMeta(
                name="set_parm",
                label="Set Parameter",
                description="Set one Houdini parameter on an existing node when the node path and parameter name are explicit.",
                schema={
                    "action": "set_parm",
                    "target_node": "/obj/geo1/box1",
                    "parm": "ty",
                    "value": "number|string|[numbers]",
                },
                adapter_method="set_node_parameter",
                tags=("write", "parameter"),
                modes=agent_only,
            ),
        ]
    )
