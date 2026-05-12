"""Execution helpers for model-requested Houdini agent actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional


ToolResultDict = Dict[str, object]
TodoHandler = Callable[..., ToolResultDict]
ThinkingLevelGetter = Callable[[], str]


@dataclass
class ToolResult:
    title: str
    message: str = ""
    events: List[Dict[str, str]] = field(default_factory=list)
    success: Optional[bool] = None
    created_paths: List[str] = field(default_factory=list)
    changed_paths: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ToolResult":
        events = []
        for event in raw.get("events", []):
            if isinstance(event, dict):
                events.append(
                    {
                        "title": str(event.get("title", "") or ""),
                        "detail": str(event.get("detail", "") or ""),
                        "status": str(event.get("status", "info") or "info"),
                    }
                )
        success = raw.get("success")
        errors = _string_list(raw.get("errors", []))
        message = str(raw.get("message", "") or "")
        if not isinstance(success, bool):
            success = not _legacy_error_markers(events, errors, message)
        return cls(
            title=str(raw.get("title", "Model action") or "Model action"),
            message=message,
            events=events,
            success=success,
            created_paths=_string_list(raw.get("created_paths", [])),
            changed_paths=_string_list(raw.get("changed_paths", [])),
            warnings=_string_list(raw.get("warnings", [])),
            errors=errors,
        )

    def to_dict(self) -> ToolResultDict:
        return {
            "title": self.title,
            "message": self.message,
            "events": list(self.events),
            "success": self.success,
            "created_paths": list(self.created_paths),
            "changed_paths": list(self.changed_paths),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }

    def has_error(self) -> bool:
        if self.success is False or self.errors:
            return True
        if any(str(event.get("status", "")).lower() == "error" for event in self.events):
            return True
        lowered = self.message.lower()
        return any(marker in lowered for marker in ("failed", "失败", "error", "exception", "traceback"))


class ActionRunner:
    """Dispatch model actions to the adapter and normalize their results."""

    def __init__(
        self,
        adapter,
        thinking_level: ThinkingLevelGetter,
        add_todo: Optional[TodoHandler] = None,
        update_todo: Optional[TodoHandler] = None,
    ):
        self.adapter = adapter
        self._thinking_level = thinking_level
        self._add_todo = add_todo
        self._update_todo = update_todo

    def execute(self, action: Mapping[str, object]) -> ToolResultDict:
        name = self.action_name(action)
        validation_error = self._validate(name, action)
        if validation_error:
            return validation_error.to_dict()
        result = self._execute(name, action)
        return ToolResult.from_mapping(result).to_dict()

    def has_error(self, result: Mapping[str, object]) -> bool:
        return ToolResult.from_mapping(result).has_error()

    def summarize(self, action: Mapping[str, object]) -> str:
        name = self.action_name(action)
        node = "节点"
        current_network = "当前网络"
        target_node = "目标节点"
        if name == "create_node":
            return f"创建 {action.get('node_type', node)}，位置：{action.get('parent_path', '') or current_network}"
        if name == "apply_code":
            return f"把代码写入 {action.get('target_node', '') or target_node} / {action.get('code_parm', 'snippet')}"
        if name == "set_parm":
            return f"设置 {action.get('target_node', '') or target_node} 的 {action.get('parm', '参数')} = {action.get('value', '')}"
        if name == "inspect_selection":
            return "检查当前选中节点"
        if name == "capture_viewport":
            return "捕获当前视口"
        if name == "analyze_scene":
            return "分析当前场景上下文"
        if name == "add_todo":
            return f"添加任务：{action.get('title', '') or action.get('task', '')}"
        if name == "update_todo":
            return f"更新任务：{action.get('title', '') or action.get('id', '')}"
        return "执行模型请求的工具动作"

    @staticmethod
    def action_name(action: Mapping[str, object]) -> str:
        return str(action.get("action", "") or "").strip().lower()

    def _validate(self, name: str, action: Mapping[str, object]) -> Optional[ToolResult]:
        if not name:
            return _validation_error("Unknown model action", "Action name is required.")
        if name == "create_node":
            return _require_nonempty(action, "node_type", "Create node")
        if name == "apply_code":
            missing = _missing_nonempty(action, ("target_node", "code"))
            if missing:
                return _validation_error("Apply code", f"Missing required field(s): {', '.join(missing)}.")
        if name == "set_parm":
            missing = _missing_nonempty(action, ("target_node", "parm"))
            if "value" not in action:
                missing.append("value")
            if missing:
                return _validation_error("Set parameter", f"Missing required field(s): {', '.join(missing)}.")
        if name == "add_todo":
            title = str(action.get("title", "") or action.get("task", "") or "").strip()
            if not title:
                return _validation_error("Update todo", "Todo title is required.")
        if name == "update_todo":
            todo_id = str(action.get("id", "") or action.get("todo_id", "") or "").strip()
            title = str(action.get("title", "") or "").strip()
            if not todo_id and not title:
                return _validation_error("Update todo", "Todo id or title is required.")
        return None

    def _execute(self, name: str, action: Mapping[str, object]) -> ToolResultDict:
        if name == "create_node":
            creator = getattr(self.adapter, "create_node", None)
            if creator is None:
                return _simple_result("Create node", "Current adapter cannot create nodes.", success=False)
            return creator(
                str(action.get("node_type", "") or "null"),
                str(action.get("node_name", "") or ""),
                str(action.get("parent_path", "") or ""),
            )
        if name == "apply_code":
            applier = getattr(self.adapter, "apply_code_to_fix_target", None)
            if applier is None:
                return _simple_result("Apply code", "Current adapter cannot apply code edits.", success=False)
            fix_context = {
                "target_node": str(action.get("target_node", "") or ""),
                "code_parm": str(action.get("code_parm", "") or "snippet"),
            }
            return applier(fix_context, str(action.get("code", "") or ""))
        if name == "set_parm":
            setter = getattr(self.adapter, "set_node_parameter", None)
            if setter is None:
                return _simple_result("Set parameter", "Current adapter cannot set node parameters.", success=False)
            return setter(
                str(action.get("target_node", "") or ""),
                str(action.get("parm", "") or action.get("parameter", "") or ""),
                action.get("value", ""),
            )
        if name == "inspect_selection":
            return self.adapter.inspect_selection(self._thinking_level())
        if name == "capture_viewport":
            return self.adapter.capture_viewport_preview(self._thinking_level())
        if name == "analyze_scene":
            return self.adapter.analyze_scene(self._thinking_level())
        if name == "add_todo" and self._add_todo is not None:
            return self._add_todo(
                str(action.get("title", "") or action.get("task", "") or ""),
                str(action.get("detail", "") or ""),
                str(action.get("status", "") or "pending"),
            )
        if name == "update_todo" and self._update_todo is not None:
            return self._update_todo(
                str(action.get("id", "") or action.get("todo_id", "") or ""),
                str(action.get("title", "") or ""),
                str(action.get("status", "") or ""),
                str(action.get("detail", "") or ""),
            )
        return {
            "title": "Unknown model action",
            "events": [{"title": "Unsupported action", "detail": name or "<empty>", "status": "warning"}],
            "message": f"The model requested an unsupported action: `{name}`.",
            "success": False,
        }


def _simple_result(title: str, message: str, success: bool) -> ToolResultDict:
    return {"title": title, "events": [], "message": message, "success": success}


def _validation_error(title: str, message: str) -> ToolResult:
    return ToolResult(
        title=title,
        message=message,
        events=[{"title": "Action validation failed", "detail": message, "status": "error"}],
        success=False,
        errors=[message],
    )


def _require_nonempty(action: Mapping[str, object], field_name: str, title: str) -> Optional[ToolResult]:
    missing = _missing_nonempty(action, (field_name,))
    if missing:
        return _validation_error(title, f"Missing required field(s): {', '.join(missing)}.")
    return None


def _missing_nonempty(action: Mapping[str, object], field_names: tuple[str, ...]) -> List[str]:
    missing = []
    for field_name in field_names:
        value = action.get(field_name, "")
        if value is None or (isinstance(value, str) and not value.strip()) or (not isinstance(value, str) and value == ""):
            missing.append(field_name)
    return missing


def _string_list(raw: object) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def _legacy_error_markers(events: List[Dict[str, str]], errors: List[str], message: str) -> bool:
    if errors:
        return True
    if any(str(event.get("status", "")).lower() == "error" for event in events):
        return True
    lowered = message.lower()
    return any(marker in lowered for marker in ("failed", "失败", "error", "exception", "traceback"))
