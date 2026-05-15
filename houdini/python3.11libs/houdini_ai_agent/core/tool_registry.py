"""Tool registry and work-mode policy for the Houdini agent.

Supports four work modes (ask, agent, plan_planning, plan_executing),
tag-based classification, per-tool enable/disable, JSON Schema definitions,
and OpenAI Function Calling schema export.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Set, Tuple, Union


# ---------------------------------------------------------------------------
# Work modes
# ---------------------------------------------------------------------------

WORK_MODE_ASK = "ask"
WORK_MODE_AGENT = "agent"
WORK_MODE_PLAN = "plan"
WORK_MODE_PLAN_PLANNING = "plan_planning"
WORK_MODE_PLAN_EXECUTING = "plan_executing"

WORK_MODE_ORDER = (WORK_MODE_ASK, WORK_MODE_AGENT, WORK_MODE_PLAN)
VALID_WORK_MODES = frozenset((WORK_MODE_ASK, WORK_MODE_AGENT, WORK_MODE_PLAN,
                               WORK_MODE_PLAN_PLANNING, WORK_MODE_PLAN_EXECUTING))


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
    WORK_MODE_PLAN_PLANNING: WorkModeMeta(
        key=WORK_MODE_PLAN_PLANNING,
        label="Plan (Planning)",
        description="Research and planning phase. Read-only tools + plan/task tools. No scene mutation.",
        prompt_instruction=(
            "Current mode is Plan (Planning). You are in the research and planning phase. "
            "You may use read-only tools to gather context, and plan/task tools to structure your work. "
            "Do not return any mutating actions."
        ),
    ),
    WORK_MODE_PLAN_EXECUTING: WorkModeMeta(
        key=WORK_MODE_PLAN_EXECUTING,
        label="Plan (Executing)",
        description="Executing a confirmed plan. Approved mutating tools + plan/task tools.",
        prompt_instruction=(
            "Current mode is Plan (Executing). You are executing a confirmed plan step by step. "
            "Use the approved tools for each step and report the actual result."
        ),
    ),
}

# Mode aliases for backward compatibility
_MODE_ALIASES: Dict[str, str] = {
    WORK_MODE_PLAN: WORK_MODE_PLAN,
}


# ---------------------------------------------------------------------------
# Tag definitions
# ---------------------------------------------------------------------------

TAG_READONLY = "readonly"
TAG_NETWORK = "network"
TAG_GEOMETRY = "geometry"
TAG_SYSTEM = "system"
TAG_DOCS = "docs"
TAG_VISION = "vision"
TAG_TASK = "task"
TAG_DANGEROUS = "dangerous"
TAG_WRITE = "write"
TAG_SKILL = "skill"

ALL_TAGS = frozenset((
    TAG_READONLY, TAG_NETWORK, TAG_GEOMETRY, TAG_SYSTEM,
    TAG_DOCS, TAG_VISION, TAG_TASK, TAG_DANGEROUS, TAG_WRITE, TAG_SKILL,
))

# Modes available for skill tools
TOOL_MODES_SKILL = frozenset({WORK_MODE_ASK, WORK_MODE_AGENT, WORK_MODE_PLAN_EXECUTING})


# ---------------------------------------------------------------------------
# Thread safety classification
# ---------------------------------------------------------------------------

THREAD_HOUDINI_MAIN = "houdini_main_thread"
THREAD_BACKGROUND = "background_safe"
THREAD_EXTERNAL = "external_process"


# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------

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
    # New fields (with defaults for backward compatibility)
    json_schema: Optional[Mapping[str, object]] = None
    thread_safety: str = THREAD_HOUDINI_MAIN
    source: str = "core"  # "core" | "skill" | "plugin" | "user"
    enabled: bool = True

    @property
    def is_readonly(self) -> bool:
        return TAG_READONLY in self.tags or TAG_DOCS in self.tags or TAG_VISION in self.tags

    @property
    def is_dangerous(self) -> bool:
        return TAG_DANGEROUS in self.tags

    @property
    def needs_main_thread(self) -> bool:
        return self.thread_safety == THREAD_HOUDINI_MAIN

    def get_json_schema(self) -> Mapping[str, object]:
        """Return the JSON Schema for OpenAI Function Calling, building from legacy schema if needed."""
        if self.json_schema:
            return self.json_schema
        return _legacy_schema_to_json_schema(self.name, self.description, self.schema)


def _legacy_schema_to_json_schema(
    name: str, description: str, schema: Mapping[str, object],
) -> Mapping[str, object]:
    """Convert a legacy {action: name, ...params...} schema to proper JSON Schema."""
    properties: Dict[str, object] = {}
    required: List[str] = []

    for key, value in schema.items():
        if key == "action":
            continue
        # Infer type from example value
        prop: Dict[str, object] = {"description": f"{key} parameter"}
        if isinstance(value, bool):
            prop["type"] = "boolean"
        elif isinstance(value, int):
            prop["type"] = "integer"
        elif isinstance(value, float):
            prop["type"] = "number"
        elif isinstance(value, (list, tuple)):
            prop["type"] = "array"
            prop["items"] = {"type": "number"}
        elif isinstance(value, str):
            if "|" in value and "action" not in value:
                prop["type"] = "string"
                prop["enum"] = [v.strip() for v in value.split("|")]
            else:
                prop["type"] = "string"
        else:
            prop["type"] = "string"
        properties[key] = prop
        required.append(key)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Mode-aware tool registry with tag classification, enable/disable, and FC schema export."""

    def __init__(self, tools: Iterable[ToolMeta] = ()):
        self._tools: Dict[str, ToolMeta] = {}
        self._toolbar_aliases: Dict[str, str] = {}
        self._disabled: Set[str] = set()
        self._lock = threading.Lock()
        for tool in tools:
            self.register(tool)

    # -- Registration --

    def register(self, tool: ToolMeta) -> None:
        with self._lock:
            self._tools[tool.name] = tool
            for action in tool.toolbar_actions:
                self._toolbar_aliases[action] = tool.name

    def unregister(self, tool_name: str) -> None:
        with self._lock:
            tool = self._tools.pop(tool_name, None)
            if tool:
                for action in tool.toolbar_actions:
                    self._toolbar_aliases.pop(action, None)
            self._disabled.discard(tool_name)

    # -- Mode normalization (backward compatible) --

    def normalize_mode(self, mode: str) -> str:
        normalized = (mode or WORK_MODE_AGENT).strip().lower()
        if normalized in VALID_WORK_MODES:
            return normalized
        if normalized in _MODE_ALIASES:
            return _MODE_ALIASES[normalized]
        return WORK_MODE_AGENT

    # -- Lookup --

    def canonical_name(self, tool_or_action: str) -> str:
        key = (tool_or_action or "").strip().lower()
        return self._toolbar_aliases.get(key, key)

    def toolbar_tool_name(self, action: str) -> str:
        return self._toolbar_aliases.get((action or "").strip().lower(), "")

    def get(self, tool_or_action: str) -> ToolMeta | None:
        return self._tools.get(self.canonical_name(tool_or_action))

    def has_tool(self, tool_or_action: str) -> bool:
        return self.get(tool_or_action) is not None

    def all_tools(self) -> List[ToolMeta]:
        with self._lock:
            return list(self._tools.values())

    # -- Enable/Disable --

    def set_enabled(self, tool_name: str, enabled: bool) -> None:
        with self._lock:
            if enabled:
                self._disabled.discard(tool_name)
            else:
                self._disabled.add(tool_name)

    def is_enabled(self, tool_or_action: str) -> bool:
        canonical = self.canonical_name(tool_or_action)
        with self._lock:
            return canonical not in self._disabled

    # -- Mode policy --

    def is_tool_allowed(self, mode: str, tool_or_action: str) -> bool:
        tool = self.get(tool_or_action)
        if tool is None:
            return False
        if not tool.enabled:
            return False
        with self._lock:
            if self.canonical_name(tool_or_action) in self._disabled:
                return False
        normalized = self.normalize_mode(mode)
        return normalized in tool.modes

    def is_toolbar_action_allowed(self, mode: str, action: str) -> bool:
        tool_name = self.toolbar_tool_name(action)
        if not tool_name:
            return True
        return self.is_tool_allowed(mode, tool_name)

    def tools_for_mode(self, mode: str) -> List[ToolMeta]:
        normalized = self.normalize_mode(mode)
        with self._lock:
            return [
                tool for tool in self._tools.values()
                if normalized in tool.modes
                and tool.enabled
                and tool.name not in self._disabled
            ]

    def action_names_for_mode(self, mode: str) -> List[str]:
        return [tool.name for tool in self.tools_for_mode(mode)]

    # -- Mode metadata --

    def mode_label(self, mode: str) -> str:
        normalized = self.normalize_mode(mode)
        if normalized in WORK_MODES:
            return WORK_MODES[normalized].label
        return WORK_MODES.get(WORK_MODE_PLAN, WorkModeMeta(WORK_MODE_PLAN, "Plan", "", "")).label

    def mode_description(self, mode: str) -> str:
        normalized = self.normalize_mode(mode)
        if normalized in WORK_MODES:
            return WORK_MODES[normalized].description
        return ""

    def mode_instruction(self, mode: str) -> str:
        normalized = self.normalize_mode(mode)
        if normalized in WORK_MODES:
            return WORK_MODES[normalized].prompt_instruction
        return ""

    def tool_label(self, tool_or_action: str) -> str:
        tool = self.get(tool_or_action)
        if tool is None:
            return self.canonical_name(tool_or_action) or tool_or_action
        return tool.label

    def block_reason(self, mode: str, tool_or_action: str) -> str:
        tool_label = self.tool_label(tool_or_action)
        mode_label = self.mode_label(mode)
        return f"{mode_label} mode does not allow {tool_label}. Switch to Agent mode to run scene-changing tools."

    # -- Schema formatting (backward compatible) --

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

    # -- OpenAI Function Calling schema export --

    def schemas_for_provider(self, mode: str) -> List[Dict[str, object]]:
        """Return OpenAI Function Calling 'tools' array for the given mode."""
        tools = self.tools_for_mode(mode)
        result: List[Dict[str, object]] = []
        for tool in tools:
            json_schema = tool.get_json_schema()
            result.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": dict(json_schema),
                },
            })
        return result

    def validate_args(self, tool_name: str, args: Dict[str, object]) -> Tuple[bool, str]:
        """Validate tool arguments against the JSON Schema.

        Returns (is_valid, error_message).
        Only checks required fields and basic type presence; full JSON Schema
        validation would require an external library.
        """
        tool = self.get(tool_name)
        if tool is None:
            return False, f"Unknown tool: {tool_name}"

        schema = tool.get_json_schema()
        if not isinstance(schema, Mapping):
            return True, ""

        required = schema.get("required", [])
        if isinstance(required, (list, tuple)):
            for req_key in required:
                if req_key not in args:
                    return False, f"Missing required parameter '{req_key}' for tool '{tool_name}'"

        properties = schema.get("properties", {})
        if isinstance(properties, Mapping):
            for key in args:
                if key not in properties:
                    # Allow extra keys (forward compatibility)
                    continue

        return True, ""

    # -- Tag-based queries --

    def tools_by_tag(self, tag: str) -> List[ToolMeta]:
        with self._lock:
            return [t for t in self._tools.values() if tag in t.tags and t.enabled and t.name not in self._disabled]

    def tools_by_source(self, source: str) -> List[ToolMeta]:
        with self._lock:
            return [t for t in self._tools.values() if t.source == source and t.enabled and t.name not in self._disabled]

    def tools_by_thread_safety(self, thread_class: str) -> List[ToolMeta]:
        with self._lock:
            return [t for t in self._tools.values() if t.thread_safety == thread_class and t.enabled and t.name not in self._disabled]


# ---------------------------------------------------------------------------
# Default tool registry
# ---------------------------------------------------------------------------

def _attach_plan_schemas(registry: ToolRegistry) -> None:
    """Attach the full JSON schemas from plan_store to plan tools after registration."""
    from houdini_ai_agent.core.plan_store import (
        PLAN_TOOL_ASK_QUESTION_SCHEMA,
        PLAN_TOOL_CREATE_SCHEMA,
        PLAN_TOOL_UPDATE_STEP_SCHEMA,
    )
    for name, schema in (
        ("create_plan", PLAN_TOOL_CREATE_SCHEMA),
        ("update_plan_step", PLAN_TOOL_UPDATE_STEP_SCHEMA),
        ("ask_question", PLAN_TOOL_ASK_QUESTION_SCHEMA),
    ):
        tool = registry.get(name)
        if tool is not None:
            updated = ToolMeta(
                name=tool.name, label=tool.label, description=tool.description,
                schema=tool.schema, adapter_method=tool.adapter_method,
                toolbar_actions=tool.toolbar_actions, tags=tool.tags,
                modes=tool.modes, json_schema=schema,
                thread_safety=tool.thread_safety, source=tool.source,
                enabled=tool.enabled,
            )
            registry.register(updated)


def get_default_tool_registry() -> ToolRegistry:
    all_modes = frozenset(WORK_MODE_ORDER)
    task_modes = frozenset(WORK_MODE_ORDER)
    agent_only = frozenset({WORK_MODE_AGENT})
    readonly_modes = frozenset({WORK_MODE_ASK, WORK_MODE_AGENT, WORK_MODE_PLAN})
    plan_planning_modes = frozenset({WORK_MODE_PLAN, WORK_MODE_PLAN_PLANNING})

    registry = ToolRegistry(
        [
            # -- Read-only tools (all modes) --
            ToolMeta(
                name="analyze_scene",
                label="Analyze Scene",
                description="Read the current scene context and summarize structure, risks, and next steps.",
                schema={"action": "analyze_scene"},
                json_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                adapter_method="analyze_scene",
                toolbar_actions=("analyze_scene",),
                tags=(TAG_READONLY,),
                modes=all_modes,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="inspect_selection",
                label="Inspect Selection",
                description="Read selected node paths, type information, parameters, and diagnostics.",
                schema={"action": "inspect_selection"},
                json_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                adapter_method="inspect_selection",
                toolbar_actions=("inspect_selection",),
                tags=(TAG_READONLY,),
                modes=all_modes,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="capture_viewport",
                label="Capture Viewport",
                description="Capture or summarize the current Scene Viewer without changing the Houdini scene.",
                schema={"action": "capture_viewport"},
                json_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                adapter_method="capture_viewport_preview",
                toolbar_actions=("capture_viewport",),
                tags=(TAG_READONLY, TAG_VISION),
                modes=all_modes,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            # -- Task tools (all modes) --
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
                json_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short task title"},
                        "detail": {"type": "string", "description": "Optional detail text"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "done", "error"],
                            "description": "Initial status",
                        },
                    },
                    "required": ["title"],
                },
                tags=(TAG_TASK,),
                modes=task_modes,
                thread_safety=THREAD_BACKGROUND,
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
                json_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Todo ID if known"},
                        "title": {"type": "string", "description": "Existing title as fallback"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "done", "error"],
                            "description": "New status",
                        },
                        "detail": {"type": "string", "description": "Optional replacement detail"},
                    },
                    "required": [],
                },
                tags=(TAG_TASK,),
                modes=task_modes,
                thread_safety=THREAD_BACKGROUND,
            ),
            # -- Mutating tools (Agent only) --
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
                json_schema={
                    "type": "object",
                    "properties": {
                        "node_type": {"type": "string", "description": "Houdini node type (e.g. box, grid, sphere, null, attribwrangle)"},
                        "node_name": {"type": "string", "description": "Optional name for the new node"},
                        "parent_path": {"type": "string", "description": "Optional parent network path"},
                    },
                    "required": ["node_type"],
                },
                adapter_method="create_node",
                toolbar_actions=("create_nodes",),
                tags=(TAG_WRITE, TAG_NETWORK, TAG_GEOMETRY),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
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
                json_schema={
                    "type": "object",
                    "properties": {
                        "target_node": {"type": "string", "description": "Full path to the target node"},
                        "code_parm": {"type": "string", "description": "Name of the code parameter (e.g. 'snippet')"},
                        "code": {"type": "string", "description": "Full replacement code"},
                    },
                    "required": ["target_node", "code_parm", "code"],
                },
                adapter_method="apply_code_to_fix_target",
                toolbar_actions=("fix_error",),
                tags=(TAG_WRITE, TAG_DANGEROUS),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
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
                json_schema={
                    "type": "object",
                    "properties": {
                        "target_node": {"type": "string", "description": "Full path to the node"},
                        "parm": {"type": "string", "description": "Parameter name"},
                        "value": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "number"},
                                {"type": "array", "items": {"type": "number"}},
                            ],
                            "description": "New parameter value (scalar, string, or tuple/array)",
                        },
                    },
                    "required": ["target_node", "parm", "value"],
                },
                adapter_method="set_node_parameter",
                tags=(TAG_WRITE, TAG_NETWORK),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            # -- New read-only tools --
            ToolMeta(
                name="get_network_structure",
                label="Get Network Structure",
                description="Get node network topology: names, types, connections, flags, and error indicators.",
                schema={"action": "get_network_structure", "network_path": ""},
                json_schema={
                    "type": "object",
                    "properties": {
                        "network_path": {"type": "string", "description": "Optional network path (defaults to current network)"},
                    },
                    "required": [],
                },
                adapter_method="get_network_structure",
                tags=(TAG_READONLY, TAG_NETWORK),
                modes=readonly_modes,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="get_node_parameters",
                label="Get Node Parameters",
                description="Get all parameters of a node with type, current value, and flags.",
                schema={"action": "get_node_parameters", "node_path": "/obj/geo1/box1"},
                json_schema={
                    "type": "object",
                    "properties": {
                        "node_path": {"type": "string", "description": "Full path to the node"},
                        "page": {"type": "integer", "description": "Page number for large parameter sets"},
                    },
                    "required": ["node_path"],
                },
                adapter_method="get_node_parameters",
                tags=(TAG_READONLY, TAG_NETWORK),
                modes=readonly_modes,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="list_children",
                label="List Children",
                description="List child nodes of a network with type and flags.",
                schema={"action": "list_children", "network_path": "", "recursive": False},
                json_schema={
                    "type": "object",
                    "properties": {
                        "network_path": {"type": "string", "description": "Network path (defaults to current)"},
                        "recursive": {"type": "boolean", "description": "Include all sub-children"},
                        "page": {"type": "integer", "description": "Page number"},
                    },
                    "required": [],
                },
                adapter_method="list_children",
                tags=(TAG_READONLY, TAG_NETWORK),
                modes=readonly_modes,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="check_errors",
                label="Check Errors",
                description="Check cooking errors and warnings for a node.",
                schema={"action": "check_errors", "node_path": ""},
                json_schema={
                    "type": "object",
                    "properties": {
                        "node_path": {"type": "string", "description": "Node path (defaults to selected or current network)"},
                    },
                    "required": [],
                },
                adapter_method="check_errors",
                tags=(TAG_READONLY, TAG_SYSTEM),
                modes=readonly_modes,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="get_node_positions",
                label="Get Node Positions",
                description="Get node positions in the network editor.",
                schema={"action": "get_node_positions", "network_path": ""},
                json_schema={
                    "type": "object",
                    "properties": {
                        "network_path": {"type": "string", "description": "Network path"},
                        "node_paths": {"type": "array", "items": {"type": "string"}, "description": "Specific node paths"},
                    },
                    "required": [],
                },
                adapter_method="get_node_positions",
                tags=(TAG_READONLY, TAG_NETWORK),
                modes=readonly_modes,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="find_nodes_by_param",
                label="Find Nodes by Parameter",
                description="Search nodes by parameter name and optional value match.",
                schema={"action": "find_nodes_by_param", "param_name": "file", "value": "", "network_path": ""},
                json_schema={
                    "type": "object",
                    "properties": {
                        "param_name": {"type": "string", "description": "Parameter name to search for"},
                        "value": {"type": "string", "description": "Optional value to match (substring)"},
                        "network_path": {"type": "string", "description": "Network to search in"},
                        "recursive": {"type": "boolean", "description": "Search all sub-children"},
                    },
                    "required": ["param_name"],
                },
                adapter_method="find_nodes_by_param",
                tags=(TAG_READONLY, TAG_NETWORK),
                modes=readonly_modes,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            # -- New mutating tools (Agent only) --
            ToolMeta(
                name="delete_node",
                label="Delete Node",
                description="Delete a node by its path.",
                schema={"action": "delete_node", "node_path": "/obj/geo1/box1"},
                json_schema={
                    "type": "object",
                    "properties": {
                        "node_path": {"type": "string", "description": "Full path of the node to delete"},
                    },
                    "required": ["node_path"],
                },
                adapter_method="delete_node",
                tags=(TAG_WRITE, TAG_NETWORK, TAG_DANGEROUS),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="connect_nodes",
                label="Connect Nodes",
                description="Connect output of one node to input of another. Use get_node_inputs first to understand port order.",
                schema={"action": "connect_nodes", "from_path": "/obj/geo1/box1", "to_path": "/obj/geo1/merge1", "input_index": 0},
                json_schema={
                    "type": "object",
                    "properties": {
                        "from_path": {"type": "string", "description": "Output node path"},
                        "to_path": {"type": "string", "description": "Input node path"},
                        "input_index": {"type": "integer", "description": "Input port index (default 0)"},
                    },
                    "required": ["from_path", "to_path"],
                },
                adapter_method="connect_nodes",
                tags=(TAG_WRITE, TAG_NETWORK, TAG_GEOMETRY),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="copy_node",
                label="Copy Node",
                description="Copy/clone a node to a new location with all parameter values.",
                schema={"action": "copy_node", "source_path": "/obj/geo1/box1", "dest_network": "", "new_name": ""},
                json_schema={
                    "type": "object",
                    "properties": {
                        "source_path": {"type": "string", "description": "Source node path"},
                        "dest_network": {"type": "string", "description": "Destination network path"},
                        "new_name": {"type": "string", "description": "Name for the copied node"},
                    },
                    "required": ["source_path"],
                },
                adapter_method="copy_node",
                tags=(TAG_WRITE, TAG_NETWORK),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="batch_set_parameters",
                label="Batch Set Parameters",
                description="Set the same parameter on multiple nodes at once.",
                schema={"action": "batch_set_parameters", "node_paths": [], "param_name": "tx", "value": 0},
                json_schema={
                    "type": "object",
                    "properties": {
                        "node_paths": {"type": "array", "items": {"type": "string"}, "description": "List of node paths"},
                        "param_name": {"type": "string", "description": "Parameter name"},
                        "value": {"description": "New value (any type)"},
                    },
                    "required": ["node_paths", "param_name"],
                },
                adapter_method="batch_set_parameters",
                tags=(TAG_WRITE, TAG_NETWORK),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="set_display_flag",
                label="Set Display Flag",
                description="Set display and render flags on a node.",
                schema={"action": "set_display_flag", "node_path": "/obj/geo1/box1", "display": True, "render": True},
                json_schema={
                    "type": "object",
                    "properties": {
                        "node_path": {"type": "string", "description": "Node path"},
                        "display": {"type": "boolean", "description": "Set display flag"},
                        "render": {"type": "boolean", "description": "Set render flag"},
                    },
                    "required": ["node_path"],
                },
                adapter_method="set_display_flag",
                tags=(TAG_WRITE, TAG_NETWORK),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="layout_nodes",
                label="Layout Nodes",
                description="Auto-layout nodes in the network editor.",
                schema={"action": "layout_nodes", "network_path": "", "method": "auto"},
                json_schema={
                    "type": "object",
                    "properties": {
                        "network_path": {"type": "string", "description": "Network path"},
                        "node_paths": {"type": "array", "items": {"type": "string"}, "description": "Specific nodes to layout"},
                        "method": {"type": "string", "enum": ["auto", "grid", "columns"], "description": "Layout method"},
                    },
                    "required": [],
                },
                adapter_method="layout_nodes",
                tags=(TAG_WRITE, TAG_NETWORK),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="execute_python",
                label="Execute Python",
                description="Execute Python code in Houdini's Python environment. Has access to 'hou' module.",
                schema={"action": "execute_python", "code": "import hou; print(hou.node('/obj').children())"},
                json_schema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python code to execute"},
                    },
                    "required": ["code"],
                },
                adapter_method="execute_python",
                tags=(TAG_WRITE, TAG_SYSTEM, TAG_DANGEROUS),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="execute_shell",
                label="Execute Shell",
                description="Execute a system shell command with safety checks. Timeout defaults to 30s, max 120s.",
                schema={"action": "execute_shell", "command": "pip list", "cwd": "", "timeout": 30},
                json_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to execute"},
                        "cwd": {"type": "string", "description": "Working directory"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (1-120)"},
                    },
                    "required": ["command"],
                },
                adapter_method="execute_shell",
                tags=(TAG_WRITE, TAG_SYSTEM, TAG_DANGEROUS),
                modes=agent_only,
                thread_safety=THREAD_EXTERNAL,
            ),
            ToolMeta(
                name="save_hip",
                label="Save HIP",
                description="Save the current HIP file.",
                schema={"action": "save_hip", "file_path": ""},
                json_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Optional save path (defaults to current)"},
                    },
                    "required": [],
                },
                adapter_method="save_hip",
                tags=(TAG_WRITE, TAG_SYSTEM),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            ToolMeta(
                name="undo_redo",
                label="Undo/Redo",
                description="Perform undo or redo in Houdini.",
                schema={"action": "undo_redo", "action": "undo"},
                json_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["undo", "redo"], "description": "Action to perform"},
                    },
                    "required": ["action"],
                },
                adapter_method="undo_redo",
                tags=(TAG_WRITE, TAG_SYSTEM),
                modes=agent_only,
                thread_safety=THREAD_HOUDINI_MAIN,
            ),
            # -- Doc RAG tool (all modes, background safe) --
            ToolMeta(
                name="search_local_doc",
                label="Search Local Docs",
                description="Search Houdini offline documentation (nodes, VEX functions, HOM API, knowledge base). "
                            "Returns relevant snippets with context. Use this before answering questions about "
                            "Houdini nodes, VEX functions, or Python HOM API.",
                schema={"action": "search_local_doc", "query": "attribwrangle"},
                json_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query: node name, VEX function, or HOM class/method"},
                        "top_k": {"type": "integer", "description": "Max results (default 5)"},
                    },
                    "required": ["query"],
                },
                tags=(TAG_READONLY, TAG_DOCS),
                modes=all_modes,
                thread_safety=THREAD_BACKGROUND,
            ),
            # -- Plan tools (plan modes only) --
            ToolMeta(
                name="create_plan",
                label="Create Plan",
                description="Create a structured execution plan with steps, dependencies, and architecture blueprint. "
                            "Use this during planning phase after researching the scene.",
                schema={"action": "create_plan", "title": "", "overview": "", "steps": []},
                json_schema=None,  # Imported from plan_store at registration time
                tags=(TAG_TASK,),
                modes=frozenset({WORK_MODE_PLAN, WORK_MODE_PLAN_PLANNING}),
                thread_safety=THREAD_BACKGROUND,
            ),
            ToolMeta(
                name="update_plan_step",
                label="Update Plan Step",
                description="Update a plan step's status during execution. "
                            "Call with status='running' when starting, 'done' or 'error' when finishing.",
                schema={"action": "update_plan_step", "step_id": "step-1", "status": "done"},
                json_schema=None,
                tags=(TAG_TASK,),
                modes=frozenset({WORK_MODE_PLAN_EXECUTING}),
                thread_safety=THREAD_BACKGROUND,
            ),
            ToolMeta(
                name="ask_question",
                label="Ask Question",
                description="Ask the user a question during planning phase. "
                            "Use when you need clarification before creating the plan.",
                schema={"action": "ask_question", "questions": []},
                json_schema=None,
                tags=(TAG_TASK,),
                modes=frozenset({WORK_MODE_PLAN, WORK_MODE_PLAN_PLANNING}),
                thread_safety=THREAD_BACKGROUND,
            ),
        ]
    )
    _attach_plan_schemas(registry)
    return registry
