"""Thin Houdini HOM adapter used when the panel runs inside Houdini.

Overrides mock methods with real hou API calls. Every method returns the
unified dict format: {"title", "events", "message", "success"}.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import contextlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from houdini_ai_agent.adapters.mock_houdini import MockHoudiniAdapter


class HoudiniAdapter(MockHoudiniAdapter):
    name = "Houdini"

    def __init__(self):
        import hou  # type: ignore

        self.hou = hou

    def get_session_storage_dir(self):
        hou = self.hou
        try:
            if hou.hipFile.isNewFile():
                return None
            hip_path = Path(hou.hipFile.path())
            if not hip_path.exists() or hip_path.name.lower() == "untitled.hip":
                return None
            return hip_path.parent / "Agent"
        except Exception:
            return None

    def navigate_to_node(self, node_path: str) -> Dict[str, object]:
        hou = self.hou
        node = hou.node(node_path)
        if node is None:
            return {"ok": False, "message": f"Node not found: {node_path}"}
        try:
            node.setSelected(True, clear_all_selected=True)
        except Exception:
            pass
        try:
            editor = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
            if editor is not None:
                editor.setPwd(node.parent())
                try:
                    editor.homeToSelection()
                except Exception:
                    pass
        except Exception:
            pass
        return {"ok": True, "message": f"Focused node: {node.path()}"}

    def _set_display_render_flags(self, node) -> List[Dict[str, str]]:
        events: List[Dict[str, str]] = []
        for method_name, label in (("setDisplayFlag", "display"), ("setRenderFlag", "render")):
            setter = getattr(node, method_name, None)
            if setter is None:
                events.append({"title": "跳过节点标志", "detail": f"{node.path()} does not support {label} flag.", "status": "info"})
                continue
            try:
                setter(True)
            except Exception as exc:
                events.append({"title": "设置节点标志失败", "detail": f"{label}: {exc}", "status": "warning"})
        return events

    def get_context(self) -> Dict[str, object]:
        hou = self.hou
        selected = hou.selectedNodes()
        selected_paths = [node.path() for node in selected]
        current_network = self._current_network().path()
        errors: List[Dict[str, str]] = []
        error_nodes = list(selected)
        try:
            current_network_node = self._current_network()
            error_nodes.extend(current_network_node.children())
            error_nodes.extend(current_network_node.allSubChildren())
        except Exception:
            pass
        seen_error_nodes = set()
        for node in error_nodes:
            if node.path() in seen_error_nodes:
                continue
            seen_error_nodes.add(node.path())
            for message in node.errors():
                errors.append({"node": node.path(), "message": message, "severity": "error"})
            for message in node.warnings():
                errors.append({"node": node.path(), "message": message, "severity": "warning"})

        return {
            "hip_file": hou.hipFile.path(),
            "network": current_network,
            "selected_nodes": selected_paths,
            "viewport": self._viewport_summary(),
            "errors": errors,
            "summary": self._scene_summary(selected_paths, errors),
        }

    def analyze_scene(self, thinking_level: str) -> Dict[str, object]:
        hou = self.hou
        network = self._current_network()
        children = network.children()
        selected = hou.selectedNodes()
        node_preview = ", ".join(f"{node.name()}:{node.type().name()}" for node in children[:10]) or "No child nodes"
        return {
            "title": "分析工程",
            "events": [
                {"title": "读取网络", "detail": network.path(), "status": "success"},
                {"title": "统计节点", "detail": f"{len(children)} child node(s), {len(selected)} selected node(s).", "status": "success"},
                {"title": "节点预览", "detail": node_preview, "status": "success"},
            ],
            "message": (
                f"当前网络：`{network.path()}`\n"
                f"子节点数量：{len(children)}\n"
                f"当前选中：{', '.join(node.path() for node in selected) or 'none'}\n"
                f"前 10 个节点预览：{node_preview}"
            ),
        }

    def inspect_selection(self, thinking_level: str) -> Dict[str, object]:
        hou = self.hou
        selected = hou.selectedNodes()
        if not selected:
            return {
                "title": "查看选中节点",
                "events": [{"title": "读取选择", "detail": "No nodes are selected.", "status": "warning"}],
                "message": "当前没有选中节点。请在网络编辑器里选择一个节点后再试。",
            }

        node = selected[0]
        parms = []
        for parm in node.parms()[:12]:
            try:
                parms.append(f"{parm.name()}={parm.eval()}")
            except Exception:
                parms.append(f"{parm.name()}=<unreadable>")

        return {
            "title": "查看选中节点",
            "events": [
                {"title": "读取选择", "detail": node.path(), "status": "success"},
                {"title": "节点类型", "detail": node.type().nameWithCategory(), "status": "success"},
                {"title": "读取参数", "detail": ", ".join(parms) or "No parameters", "status": "success"},
            ],
            "message": f"选中节点：`{node.path()}`\n类型：`{node.type().nameWithCategory()}`\n参数预览：{', '.join(parms[:8])}",
        }

    def create_node_preview(self, thinking_level: str, request_text: str = "") -> Dict[str, object]:
        hou = self.hou
        events: List[Dict[str, str]] = []
        created_node = None
        requested_type = self._node_type_from_text(request_text)
        try:
            with hou.undos.group("Houdini AI Agent Create Node"):
                selected = hou.selectedNodes()
                if requested_type:
                    parent = selected[-1].parent() if selected else self._current_network()
                    if parent.childTypeCategory().name() == "Object":
                        geo = parent.createNode("geo", node_name=f"agent_{requested_type}_geo")
                        file_node = geo.node("file1")
                        if file_node is not None:
                            try:
                                file_node.destroy()
                            except Exception:
                                pass
                        created_node = geo.createNode(requested_type, node_name=f"agent_{requested_type}1")
                        geo.layoutChildren()
                        geo.moveToGoodPosition()
                        events.append({"title": "创建 Geometry 容器", "detail": geo.path(), "status": "success"})
                    else:
                        created_node = parent.createNode(requested_type, node_name=f"agent_{requested_type}1")
                        parent.layoutChildren()
                    events.extend(self._set_display_render_flags(created_node))
                    created_node.moveToGoodPosition()
                    created_node.setSelected(True, clear_all_selected=True)
                    events.append({"title": "创建指定节点", "detail": f"{created_node.path()} ({requested_type})", "status": "success"})
                elif selected:
                    source = selected[-1]
                    created_node = source.createOutputNode("null", node_name="OUT_AGENT_PREVIEW")
                    events.extend(self._set_display_render_flags(created_node))
                    created_node.moveToGoodPosition()
                    source.parent().layoutChildren()
                    created_node.setSelected(True, clear_all_selected=True)
                    events.append({"title": "创建输出节点", "detail": f"{created_node.path()} from {source.path()}", "status": "success"})
                else:
                    network = self._current_network()
                    if network.childTypeCategory().name() == "Object":
                        geo = network.createNode("geo", node_name="agent_preview_geo")
                        file_node = geo.node("file1")
                        if file_node is not None:
                            try:
                                file_node.destroy()
                            except Exception:
                                pass
                        created_node = geo.createNode("null", node_name="OUT_AGENT_PREVIEW")
                        events.extend(self._set_display_render_flags(created_node))
                        geo.layoutChildren()
                        geo.moveToGoodPosition()
                        created_node.setSelected(True, clear_all_selected=True)
                        events.append({"title": "创建 Geometry 容器", "detail": geo.path(), "status": "success"})
                        events.append({"title": "创建输出节点", "detail": created_node.path(), "status": "success"})
                    else:
                        created_node = network.createNode("null", node_name="OUT_AGENT_PREVIEW")
                        events.extend(self._set_display_render_flags(created_node))
                        created_node.moveToGoodPosition()
                        network.layoutChildren()
                        created_node.setSelected(True, clear_all_selected=True)
                        events.append({"title": "创建节点", "detail": created_node.path(), "status": "success"})
        except Exception as exc:
            return {
                "title": "创建节点",
                "events": events + [{"title": "创建失败", "detail": str(exc), "status": "error"}],
                "message": f"创建节点失败：{exc}",
            }

        return {
            "title": "创建节点",
            "events": events,
            "message": f"已创建节点：`{created_node.path()}`" if created_node is not None else "没有创建任何节点。",
        }

    def create_node(self, node_type: str, node_name: str = "", parent_path: str = "") -> Dict[str, object]:
        hou = self.hou
        node_type = (node_type or "null").strip()
        node_name = (node_name or "").strip()
        parent_path = (parent_path or "").strip()
        events: List[Dict[str, str]] = []
        created_node = None
        try:
            with hou.undos.group("Houdini AI Agent Create Node"):
                selected = hou.selectedNodes()
                parent = hou.node(parent_path) if parent_path else None
                if parent is None:
                    parent = selected[-1].parent() if selected else self._current_network()

                if parent.childTypeCategory().name() == "Object" and node_type != "geo":
                    geo = parent.createNode("geo", node_name=node_name or f"agent_{node_type}_geo")
                    file_node = geo.node("file1")
                    if file_node is not None:
                        try:
                            file_node.destroy()
                        except Exception:
                            pass
                    created_node = geo.createNode(node_type, node_name=f"agent_{node_type}1")
                    geo.layoutChildren()
                    geo.moveToGoodPosition()
                    events.append({"title": "Create geometry container", "detail": geo.path(), "status": "success"})
                else:
                    created_node = parent.createNode(node_type, node_name=node_name or f"agent_{node_type}1")
                    parent.layoutChildren()

                events.extend(self._set_display_render_flags(created_node))
                created_node.moveToGoodPosition()
                created_node.setSelected(True, clear_all_selected=True)
                events.append({"title": "Create node", "detail": f"{created_node.path()} ({node_type})", "status": "success"})
        except Exception as exc:
            return {
                "title": "Create node",
                "events": events + [{"title": "Create failed", "detail": str(exc), "status": "error"}],
                "message": f"Create node failed: {exc}",
            }

        return {
            "title": "Create node",
            "events": events,
            "message": f"Created node: `{created_node.path()}`" if created_node is not None else "No node was created.",
        }

    def set_node_parameter(self, target_node: str, parm_name: str, value) -> Dict[str, object]:
        hou = self.hou
        target_node = (target_node or "").strip()
        parm_name = (parm_name or "").strip()
        if not target_node or not parm_name:
            return {
                "title": "Set parameter",
                "events": [{"title": "Missing parameter target", "detail": f"{target_node}.{parm_name}", "status": "error"}],
                "message": "Set parameter failed: target node and parameter name are required.",
            }
        node = hou.node(target_node)
        if node is None:
            return {
                "title": "Set parameter",
                "events": [{"title": "Node not found", "detail": target_node, "status": "error"}],
                "message": f"Set parameter failed: `{target_node}` was not found.",
            }
        parm = node.parm(parm_name)
        if parm is None:
            return {
                "title": "Set parameter",
                "events": [{"title": "Parameter not found", "detail": f"{target_node}.{parm_name}", "status": "error"}],
                "message": f"Set parameter failed: `{parm_name}` was not found on `{target_node}`.",
            }
        try:
            with hou.undos.group("Houdini AI Agent Set Parameter"):
                parm.set(value)
        except Exception as exc:
            return {
                "title": "Set parameter",
                "events": [{"title": "Set parameter failed", "detail": str(exc), "status": "error"}],
                "message": f"Set parameter failed: {exc}",
            }
        return {
            "title": "Set parameter",
            "events": [{"title": "Set parameter", "detail": f"{parm.path()} = {value}", "status": "success"}],
            "message": f"Set `{parm.path()}` to `{value}`.",
        }

    def fix_error_preview(self, thinking_level: str) -> Dict[str, object]:
        hou = self.hou
        selected = hou.selectedNodes()
        if not selected:
            return {
                "title": "修复错误",
                "events": [{"title": "缺少选择", "detail": "Please select a node with an error first.", "status": "warning"}],
                "message": "当前没有选中节点。请先选中一个报错节点。",
            }
        selected_node = selected[-1]
        node = self._find_fix_target(selected_node) or selected_node
        events: List[Dict[str, str]] = [{"title": "读取节点", "detail": selected_node.path(), "status": "success"}]
        if node.path() != selected_node.path():
            events.append({"title": "定位实际报错节点", "detail": node.path(), "status": "success"})
        if not node.errors() and not node.warnings():
            return {
                "title": "修复错误",
                "events": events + [{"title": "未发现错误", "detail": "Selected node has no current errors or warnings.", "status": "warning"}],
                "message": "选中节点当前没有错误或警告。",
            }

        known_replacements = {
            "fitramge": "fitrange",
            "chrnage": "chrange",
            "setprimattribb": "setprimattrib",
        }
        target_parm = self._find_code_parm(node)
        if target_parm is None:
            details = "; ".join(node.errors() or node.warnings())
            return {
                "title": "修复错误",
                "events": events + [{"title": "仅诊断", "detail": details or "No editable code parm found.", "status": "warning"}],
                "message": "已读取错误，但当前节点没有可安全自动修改的代码参数。请查看执行轨迹中的诊断信息。",
            }

        try:
            original = target_parm.unexpandedString()
        except Exception:
            try:
                original = target_parm.evalAsString()
            except Exception:
                original = ""
        updated = original
        applied: List[str] = []
        for old, new in known_replacements.items():
            if old in updated:
                updated = updated.replace(old, new)
                applied.append(f"{old} -> {new}")

        if updated == original:
            syntax_fixed = self._apply_common_code_fixes(updated, list(node.errors()) + list(node.warnings()))
            updated = syntax_fixed["code"]
            applied.extend(syntax_fixed["applied"])

        if updated == original:
            details = "; ".join(node.errors() or node.warnings())
            return {
                "title": "修复错误",
                "events": events + [{"title": "未匹配自动修复规则", "detail": details or target_parm.name(), "status": "warning"}],
                "message": "已识别错误，但当前版本没有匹配到安全的自动修复规则。",
            }

        try:
            with hou.undos.group("Houdini AI Agent Fix Error"):
                target_parm.set(updated)
                events.append({"title": "更新代码参数", "detail": f"{target_parm.path()} | {', '.join(applied)}", "status": "success"})
                try:
                    node.cook(force=True)
                    events.append({"title": "重新 Cook", "detail": "Cook completed after the edit.", "status": "success"})
                except Exception as cook_exc:
                    events.append({"title": "Cook 结果", "detail": str(cook_exc), "status": "warning"})
        except Exception as exc:
            return {
                "title": "修复错误",
                "events": events + [{"title": "修复失败", "detail": str(exc), "status": "error"}],
                "message": f"自动修复失败：{exc}",
            }

        remaining = node.errors()
        message = "已应用自动修复：" + ", ".join(applied)
        if remaining:
            message += f"\n节点仍有错误：{' | '.join(remaining)}"
        else:
            message += "\n节点当前没有错误。"
        return {
            "title": "修复错误",
            "events": events,
            "message": message,
        }

    def capture_viewport_preview(self, thinking_level: str) -> Dict[str, object]:
        capture_path = self._capture_viewport_image()
        if capture_path is None:
            return {
                "title": "捕获视口",
                "events": [
                    {"title": "定位 Scene Viewer", "detail": self._viewport_summary(), "status": "success"},
                    {"title": "截图导出失败", "detail": "Could not write a viewport image file.", "status": "error"},
                ],
                "message": f"当前视口：{self._viewport_summary()}",
            }
        return {
            "title": "捕获视口",
            "events": [
                {"title": "定位 Scene Viewer", "detail": self._viewport_summary(), "status": "success"},
                {"title": "截图导出", "detail": str(capture_path), "status": "success"},
            ],
            "message": f"当前视口：{self._viewport_summary()}\n截图已保存到：`{capture_path}`",
            "image_paths": [str(capture_path)],
        }

    def _viewport_summary(self) -> str:
        hou = self.hou
        try:
            viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
            if viewer is None:
                return "No Scene Viewer found"
            viewport = viewer.curViewport()
            camera = viewport.camera()
            camera_path = camera.path() if camera else "none"
            return f"SceneViewer: {viewport.name()} / camera: {camera_path}"
        except Exception as exc:
            return f"Viewport unavailable: {exc}"

    def _scene_summary(self, selected_paths: List[str], errors: List[Dict[str, str]]) -> str:
        if selected_paths:
            return f"{len(selected_paths)} selected node(s), {len(errors)} warning/error message(s)."
        return f"No selected nodes, {len(errors)} warning/error message(s)."

    def _current_network(self):
        hou = self.hou
        selected = hou.selectedNodes()
        if selected:
            return selected[-1].parent()
        try:
            editor = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
            if editor is not None:
                node = editor.pwd()
                if node is not None:
                    return node
        except Exception:
            pass
        return hou.node("/obj")

    def _find_code_parm(self, node) -> Optional[object]:
        for parm_name in ("snippet", "python", "code", "vexpression", "snippet1"):
            parm = node.parm(parm_name)
            if parm is not None:
                return parm
        return None

    def _node_type_from_text(self, text: str) -> str:
        lowered = text.lower()
        aliases = {
            "box": "box",
            "cube": "box",
            "立方体": "box",
            "盒子": "box",
            "sphere": "sphere",
            "球": "sphere",
            "grid": "grid",
            "平面": "grid",
            "plane": "grid",
            "null": "null",
            "空节点": "null",
            "merge": "merge",
            "transform": "xform",
            "xform": "xform",
            "attribwrangle": "attribwrangle",
            "wrangle": "attribwrangle",
        }
        for keyword, node_type in aliases.items():
            if keyword in lowered or keyword in text:
                return node_type
        return ""

    def error_fix_context(self) -> Dict[str, object]:
        selected = self.hou.selectedNodes()
        selected_node = selected[-1] if selected else None
        node = self._find_fix_target(selected_node) if selected_node is not None else None
        if node is None:
            node = self._find_first_error_node()
        if node is None:
            return {"ok": False, "message": "No editable error node found in the current context."}
        parm = self._find_code_parm(node)
        code = ""
        if parm is not None:
            try:
                code = parm.unexpandedString()
            except Exception:
                try:
                    code = parm.evalAsString()
                except Exception:
                    code = ""
        return {
            "ok": True,
            "selected_node": selected_node.path() if selected_node is not None else "",
            "target_node": node.path(),
            "target_type": node.type().nameWithCategory(),
            "code_parm": parm.name() if parm is not None else "",
            "code": code,
            "errors": list(node.errors()),
            "warnings": list(node.warnings()),
        }

    def apply_code_to_fix_target(self, fix_context: Dict[str, object], code: str) -> Dict[str, object]:
        hou = self.hou
        target_path = str(fix_context.get("target_node", "") or "")
        parm_name = str(fix_context.get("code_parm", "") or "")
        if not target_path or not parm_name:
            return {
                "title": "Apply model fix",
                "events": [{"title": "Missing target", "detail": "Model fix has no target node or code parm.", "status": "warning"}],
                "message": "Model returned code, but there is no remembered editable Houdini parameter to update.",
            }

        node = hou.node(target_path)
        if node is None:
            return {
                "title": "Apply model fix",
                "events": [{"title": "Missing node", "detail": target_path, "status": "error"}],
                "message": f"Could not apply model fix because `{target_path}` no longer exists.",
            }
        parm = node.parm(parm_name)
        if parm is None:
            return {
                "title": "Apply model fix",
                "events": [{"title": "Missing parameter", "detail": f"{target_path}.{parm_name}", "status": "error"}],
                "message": f"Could not apply model fix because `{parm_name}` no longer exists on `{target_path}`.",
            }

        events: List[Dict[str, str]] = []
        try:
            with hou.undos.group("Houdini AI Agent Apply Model Fix"):
                parm.set(code)
                events.append({"title": "Apply model code", "detail": parm.path(), "status": "success"})
                try:
                    node.cook(force=True)
                    events.append({"title": "Cook fixed node", "detail": node.path(), "status": "success"})
                except Exception as cook_exc:
                    events.append({"title": "Cook result", "detail": str(cook_exc), "status": "warning"})
        except Exception as exc:
            return {
                "title": "Apply model fix",
                "events": events + [{"title": "Apply failed", "detail": str(exc), "status": "error"}],
                "message": f"Model fix could not be applied: {exc}",
            }

        remaining = list(node.errors()) + list(node.warnings())
        if remaining:
            message = "Applied the model code block, but the node still reports:\n" + "\n".join(remaining)
            status = "warning"
        else:
            message = f"Applied the model code block to `{parm.path()}` and the node has no current errors."
            status = "success"
        events.append({"title": "Validate model fix", "detail": " | ".join(remaining) if remaining else "No current errors.", "status": status})
        return {"title": "Apply model fix", "events": events, "message": message}

    def _find_fix_target(self, node):
        candidates = [node]
        try:
            candidates.extend(node.allSubChildren())
        except Exception:
            pass
        for candidate in candidates:
            try:
                if candidate.errors() or candidate.warnings():
                    if self._find_code_parm(candidate) is not None:
                        return candidate
            except Exception:
                continue
        return None

    def _find_first_error_node(self):
        candidates = []
        try:
            network = self._current_network()
            candidates.extend(network.children())
            candidates.extend(network.allSubChildren())
        except Exception:
            return None
        for candidate in candidates:
            try:
                if (candidate.errors() or candidate.warnings()) and self._find_code_parm(candidate) is not None:
                    return candidate
            except Exception:
                continue
        return None

    def _apply_common_code_fixes(self, code: str, messages: List[str]) -> Dict[str, object]:
        updated = code
        applied: List[str] = []

        combined = " ".join(messages)
        if "expecting ';'" in combined:
            lines = updated.splitlines()
            changed = False
            for index in range(len(lines) - 1):
                current = lines[index].rstrip()
                next_line = lines[index + 1].strip()
                if not current.strip():
                    continue
                if next_line == "}":
                    stripped = current.strip()
                    if not stripped.endswith((";", "{", "}", ":", ",")):
                        lines[index] = current + ";"
                        changed = True
            if changed:
                updated = "\n".join(lines)
                applied.append("added missing semicolon before closing brace")

        if "unexpected '}'" in combined or "unmatched" in combined.lower():
            balance = 0
            lines = updated.splitlines()
            removable_indexes: List[int] = []
            for index, line in enumerate(lines):
                for char in line:
                    if char == "{":
                        balance += 1
                    elif char == "}":
                        if balance == 0:
                            removable_indexes.append(index)
                            break
                        balance -= 1
            if removable_indexes:
                filtered = [line for index, line in enumerate(lines) if index not in removable_indexes]
                updated = "\n".join(filtered)
                applied.append("removed unmatched closing brace")
            elif balance < 0:
                updated = re.sub(r"\n?\s*\}\s*$", "", updated)
                if updated != code:
                    applied.append("removed trailing closing brace")

        return {"code": updated, "applied": applied}

    def _capture_viewport_image(self) -> Optional[Path]:
        hou = self.hou
        try:
            viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
            if viewer is None:
                return None
            viewport = viewer.curViewport()
            frame = int(round(hou.frame()))
            output_dir = self._capture_dir()
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"viewport_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{frame:04d}.png"
            settings = viewer.flipbookSettings().stash()
            settings.frameRange((frame, frame))
            settings.output(str(output_path))
            settings.outputToMPlay(False)
            settings.useResolution(False)
            viewer.flipbook(viewport, settings)
            return output_path if output_path.exists() else None
        except Exception:
            return None

    def _capture_dir(self) -> Path:
        storage_dir = self.get_session_storage_dir()
        if storage_dir is None:
            return Path.home() / "houdini_ai_agent_captures"
        return Path(storage_dir) / "captures"

    # ==================================================================
    # NEW: Extended tool methods
    # ==================================================================

    # -- Network structure / analysis (read-only) --

    def get_network_structure(self, network_path: str = "") -> Dict[str, object]:
        """Get node network topology: names, types, connections."""
        hou = self.hou
        events: List[Dict[str, str]] = []
        try:
            parent = hou.node(network_path) if network_path else self._current_network()
            if parent is None:
                parent = hou.node("/obj")
            network_path = parent.path()
            children = parent.children()
            events.append({"title": "Read network", "detail": f"{network_path} ({len(children)} nodes)", "status": "success"})

            lines: List[str] = []
            for child in children:
                inputs = []
                for i in range(child.numInputs()):
                    conn = child.input(i)
                    if conn:
                        inputs.append(conn.name())
                flags = []
                try:
                    if child.isDisplayFlagSet():
                        flags.append("D")
                    if child.isRenderFlagSet():
                        flags.append("R")
                    if child.isBypassed():
                        flags.append("B")
                except Exception:
                    pass
                flag_str = f" [{','.join(flags)}]" if flags else ""
                input_str = f" ← {', '.join(inputs)}" if inputs else ""
                type_name = child.type().name()
                errs = list(child.errors())
                err_str = f" ⚠ {len(errs)} error(s)" if errs else ""
                lines.append(f"  {child.name()} [{type_name}]{flag_str}{input_str}{err_str}")

            structure = f"Network `{network_path}`:\n" + "\n".join(lines)
            return {"title": "Get network structure", "events": events, "message": structure, "success": True}
        except Exception as exc:
            return {"title": "Get network structure", "events": events + [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Failed to read network: {exc}", "success": False}

    def get_node_parameters(self, node_path: str, page: int = 1) -> Dict[str, object]:
        """Get node parameters with type, current value."""
        hou = self.hou
        events: List[Dict[str, str]] = []
        if not node_path:
            return {"title": "Get node parameters", "events": [{"title": "Missing path", "detail": "node_path is required", "status": "error"}],
                    "message": "node_path is required.", "success": False}
        try:
            node = hou.node(node_path)
            if node is None:
                return {"title": "Get node parameters", "events": [{"title": "Node not found", "detail": node_path, "status": "error"}],
                        "message": f"Node not found: {node_path}", "success": False}

            type_name = node.type().nameWithCategory()
            events.append({"title": "Read node", "detail": f"{node.path()} ({type_name})", "status": "success"})

            flags_info = []
            try:
                if node.isDisplayFlagSet():
                    flags_info.append("display")
                if node.isRenderFlagSet():
                    flags_info.append("render")
                if node.isBypassed():
                    flags_info.append("bypass")
            except Exception:
                pass

            lines = [f"Node `{node.path()}` ({type_name})"]
            if flags_info:
                lines.append(f"Flags: {', '.join(flags_info)}")
            errs = list(node.errors())
            if errs:
                lines.append(f"Errors: {'; '.join(errs)}")

            parms = node.parms()
            lines.append(f"Parameters ({len(parms)} total):")
            for parm in parms[:30]:
                try:
                    name = parm.name()
                    pt = parm.parmTemplate()
                    ptype = pt.type().name() if pt else "unknown"
                    try:
                        val = parm.evalAsString()
                    except Exception:
                        val = "<non-evaluable>"
                    lines.append(f"  {name} ({ptype}) = {val}")
                except Exception:
                    continue
            if len(parms) > 30:
                lines.append(f"  ... and {len(parms) - 30} more parameters")

            return {"title": "Get node parameters",
                    "events": events + [{"title": "Parameters read", "detail": f"{len(parms)} parameters", "status": "success"}],
                    "message": "\n".join(lines), "success": True}
        except Exception as exc:
            return {"title": "Get node parameters", "events": events + [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Failed: {exc}", "success": False}

    def list_children(self, network_path: str = "", recursive: bool = False, page: int = 1) -> Dict[str, object]:
        """List child nodes of a network."""
        hou = self.hou
        events: List[Dict[str, str]] = []
        try:
            parent = hou.node(network_path) if network_path else self._current_network()
            if parent is None:
                parent = hou.node("/obj")
            path = parent.path()
            children = list(parent.allSubChildren()) if recursive else list(parent.children())
            events.append({"title": "List children", "detail": f"{path}: {len(children)} nodes", "status": "success"})

            lines = [f"Children of `{path}` ({len(children)} nodes, recursive={recursive}):"]
            for i, child in enumerate(children[:50]):
                type_name = child.type().name()
                flags = ""
                try:
                    f_parts = []
                    if child.isDisplayFlagSet():
                        f_parts.append("D")
                    if child.isBypassed():
                        f_parts.append("B")
                    if f_parts:
                        flags = f" [{','.join(f_parts)}]"
                except Exception:
                    pass
                indent = "  " if recursive else ""
                lines.append(f"{indent}{i + 1}. {child.name()} [{type_name}]{flags}")
            if len(children) > 50:
                lines.append(f"... and {len(children) - 50} more nodes")

            return {"title": "List children", "events": events, "message": "\n".join(lines), "success": True}
        except Exception as exc:
            return {"title": "List children", "events": events + [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Failed: {exc}", "success": False}

    def check_errors(self, node_path: str = "") -> Dict[str, object]:
        """Check cooking errors and warnings for a node."""
        hou = self.hou
        events: List[Dict[str, str]] = []
        try:
            node = hou.node(node_path) if node_path else None
            if node is None:
                selected = hou.selectedNodes()
                node = selected[0] if selected else self._current_network()
            events.append({"title": "Check node", "detail": node.path(), "status": "success"})

            errors = list(node.errors())
            warnings = list(node.warnings())
            lines = [f"Node `{node.path()}` error check:"]
            if errors:
                lines.append(f"Errors ({len(errors)}):")
                for e in errors:
                    lines.append(f"  - {e}")
            if warnings:
                lines.append(f"Warnings ({len(warnings)}):")
                for w in warnings:
                    lines.append(f"  - {w}")
            if not errors and not warnings:
                lines.append("No errors or warnings found.")

            status = "warning" if (errors or warnings) else "success"
            events.append({"title": f"{len(errors)} errors, {len(warnings)} warnings", "detail": node.path(), "status": status})
            return {"title": "Check errors", "events": events, "message": "\n".join(lines), "success": True}
        except Exception as exc:
            return {"title": "Check errors", "events": events + [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Failed: {exc}", "success": False}

    def get_node_positions(self, network_path: str = "", node_paths: Optional[List[str]] = None) -> Dict[str, object]:
        """Get node positions in the network editor."""
        hou = self.hou
        events: List[Dict[str, str]] = []
        try:
            parent = hou.node(network_path) if network_path else self._current_network()
            if parent is None:
                parent = hou.node("/obj")
            targets = [hou.node(p) for p in node_paths if hou.node(p)] if node_paths else list(parent.children())
            events.append({"title": "Read positions", "detail": f"{len(targets)} nodes", "status": "success"})

            lines = [f"Node positions in `{parent.path()}`:"]
            for node in targets:
                try:
                    pos = node.position()
                    lines.append(f"  {node.name()} ({node.type().name()}): ({pos.x():.2f}, {pos.y():.2f})")
                except Exception:
                    lines.append(f"  {node.name()}: position unavailable")
            return {"title": "Get node positions", "events": events, "message": "\n".join(lines), "success": True}
        except Exception as exc:
            return {"title": "Get node positions", "events": events + [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Failed: {exc}", "success": False}

    # -- Node mutation tools --

    def delete_node(self, node_path: str) -> Dict[str, object]:
        """Delete a node by its path."""
        hou = self.hou
        if not node_path:
            return {"title": "Delete node", "events": [{"title": "Missing path", "detail": "node_path is required", "status": "error"}],
                    "message": "Delete node failed: node_path is required.", "success": False}
        try:
            node = hou.node(node_path)
            if node is None:
                return {"title": "Delete node", "events": [{"title": "Node not found", "detail": node_path, "status": "error"}],
                        "message": f"Node not found: {node_path}", "success": False}
            with hou.undos.group("Houdini AI Agent Delete Node"):
                node.destroy()
            return {"title": "Delete node", "events": [{"title": "Deleted", "detail": node_path, "status": "success"}],
                    "message": f"Deleted node `{node_path}`.", "success": True}
        except Exception as exc:
            return {"title": "Delete node", "events": [{"title": "Delete failed", "detail": str(exc), "status": "error"}],
                    "message": f"Delete node failed: {exc}", "success": False}

    def connect_nodes(self, from_path: str, to_path: str, input_index: int = 0) -> Dict[str, object]:
        """Connect output of from_path node to input of to_path node."""
        hou = self.hou
        if not from_path or not to_path:
            return {"title": "Connect nodes", "events": [{"title": "Missing paths", "detail": "from_path and to_path required", "status": "error"}],
                    "message": "Connect nodes failed: from_path and to_path are required.", "success": False}
        try:
            output_node = hou.node(from_path)
            input_node = hou.node(to_path)
            if output_node is None:
                return {"title": "Connect nodes", "events": [{"title": "Node not found", "detail": from_path, "status": "error"}],
                        "message": f"Output node not found: {from_path}", "success": False}
            if input_node is None:
                return {"title": "Connect nodes", "events": [{"title": "Node not found", "detail": to_path, "status": "error"}],
                        "message": f"Input node not found: {to_path}", "success": False}
            with hou.undos.group("Houdini AI Agent Connect Nodes"):
                input_node.setInput(input_index, output_node)
            return {"title": "Connect nodes",
                    "events": [{"title": "Connected", "detail": f"{from_path} → {to_path}[{input_index}]", "status": "success"}],
                    "message": f"Connected `{from_path}` output to `{to_path}` input {input_index}.", "success": True}
        except Exception as exc:
            return {"title": "Connect nodes", "events": [{"title": "Connect failed", "detail": str(exc), "status": "error"}],
                    "message": f"Connect failed: {exc}", "success": False}

    def copy_node(self, source_path: str, dest_network: str = "", new_name: str = "") -> Dict[str, object]:
        """Copy/clone a node to a new location."""
        hou = self.hou
        if not source_path:
            return {"title": "Copy node", "events": [{"title": "Missing source", "detail": "source_path required", "status": "error"}],
                    "message": "Copy node failed: source_path is required.", "success": False}
        try:
            source = hou.node(source_path)
            if source is None:
                return {"title": "Copy node", "events": [{"title": "Node not found", "detail": source_path, "status": "error"}],
                        "message": f"Source node not found: {source_path}", "success": False}
            dest_parent = hou.node(dest_network) if dest_network else source.parent()
            if dest_parent is None:
                return {"title": "Copy node", "events": [{"title": "Dest not found", "detail": dest_network, "status": "error"}],
                        "message": f"Destination network not found: {dest_network}", "success": False}
            name = new_name or f"{source.name()}_copy"
            with hou.undos.group("Houdini AI Agent Copy Node"):
                new_node = dest_parent.createNode(source.type().name(), node_name=name)
                for parm in source.parms():
                    try:
                        new_parm = new_node.parm(parm.name())
                        if new_parm is not None:
                            new_parm.set(parm.eval())
                    except Exception:
                        continue
                new_node.moveToGoodPosition()
            return {"title": "Copy node",
                    "events": [{"title": "Copied", "detail": f"{source_path} → {new_node.path()}", "status": "success"}],
                    "message": f"Copied `{source_path}` to `{new_node.path()}`.", "success": True}
        except Exception as exc:
            return {"title": "Copy node", "events": [{"title": "Copy failed", "detail": str(exc), "status": "error"}],
                    "message": f"Copy failed: {exc}", "success": False}

    def batch_set_parameters(self, node_paths: List[str], param_name: str, value: Any = None) -> Dict[str, object]:
        """Set the same parameter on multiple nodes."""
        hou = self.hou
        if not node_paths or not param_name:
            return {"title": "Batch set parameters", "events": [{"title": "Missing args", "detail": "node_paths and param_name required", "status": "error"}],
                    "message": "Batch set failed: node_paths and param_name required.", "success": False}
        events: List[Dict[str, str]] = []
        successes, failures = [], []
        try:
            with hou.undos.group("Houdini AI Agent Batch Set"):
                for path in node_paths:
                    try:
                        node = hou.node(path)
                        if node is None:
                            failures.append(f"{path}: not found")
                            continue
                        parm = node.parm(param_name)
                        if parm is None:
                            failures.append(f"{path}: param '{param_name}' not found")
                            continue
                        parm.set(value)
                        successes.append(path)
                    except Exception as exc:
                        failures.append(f"{path}: {exc}")
            events.append({"title": "Batch set", "detail": f"{len(successes)} ok, {len(failures)} failed",
                           "status": "success" if not failures else "warning"})
            msg = f"Set `{param_name}` = `{value}` on {len(successes)} node(s)."
            if failures:
                msg += f"\nFailures: {'; '.join(failures[:5])}"
            return {"title": "Batch set parameters", "events": events, "message": msg, "success": len(successes) > 0}
        except Exception as exc:
            return {"title": "Batch set parameters", "events": [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Batch set failed: {exc}", "success": False}

    def find_nodes_by_param(self, param_name: str, value: str = "", network_path: str = "", recursive: bool = True) -> Dict[str, object]:
        """Search nodes by parameter value."""
        hou = self.hou
        if not param_name:
            return {"title": "Find nodes by param", "events": [{"title": "Missing param_name", "detail": "param_name required", "status": "error"}],
                    "message": "Find failed: param_name is required.", "success": False}
        events: List[Dict[str, str]] = []
        try:
            parent = hou.node(network_path) if network_path else self._current_network()
            if parent is None:
                parent = hou.node("/obj")
            nodes = list(parent.allSubChildren()) if recursive else list(parent.children())
            events.append({"title": "Scanning", "detail": f"{len(nodes)} nodes in {parent.path()}", "status": "success"})
            matches = []
            for node in nodes:
                parm = node.parm(param_name)
                if parm is None:
                    continue
                try:
                    current = str(parm.eval())
                    if not value or value in current:
                        matches.append(f"{node.path()} = {current}")
                except Exception:
                    continue
            events.append({"title": "Found", "detail": f"{len(matches)} matches", "status": "success"})
            msg = f"Found {len(matches)} node(s) with `{param_name}`"
            if value:
                msg += f" matching `{value}`"
            msg += ":" + ("\n" + "\n".join(f"  - {m}" for m in matches[:20]) if matches else " (none)")
            return {"title": "Find nodes by param", "events": events, "message": msg, "success": True}
        except Exception as exc:
            return {"title": "Find nodes by param", "events": events + [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Find failed: {exc}", "success": False}

    def set_display_flag(self, node_path: str, display: bool = True, render: bool = True) -> Dict[str, object]:
        """Set display and render flags on a node."""
        hou = self.hou
        if not node_path:
            return {"title": "Set display flag", "events": [{"title": "Missing node_path", "detail": "node_path required", "status": "error"}],
                    "message": "Set display flag failed: node_path is required.", "success": False}
        events: List[Dict[str, str]] = []
        try:
            node = hou.node(node_path)
            if node is None:
                return {"title": "Set display flag", "events": [{"title": "Node not found", "detail": node_path, "status": "error"}],
                        "message": f"Node not found: {node_path}", "success": False}
            with hou.undos.group("Houdini AI Agent Set Flags"):
                flags_set = []
                if display:
                    try:
                        node.setDisplayFlag(True)
                        flags_set.append("display")
                    except Exception:
                        pass
                if render:
                    try:
                        node.setRenderFlag(True)
                        flags_set.append("render")
                    except Exception:
                        pass
            events.append({"title": "Flags set", "detail": f"{node_path}: {', '.join(flags_set)}", "status": "success"})
            return {"title": "Set display flag", "events": events, "message": f"Set `{node_path}` flags: {', '.join(flags_set)}.", "success": True}
        except Exception as exc:
            return {"title": "Set display flag", "events": events + [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Set display flag failed: {exc}", "success": False}

    def layout_nodes(self, network_path: str = "", node_paths: Optional[List[str]] = None, method: str = "auto") -> Dict[str, object]:
        """Auto-layout nodes in the network editor."""
        hou = self.hou
        events: List[Dict[str, str]] = []
        try:
            parent = hou.node(network_path) if network_path else self._current_network()
            if parent is None:
                parent = hou.node("/obj")
            with hou.undos.group("Houdini AI Agent Layout"):
                if node_paths:
                    nodes = [hou.node(p) for p in node_paths if hou.node(p)]
                    if nodes:
                        parent.layoutChildren(items=nodes)
                    events.append({"title": "Layout specific", "detail": f"{len(nodes)} nodes", "status": "success"})
                else:
                    parent.layoutChildren()
                    events.append({"title": "Layout all", "detail": parent.path(), "status": "success"})
            return {"title": "Layout nodes", "events": events,
                    "message": f"Auto-layout completed in `{parent.path()}`.", "success": True}
        except Exception as exc:
            return {"title": "Layout nodes", "events": events + [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Layout failed: {exc}", "success": False}

    # -- Code / execution tools --

    def execute_python(self, code: str) -> Dict[str, object]:
        """Execute Python code in Houdini's Python environment."""
        hou = self.hou
        if not code or not code.strip():
            return {"title": "Execute Python", "events": [{"title": "Empty code", "detail": "code is required", "status": "error"}],
                    "message": "Execute Python failed: code is required.", "success": False}
        dangerous = self._check_python_safety(code)
        if dangerous:
            return {"title": "Execute Python", "events": [{"title": "Security", "detail": dangerous, "status": "error"}],
                    "message": f"Code rejected: {dangerous}", "success": False}
        try:
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                exec(compile(code, "<agent_python>", "exec"), {"hou": hou, "__builtins__": __builtins__})
            result = output.getvalue()
            if not result.strip():
                result = "(no output)"
            if len(result) > 5000:
                result = result[:4500] + "\n... (truncated)"
            return {"title": "Execute Python",
                    "events": [{"title": "Executed", "detail": f"Code ran ({len(code)} chars)", "status": "success"}],
                    "message": f"Python output:\n```\n{result}\n```", "success": True}
        except Exception as exc:
            tb = traceback.format_exc() if hasattr(traceback, 'format_exc') else str(exc)
            return {"title": "Execute Python",
                    "events": [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Python error:\n```\n{tb[:3000]}\n```", "success": False}

    def execute_shell(self, command: str, cwd: str = "", timeout: int = 30) -> Dict[str, object]:
        """Execute a shell command with safety checks."""
        if not command or not command.strip():
            return {"title": "Execute Shell", "events": [{"title": "Empty command", "detail": "command required", "status": "error"}],
                    "message": "Execute Shell failed: command is required.", "success": False}
        dangerous = self._check_shell_safety(command)
        if dangerous:
            return {"title": "Execute Shell", "events": [{"title": "Security", "detail": dangerous, "status": "error"}],
                    "message": f"Command rejected: {dangerous}", "success": False}
        timeout = max(1, min(timeout, 120))
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd or None)
            stdout = result.stdout[:3000] if result.stdout else ""
            stderr = result.stderr[:1000] if result.stderr else ""
            if result.returncode != 0:
                return {"title": "Execute Shell",
                        "events": [{"title": "Failed", "detail": f"exit code {result.returncode}", "status": "error"}],
                        "message": f"Exit code {result.returncode}.\nstdout:\n```\n{stdout}\n```\nstderr:\n```\n{stderr}\n```",
                        "success": False}
            return {"title": "Execute Shell",
                    "events": [{"title": "Executed", "detail": f"exit 0, {len(stdout)} chars", "status": "success"}],
                    "message": f"Output:\n```\n{stdout}\n```", "success": True}
        except subprocess.TimeoutExpired:
            return {"title": "Execute Shell", "events": [{"title": "Timeout", "detail": f"{timeout}s", "status": "error"}],
                    "message": f"Command timed out after {timeout} seconds.", "success": False}
        except Exception as exc:
            return {"title": "Execute Shell", "events": [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Shell error: {exc}", "success": False}

    # -- File / undo tools --

    def save_hip(self, file_path: str = "") -> Dict[str, object]:
        """Save the current HIP file."""
        hou = self.hou
        try:
            target = file_path.strip() if file_path else ""
            with hou.undos.group("Houdini AI Agent Save"):
                if target:
                    hou.hipFile.save(target)
                else:
                    hou.hipFile.save()
            return {"title": "Save HIP",
                    "events": [{"title": "Saved", "detail": target or hou.hipFile.path(), "status": "success"}],
                    "message": f"HIP file saved to `{target or hou.hipFile.path()}`.", "success": True}
        except Exception as exc:
            return {"title": "Save HIP", "events": [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"Save failed: {exc}", "success": False}

    def undo_redo(self, action: str = "undo") -> Dict[str, object]:
        """Perform undo or redo."""
        hou = self.hou
        if action not in ("undo", "redo"):
            return {"title": "Undo/Redo", "events": [{"title": "Invalid action", "detail": f'must be "undo" or "redo"', "status": "error"}],
                    "message": f"Invalid action: {action}", "success": False}
        try:
            if action == "undo":
                hou.undos.performUndo()
            else:
                hou.undos.performRedo()
            return {"title": "Undo/Redo", "events": [{"title": action.capitalize(), "detail": action, "status": "success"}],
                    "message": f"Performed {action}.", "success": True}
        except Exception as exc:
            return {"title": "Undo/Redo", "events": [{"title": "Error", "detail": str(exc), "status": "error"}],
                    "message": f"{action.capitalize()} failed: {exc}", "success": False}


import traceback  # noqa: E402 — needed for execute_python error reporting


def create_best_adapter():
    try:
        import hou  # noqa: F401

        return HoudiniAdapter()
    except Exception:
        return MockHoudiniAdapter()
