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
        if name == "get_network_structure":
            return f"读取网络结构：{action.get('network_path', '') or current_network}"
        if name == "get_node_parameters":
            return f"读取参数：{action.get('node_path', '') or target_node}"
        if name == "list_children":
            return f"列出子节点：{action.get('network_path', '') or current_network}"
        if name == "check_errors":
            return f"检查错误：{action.get('node_path', '') or target_node}"
        if name == "delete_node":
            return f"删除节点：{action.get('node_path', '') or target_node}"
        if name == "connect_nodes":
            return f"连接 {action.get('from_path', '')} → {action.get('to_path', '')}"
        if name == "copy_node":
            return f"复制节点：{action.get('source_path', '')}"
        if name == "batch_set_parameters":
            return f"批量设置 {action.get('param_name', '参数')}"
        if name == "set_display_flag":
            return f"设置标志：{action.get('node_path', '')}"
        if name == "layout_nodes":
            return f"布局节点：{action.get('network_path', '') or current_network}"
        if name == "execute_python":
            return f"执行 Python 代码"
        if name == "execute_shell":
            return f"执行 Shell：{str(action.get('command', ''))[:50]}"
        if name == "save_hip":
            return f"保存 HIP"
        if name == "undo_redo":
            return f"{'撤销' if action.get('action') == 'undo' else '重做'}"
        if name == "find_nodes_by_param":
            return f"搜索参数 {action.get('param_name', '')}"
        if name == "get_node_positions":
            return f"读取节点位置"
        if name == "search_local_doc":
            return f"搜索文档：{str(action.get('query', ''))[:50]}"
        if name == "create_plan":
            return f"创建计划：{str(action.get('title', ''))[:50]}"
        if name == "update_plan_step":
            return f"更新步骤：{action.get('step_id', '')} → {action.get('status', '')}"
        if name == "ask_question":
            return f"向用户提问"
        # -- Skill tools --
        if name.startswith("skill:"):
            skill_label = name.replace("skill:", "").replace("_", " ")
            return f"执行技能：{skill_label}"
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
        if name == "delete_node":
            return _require_nonempty(action, "node_path", "Delete node")
        if name == "connect_nodes":
            missing = _missing_nonempty(action, ("from_path", "to_path"))
            if missing:
                return _validation_error("Connect nodes", f"Missing required field(s): {', '.join(missing)}.")
        if name == "copy_node":
            return _require_nonempty(action, "source_path", "Copy node")
        if name == "batch_set_parameters":
            missing = _missing_nonempty(action, ("param_name",))
            if not action.get("node_paths"):
                missing.append("node_paths")
            if missing:
                return _validation_error("Batch set parameters", f"Missing required field(s): {', '.join(missing)}.")
        if name == "set_display_flag":
            return _require_nonempty(action, "node_path", "Set display flag")
        if name == "execute_python":
            return _require_nonempty(action, "code", "Execute Python")
        if name == "execute_shell":
            return _require_nonempty(action, "command", "Execute Shell")
        if name == "undo_redo":
            act = str(action.get("action", "") or "").strip()
            if act not in ("undo", "redo"):
                return _validation_error("Undo/Redo", 'action must be "undo" or "redo".')
        if name == "find_nodes_by_param":
            return _require_nonempty(action, "param_name", "Find nodes by param")
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
        # -- New read-only tools --
        if name == "get_network_structure":
            return self._call_adapter("get_network_structure", network_path=str(action.get("network_path", "") or ""))
        if name == "get_node_parameters":
            return self._call_adapter("get_node_parameters", node_path=str(action.get("node_path", "") or ""),
                                      page=int(action.get("page", 1) or 1))
        if name == "list_children":
            return self._call_adapter("list_children", network_path=str(action.get("network_path", "") or ""),
                                      recursive=bool(action.get("recursive", False)),
                                      page=int(action.get("page", 1) or 1))
        if name == "check_errors":
            return self._call_adapter("check_errors", node_path=str(action.get("node_path", "") or ""))
        if name == "get_node_positions":
            return self._call_adapter("get_node_positions", network_path=str(action.get("network_path", "") or ""),
                                      node_paths=action.get("node_paths"))
        if name == "find_nodes_by_param":
            return self._call_adapter("find_nodes_by_param",
                                      param_name=str(action.get("param_name", "") or ""),
                                      value=str(action.get("value", "") or ""),
                                      network_path=str(action.get("network_path", "") or ""),
                                      recursive=bool(action.get("recursive", True)))
        # -- New mutating tools --
        if name == "delete_node":
            return self._call_adapter("delete_node", node_path=str(action.get("node_path", "") or ""))
        if name == "connect_nodes":
            return self._call_adapter("connect_nodes",
                                      from_path=str(action.get("from_path", "") or ""),
                                      to_path=str(action.get("to_path", "") or ""),
                                      input_index=int(action.get("input_index", 0) or 0))
        if name == "copy_node":
            return self._call_adapter("copy_node",
                                      source_path=str(action.get("source_path", "") or ""),
                                      dest_network=str(action.get("dest_network", "") or ""),
                                      new_name=str(action.get("new_name", "") or ""))
        if name == "batch_set_parameters":
            return self._call_adapter("batch_set_parameters",
                                      node_paths=action.get("node_paths", []),
                                      param_name=str(action.get("param_name", "") or ""),
                                      value=action.get("value"))
        if name == "set_display_flag":
            return self._call_adapter("set_display_flag",
                                      node_path=str(action.get("node_path", "") or ""),
                                      display=bool(action.get("display", True)),
                                      render=bool(action.get("render", True)))
        if name == "layout_nodes":
            return self._call_adapter("layout_nodes",
                                      network_path=str(action.get("network_path", "") or ""),
                                      node_paths=action.get("node_paths"),
                                      method=str(action.get("method", "auto") or "auto"))
        if name == "execute_python":
            return self._call_adapter("execute_python", code=str(action.get("code", "") or ""))
        if name == "execute_shell":
            return self._call_adapter("execute_shell",
                                      command=str(action.get("command", "") or ""),
                                      cwd=str(action.get("cwd", "") or ""),
                                      timeout=int(action.get("timeout", 30) or 30))
        if name == "save_hip":
            return self._call_adapter("save_hip", file_path=str(action.get("file_path", "") or ""))
        if name == "undo_redo":
            return self._call_adapter("undo_redo", action=str(action.get("action", "undo") or "undo"))
        # -- Doc RAG tool --
        if name == "search_local_doc":
            return self._execute_search_local_doc(action)
        # -- Plan tools --
        if name == "create_plan":
            return self._execute_create_plan(action)
        if name == "update_plan_step":
            return self._execute_update_plan_step(action)
        if name == "ask_question":
            return self._execute_ask_question(action)
        # -- Skill tools --
        if name.startswith("skill:"):
            return self._execute_skill(name, action)
        # -- Task tools --
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
        # -- Plugin tools --
        plugin_result = self._execute_plugin_tool(name, action)
        if plugin_result is not None:
            return plugin_result
        return {
            "title": "Unknown model action",
            "events": [{"title": "Unsupported action", "detail": name or "<empty>", "status": "warning"}],
            "message": f"The model requested an unsupported action: `{name}`.",
            "success": False,
        }

    def _execute_create_plan(self, action: Mapping[str, object]) -> ToolResultDict:
        """Execute create_plan using PlanManager."""
        try:
            from houdini_ai_agent.core.plan_store import get_plan_manager
            import json
            # Extract session_id from somewhere - for now use a default
            session_id = str(action.get("session_id", "") or "default")
            plan_data = get_plan_manager().create_plan(session_id, action)
            return {
                "title": "Create Plan",
                "message": f"Plan created: {plan_data.get('title', '')} "
                           f"({len(plan_data.get('steps', []))} steps, "
                           f"status: {plan_data.get('status', '')})",
                "plan_data": plan_data,
                "success": True,
            }
        except Exception as exc:
            return {"title": "Create Plan", "events": [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Create plan failed: {exc}", "success": False}

    def _execute_update_plan_step(self, action: Mapping[str, object]) -> ToolResultDict:
        """Execute update_plan_step using PlanManager."""
        step_id = str(action.get("step_id", "") or "")
        status = str(action.get("status", "") or "")
        result_summary = str(action.get("result_summary", "") or "")
        if not step_id or status not in ("running", "done", "error"):
            return {"title": "Update Plan Step", "message": "step_id and valid status (running/done/error) required.",
                    "success": False}
        try:
            from houdini_ai_agent.core.plan_store import get_plan_manager
            session_id = str(action.get("session_id", "") or "default")
            plan = get_plan_manager().update_step(session_id, step_id, status, result_summary)
            if plan is None:
                return {"title": "Update Plan Step", "message": f"No active plan for session.", "success": False}
            stats = get_plan_manager().plan_stats(session_id)
            return {
                "title": "Update Plan Step",
                "message": f"Step {step_id} updated to '{status}'. "
                           f"Progress: {stats.get('done', 0)}/{stats.get('total', 0)} done, "
                           f"plan status: {plan.get('status', '')}",
                "success": True,
            }
        except Exception as exc:
            return {"title": "Update Plan Step", "events": [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Update plan step failed: {exc}", "success": False}

    def _execute_ask_question(self, action: Mapping[str, object]) -> ToolResultDict:
        """Execute ask_question - returns the questions for the session layer to handle."""
        questions = action.get("questions", [])
        if not isinstance(questions, list) or not questions:
            return {"title": "Ask Question", "message": "questions array is required.", "success": False}
        # The actual user interaction is handled by the session/UI layer.
        # Here we just validate and return the questions as a result.
        return {
            "title": "Ask Question",
            "message": f"Questions asked: {len(questions)}. "
                       f"Awaiting user response (handled by UI layer).",
            "questions": questions,
            "needs_user_input": True,
            "success": True,
        }

    def _execute_skill(self, tool_name: str, action: Mapping[str, object]) -> ToolResultDict:
        """Execute a skill tool by name."""
        skill_name = tool_name.replace("skill:", "")
        # Extract parameters (everything except 'action')
        params = {k: v for k, v in action.items() if k != "action" and v is not None}
        try:
            from houdini_ai_agent.core.skills import run_skill, set_adapter
            set_adapter(self.adapter)
            result = run_skill(skill_name, params)
            if "error" in result:
                return {
                    "title": f"Skill: {skill_name}",
                    "message": f"Skill failed: {result['error']}",
                    "events": [{"title": "Skill error", "detail": result["error"], "status": "error"}],
                    "success": False,
                }
            # Format the result for display
            import json
            message = json.dumps(result, ensure_ascii=False, indent=2, default=str)
            if len(message) > 5000:
                message = message[:4500] + "\n... (truncated)"
            return {
                "title": f"Skill: {skill_name}",
                "message": message,
                "skill_result": result,
                "success": True,
            }
        except Exception as exc:
            return {
                "title": f"Skill: {skill_name}",
                "message": f"Skill execution error: {exc}",
                "events": [{"title": "Error", "detail": str(exc), "status": "error"}],
                "success": False,
            }

    def _call_adapter(self, method_name: str, **kwargs) -> ToolResultDict:
        """Safely call an adapter method with the given keyword arguments."""
        method = getattr(self.adapter, method_name, None)
        if method is None:
            return {"title": method_name, "events": [],
                    "message": f"Adapter does not support {method_name}.", "success": False}
        try:
            return method(**kwargs)
        except Exception as exc:
            return {"title": method_name, "events": [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"{method_name} failed: {exc}", "success": False}

    def _execute_plugin_tool(self, name: str, action: Mapping[str, object]) -> Optional[ToolResultDict]:
        """Try to execute an external plugin tool. Returns None if not a plugin tool."""
        try:
            from houdini_ai_agent.core.hooks import get_hook_manager
            manager = get_hook_manager()
            if not manager.has_external_tool(name):
                return None
            # Build args dict from action (exclude the "action" key itself)
            args = {k: v for k, v in action.items() if k != "action"}
            result = manager.execute_external_tool(name, args)
            title = f"Plugin Tool: {name}"
            events = []
            if not result.get("success", True):
                error_msg = result.get("error", "Unknown error")
                events.append({"title": "Plugin tool error", "detail": error_msg, "status": "error"})
            message = str(result.get("result", "") or result.get("error", ""))
            return {
                "title": title,
                "events": events,
                "message": message,
                "success": result.get("success", True),
            }
        except ImportError:
            return None
        except Exception as exc:
            return {
                "title": f"Plugin Tool: {name}",
                "events": [{"title": "Error", "detail": str(exc), "status": "error"}],
                "message": f"Plugin tool '{name}' failed: {exc}",
                "success": False,
            }

    def _execute_search_local_doc(self, action: Mapping[str, object]) -> ToolResultDict:
        """Execute search_local_doc using the doc_rag module directly (no adapter needed)."""
        query = str(action.get("query", "") or "").strip()
        if not query:
            return {"title": "Search Local Docs", "events": [],
                    "message": "Query is required.", "success": False}
        try:
            from houdini_ai_agent.core.doc_rag import get_doc_index
            index = get_doc_index()
            top_k = int(action.get("top_k", 5) or 5)
            results = index.search(query, top_k=top_k)
            if not results:
                return {"title": "Search Local Docs",
                        "message": f"No documentation found for '{query}'.",
                        "success": True}
            snippets = []
            for r in results:
                snippets.append(f"[{r['type']}] {r['name']} (score: {r['score']:.2f})\n{r['snippet']}")
            return {"title": "Search Local Docs",
                    "message": "\n\n".join(snippets),
                    "success": True}
        except Exception as exc:
            return {"title": "Search Local Docs",
                    "events": [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Doc search failed: {exc}", "success": False}


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
