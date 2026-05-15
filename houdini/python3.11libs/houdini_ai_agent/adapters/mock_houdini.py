"""Mock Houdini adapter for the first UI milestone and testing.

This module defines the base adapter interface. All tool methods return a
unified dict format: {"title", "events", "message", "success"}.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional


class MockHoudiniAdapter:
    """Base adapter with stub implementations for every tool method.

    Subclasses (HoudiniAdapter) override methods that need real HOM calls.
    """

    name = "Mock Houdini"

    # ------------------------------------------------------------------
    # Session / storage
    # ------------------------------------------------------------------

    def get_session_storage_dir(self):
        return None

    # ------------------------------------------------------------------
    # Context (read-only)
    # ------------------------------------------------------------------

    def get_context(self) -> Dict[str, object]:
        return {
            "hip_file": "E:/Work/Houdini/demo_scene.hip",
            "network": "/obj/terrain_agent_preview",
            "selected_nodes": ["/obj/terrain_agent_preview/mountain1"],
            "viewport": "SceneViewer: persp1 / camera: none / shading: Smooth Wire Shaded",
            "errors": [
                {
                    "node": "/obj/terrain_agent_preview/attribwrangle1",
                    "message": "VEX error: Unknown function 'fitramge'. Did you mean 'fitrange'?",
                    "severity": "error",
                }
            ],
            "summary": "Mock terrain SOP network with a mountain deformation and one VEX typo.",
        }

    def describe_context(self, context: Dict[str, object]) -> str:
        selected = ", ".join(context.get("selected_nodes", [])) or "none"
        errors = context.get("errors", [])
        return f"HIP: {context.get('hip_file')} | Network: {context.get('network')} | Selected: {selected} | Errors: {len(errors)}"

    # ------------------------------------------------------------------
    # Read-only analysis tools
    # ------------------------------------------------------------------

    def analyze_scene(self, thinking_level: str) -> Dict[str, object]:
        return {
            "title": "分析工程",
            "events": [
                {"title": "读取 HIP 信息", "detail": "Collected file path, current network and selected nodes.", "status": "success"},
                {"title": "扫描节点网络", "detail": "Found terrain source, mountain deformation and VEX wrangle.", "status": "success"},
                {"title": "生成摘要", "detail": f"Used thinking level {thinking_level} for a compact scene explanation.", "status": "success"},
            ],
            "message": "工程预览：这是一个地形 SOP 网络，主要流程是 grid -> mountain -> wrangle。当前有一个 VEX 拼写错误等待修复。",
        }

    def inspect_selection(self, thinking_level: str) -> Dict[str, object]:
        return {
            "title": "查看选中节点",
            "events": [
                {"title": "读取选择", "detail": "Selected: /obj/terrain_agent_preview/mountain1", "status": "success"},
                {"title": "读取参数", "detail": "height=1.25, elementsize=0.8, offset animated=false", "status": "success"},
            ],
            "message": "选中节点是 `mountain1`，类型为 Mountain SOP。它负责给 grid 添加噪声起伏。",
        }

    def get_network_structure(self, network_path: str = "") -> Dict[str, object]:
        path = network_path or "/obj/terrain_agent_preview"
        return {
            "title": "Get network structure",
            "events": [
                {"title": "Read network", "detail": path, "status": "success"},
                {"title": "Node count", "detail": "5 nodes", "status": "success"},
            ],
            "message": (
                f"Network `{path}` structure (mock):\n"
                "```\n"
                "grid1 [grid]  →  mountain1 [mountain]  →  attribwrangle1 [attribwrangle]\n"
                "                                              →  null1 [null] (display)\n"
                "```\n"
            ),
            "success": True,
        }

    def get_node_parameters(self, node_path: str, page: int = 1) -> Dict[str, object]:
        return {
            "title": "Get node parameters",
            "events": [
                {"title": "Read node", "detail": node_path or "/obj/geo1/box1", "status": "success"},
                {"title": "Parameter count", "detail": "12 parameters found", "status": "success"},
            ],
            "message": (
                f"Node `{node_path or '/obj/geo1/box1'}` parameters (mock):\n"
                "- sizex = 1.0  (float)\n"
                "- sizey = 1.0  (float)\n"
                "- sizez = 1.0  (float)\n"
                "- scale = 1.0  (float)\n"
                "- display = True  (toggle)\n"
            ),
            "success": True,
        }

    def list_children(self, network_path: str = "", recursive: bool = False, page: int = 1) -> Dict[str, object]:
        path = network_path or "/obj/terrain_agent_preview"
        return {
            "title": "List children",
            "events": [
                {"title": "Read children", "detail": path, "status": "success"},
            ],
            "message": (
                f"Children of `{path}` (mock):\n"
                "1. grid1 [grid] (display: off)\n"
                "2. mountain1 [mountain] (display: off)\n"
                "3. attribwrangle1 [attribwrangle] (display: off, 1 error)\n"
                "4. null1 [null] (display: on)\n"
                f"{'5. OUT_agent [null]' if not recursive else ''}\n"
            ),
            "success": True,
        }

    def check_errors(self, node_path: str = "") -> Dict[str, object]:
        path = node_path or "/obj/terrain_agent_preview/attribwrangle1"
        return {
            "title": "Check errors",
            "events": [
                {"title": "Check node", "detail": path, "status": "success"},
                {"title": "Errors found", "detail": "1 error, 0 warnings", "status": "warning"},
            ],
            "message": f"Node `{path}` has errors:\n- VEX error: Unknown function 'fitramge'. Did you mean 'fitrange'?",
            "success": True,
        }

    def get_node_positions(self, network_path: str = "", node_paths: Optional[List[str]] = None) -> Dict[str, object]:
        return {
            "title": "Get node positions",
            "events": [{"title": "Read positions", "detail": "mock", "status": "success"}],
            "message": "Mock: node positions not available outside Houdini.",
            "success": True,
        }

    # ------------------------------------------------------------------
    # Viewport / capture
    # ------------------------------------------------------------------

    def capture_viewport_preview(self, thinking_level: str) -> Dict[str, object]:
        return {
            "title": "捕获视口预演",
            "events": [
                {"title": "定位 Scene Viewer", "detail": "Mock viewport persp1 found.", "status": "success"},
                {"title": "捕获画面", "detail": "Viewport capture is mocked in this milestone.", "status": "success"},
            ],
            "message": "已读取当前视口预览信息。真实截图导出会在 Houdini 接入阶段实现。",
        }

    # ------------------------------------------------------------------
    # Node mutation tools
    # ------------------------------------------------------------------

    def create_node_preview(self, thinking_level: str, request_text: str = "") -> Dict[str, object]:
        return {
            "title": "创建节点预演",
            "events": [
                {"title": "规划节点", "detail": "Create null OUT_AGENT_PREVIEW after selected node.", "status": "running"},
                {"title": "模拟创建", "detail": "No real Houdini node was modified in mock mode.", "status": "success"},
            ],
            "message": "已完成节点创建预演：下一阶段会在真实 Houdini adapter 中创建并连接 `OUT_AGENT_PREVIEW`。",
        }

    def create_node(self, node_type: str, node_name: str = "", parent_path: str = "") -> Dict[str, object]:
        node_type = node_type or "null"
        return {
            "title": "Create node",
            "events": [{"title": "Mock create", "detail": f"{node_type} named {node_name or f'agent_{node_type}1'}", "status": "success"}],
            "message": f"Mock mode: would create `{node_type}` node named `{node_name or f'agent_{node_type}1'}`.",
            "success": True,
        }

    def delete_node(self, node_path: str) -> Dict[str, object]:
        if not node_path:
            return {"title": "Delete node", "events": [{"title": "Missing path", "detail": "node_path is required", "status": "error"}],
                    "message": "Delete node failed: node_path is required.", "success": False}
        return {
            "title": "Delete node",
            "events": [{"title": "Mock delete", "detail": node_path, "status": "success"}],
            "message": f"Mock mode: would delete node `{node_path}`.",
            "success": True,
        }

    def connect_nodes(self, from_path: str, to_path: str, input_index: int = 0) -> Dict[str, object]:
        if not from_path or not to_path:
            return {"title": "Connect nodes", "events": [{"title": "Missing paths", "detail": "from_path and to_path are required", "status": "error"}],
                    "message": "Connect nodes failed: from_path and to_path are required.", "success": False}
        return {
            "title": "Connect nodes",
            "events": [{"title": "Mock connect", "detail": f"{from_path} → {to_path}[{input_index}]", "status": "success"}],
            "message": f"Mock mode: would connect `{from_path}` output to `{to_path}` input {input_index}.",
            "success": True,
        }

    def copy_node(self, source_path: str, dest_network: str = "", new_name: str = "") -> Dict[str, object]:
        if not source_path:
            return {"title": "Copy node", "events": [{"title": "Missing source", "detail": "source_path is required", "status": "error"}],
                    "message": "Copy node failed: source_path is required.", "success": False}
        return {
            "title": "Copy node",
            "events": [{"title": "Mock copy", "detail": f"{source_path} → {new_name or 'copy'}", "status": "success"}],
            "message": f"Mock mode: would copy `{source_path}` as `{new_name or 'copy'}` in `{dest_network or 'same network'}`.",
            "success": True,
        }

    def set_node_parameter(self, target_node: str, parm_name: str, value: Any = None) -> Dict[str, object]:
        return {
            "title": "Set parameter",
            "events": [{"title": "Mock set parameter", "detail": f"{target_node}.{parm_name} = {value}", "status": "success"}],
            "message": f"Mock mode set `{target_node}.{parm_name}` to `{value}`.",
            "success": True,
        }

    def batch_set_parameters(self, node_paths: List[str], param_name: str, value: Any = None) -> Dict[str, object]:
        if not node_paths or not param_name:
            return {"title": "Batch set parameters", "events": [{"title": "Missing args", "detail": "node_paths and param_name required", "status": "error"}],
                    "message": "Batch set parameters failed: node_paths and param_name are required.", "success": False}
        return {
            "title": "Batch set parameters",
            "events": [{"title": "Mock batch set", "detail": f"{param_name} = {value} on {len(node_paths)} nodes", "status": "success"}],
            "message": f"Mock mode: would set `{param_name}` to `{value}` on {len(node_paths)} node(s).",
            "success": True,
        }

    def find_nodes_by_param(self, param_name: str, value: str = "", network_path: str = "", recursive: bool = True) -> Dict[str, object]:
        if not param_name:
            return {"title": "Find nodes by param", "events": [{"title": "Missing param_name", "detail": "param_name is required", "status": "error"}],
                    "message": "Find nodes failed: param_name is required.", "success": False}
        return {
            "title": "Find nodes by param",
            "events": [{"title": "Mock search", "detail": f"param={param_name}, value={value}", "status": "success"}],
            "message": f"Mock mode: would search for nodes with `{param_name}` = `{value}` in `{network_path or 'current network'}`.",
            "success": True,
        }

    def set_display_flag(self, node_path: str, display: bool = True, render: bool = True) -> Dict[str, object]:
        if not node_path:
            return {"title": "Set display flag", "events": [{"title": "Missing node_path", "detail": "node_path is required", "status": "error"}],
                    "message": "Set display flag failed: node_path is required.", "success": False}
        return {
            "title": "Set display flag",
            "events": [{"title": "Mock set flags", "detail": f"{node_path}: display={display}, render={render}", "status": "success"}],
            "message": f"Mock mode: would set `{node_path}` display={display}, render={render}.",
            "success": True,
        }

    def layout_nodes(self, network_path: str = "", node_paths: Optional[List[str]] = None, method: str = "auto") -> Dict[str, object]:
        return {
            "title": "Layout nodes",
            "events": [{"title": "Mock layout", "detail": f"method={method}", "status": "success"}],
            "message": f"Mock mode: would auto-layout nodes in `{network_path or 'current network'}` using {method} method.",
            "success": True,
        }

    # ------------------------------------------------------------------
    # Code / execution tools
    # ------------------------------------------------------------------

    def execute_python(self, code: str) -> Dict[str, object]:
        """Execute Python code in a sandboxed namespace (mock mode)."""
        if not code or not code.strip():
            return {"title": "Execute Python", "events": [{"title": "Empty code", "detail": "code is required", "status": "error"}],
                    "message": "Execute Python failed: code is required.", "success": False}

        # Security check
        dangerous = self._check_python_safety(code)
        if dangerous:
            return {"title": "Execute Python", "events": [{"title": "Security check", "detail": dangerous, "status": "error"}],
                    "message": f"Code rejected: {dangerous}", "success": False}

        # Safe mock execution
        try:
            import io
            import contextlib
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                exec(compile(code, "<agent_python>", "exec"), {"__builtins__": {}})
            result = output.getvalue()
            if not result.strip():
                result = "(no output)"
            return {
                "title": "Execute Python",
                "events": [{"title": "Mock exec", "detail": f"Code executed ({len(code)} chars)", "status": "success"}],
                "message": f"Mock mode Python output:\n```\n{result}\n```",
                "success": True,
            }
        except Exception as exc:
            return {
                "title": "Execute Python",
                "events": [{"title": "Execution error", "detail": str(exc), "status": "error"}],
                "message": f"Python execution error: {exc}",
                "success": False,
            }

    def execute_shell(self, command: str, cwd: str = "", timeout: int = 30) -> Dict[str, object]:
        """Execute a shell command (mock mode runs in subprocess with safety checks)."""
        if not command or not command.strip():
            return {"title": "Execute Shell", "events": [{"title": "Empty command", "detail": "command is required", "status": "error"}],
                    "message": "Execute Shell failed: command is required.", "success": False}

        # Security check
        dangerous = self._check_shell_safety(command)
        if dangerous:
            return {"title": "Execute Shell", "events": [{"title": "Security check", "detail": dangerous, "status": "error"}],
                    "message": f"Command rejected: {dangerous}", "success": False}

        timeout = max(1, min(timeout, 120))
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd or None,
            )
            stdout = result.stdout[:3000] if result.stdout else ""
            stderr = result.stderr[:1000] if result.stderr else ""
            if result.returncode != 0:
                return {
                    "title": "Execute Shell",
                    "events": [{"title": "Command failed", "detail": f"exit code {result.returncode}", "status": "error"}],
                    "message": f"Command exited with code {result.returncode}.\nstdout:\n```\n{stdout}\n```\nstderr:\n```\n{stderr}\n```",
                    "success": False,
                }
            return {
                "title": "Execute Shell",
                "events": [{"title": "Command executed", "detail": f"exit code 0, {len(stdout)} chars output", "status": "success"}],
                "message": f"Command output:\n```\n{stdout}\n```",
                "success": True,
            }
        except subprocess.TimeoutExpired:
            return {
                "title": "Execute Shell",
                "events": [{"title": "Timeout", "detail": f"Command timed out after {timeout}s", "status": "error"}],
                "message": f"Command timed out after {timeout} seconds.",
                "success": False,
            }
        except Exception as exc:
            return {
                "title": "Execute Shell",
                "events": [{"title": "Execution error", "detail": str(exc), "status": "error"}],
                "message": f"Shell execution error: {exc}",
                "success": False,
            }

    # ------------------------------------------------------------------
    # File / undo tools
    # ------------------------------------------------------------------

    def save_hip(self, file_path: str = "") -> Dict[str, object]:
        return {
            "title": "Save HIP",
            "events": [{"title": "Mock save", "detail": file_path or "current path", "status": "success"}],
            "message": f"Mock mode: would save HIP file to `{file_path or 'current path'}`.",
            "success": True,
        }

    def undo_redo(self, action: str = "undo") -> Dict[str, object]:
        if action not in ("undo", "redo"):
            return {"title": "Undo/Redo", "events": [{"title": "Invalid action", "detail": f'action must be "undo" or "redo", got "{action}"', "status": "error"}],
                    "message": f"Invalid action: {action}", "success": False}
        return {
            "title": "Undo/Redo",
            "events": [{"title": f"Mock {action}", "detail": action, "status": "success"}],
            "message": f"Mock mode: would perform {action}.",
            "success": True,
        }

    # ------------------------------------------------------------------
    # Error fix / code apply
    # ------------------------------------------------------------------

    def fix_error_preview(self, thinking_level: str) -> Dict[str, object]:
        return {
            "title": "自动修复错误预演",
            "events": [
                {"title": "收集错误", "detail": "VEX unknown function: fitramge", "status": "success"},
                {"title": "分析原因", "detail": "Likely typo. Correct function is fitrange.", "status": "success"},
                {"title": "生成修复", "detail": "Replace fitramge(...) with fitrange(...).", "status": "success"},
                {"title": "验证", "detail": "Mock cook succeeded after replacement.", "status": "success"},
            ],
            "message": f"按「{thinking_level}」档位完成自动修复预演：把 `fitramge` 修正为 `fitrange`，并模拟 cook 通过。",
        }

    def error_fix_context(self) -> Dict[str, object]:
        return {"ok": False, "message": "No editable error node found in mock mode."}

    def apply_code_to_fix_target(self, fix_context: Dict[str, object], code: str) -> Dict[str, object]:
        target = fix_context.get("target_node", "")
        parm = fix_context.get("code_parm", "")
        return {
            "title": "Apply model fix",
            "events": [{"title": "Mock apply", "detail": f"{target}.{parm} = <code>", "status": "success"}],
            "message": f"Mock mode: would apply code to `{target}.{parm}`.",
            "success": True,
        }

    # ------------------------------------------------------------------
    # Mock helper
    # ------------------------------------------------------------------

    def mock_chat_response(
        self,
        prompt: str,
        thinking_level: str,
        provider: str,
        context: Dict[str, object],
        image_paths: Optional[List[str]] = None,
    ) -> str:
        image_paths = image_paths or []
        image_note = ""
        if image_paths:
            image_note = (
                f"\n\n图片输入：收到 {len(image_paths)} 张图片。当前前端已保存附件路径并显示缩略图；"
                "接入视觉模型后会把图片作为多模态输入发送给模型识别。"
            )
        return (
            f"我已按「{thinking_level}」思考档位处理你的请求。\n\n"
            f"当前使用 provider: {provider}。\n"
            f"当前网络是 `{context.get('network')}`，选中节点是 "
            f"`{', '.join(context.get('selected_nodes', [])) or 'none'}`。"
            f"{image_note}\n\n"
            "这是前端预览回复：下一阶段会接入真实模型、视觉识别和流式工具调用。"
        )

    def navigate_to_node(self, node_path: str) -> Dict[str, object]:
        return {
            "ok": True,
            "message": f"Mock mode focused node: {node_path}",
        }

    # ------------------------------------------------------------------
    # Security helpers
    # ------------------------------------------------------------------

    _PYTHON_DANGEROUS_PATTERNS = [
        (r"\bos\.remove\b", "os.remove is blocked"),
        (r"\bos\.rmdir\b", "os.rmdir is blocked"),
        (r"\bshutil\.rmtree\b", "shutil.rmtree is blocked"),
        (r"\bos\.system\b", "os.system is blocked"),
        (r"\bsubprocess\b", "subprocess is blocked"),
        (r"\b__import__\b", "__import__ is blocked"),
        (r"\bhou\.exit\b", "hou.exit is blocked"),
        (r"\bhou\.hipFile\.clear\b", "hou.hipFile.clear is blocked"),
    ]

    _SHELL_DANGEROUS_PATTERNS = [
        (r"\brm\s+-rf\b", "rm -rf is blocked"),
        (r"\bformat\s+[A-Za-z]:", "disk format is blocked"),
        (r"\bshutdown\b", "shutdown is blocked"),
        (r"\bsudo\b", "sudo is blocked"),
        (r"\breg\s+(delete|add)\b", "registry modification is blocked"),
    ]

    def _check_python_safety(self, code: str) -> str:
        import re
        for pattern, reason in self._PYTHON_DANGEROUS_PATTERNS:
            if re.search(pattern, code):
                return reason
        return ""

    def _check_shell_safety(self, command: str) -> str:
        import re
        for pattern, reason in self._SHELL_DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return reason
        return ""
