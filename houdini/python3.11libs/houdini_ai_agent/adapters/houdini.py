"""Thin Houdini HOM adapter used when the panel runs inside Houdini."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

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

    def get_context(self) -> Dict[str, object]:
        hou = self.hou
        selected = hou.selectedNodes()
        selected_paths = [node.path() for node in selected]
        current_network = self._current_network().path()
        errors: List[Dict[str, str]] = []
        for node in selected:
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

    def create_node_preview(self, thinking_level: str) -> Dict[str, object]:
        hou = self.hou
        events: List[Dict[str, str]] = []
        created_node = None
        try:
            with hou.undos.group("Houdini AI Agent Create Node"):
                selected = hou.selectedNodes()
                if selected:
                    source = selected[-1]
                    created_node = source.createOutputNode("null", node_name="OUT_AGENT_PREVIEW")
                    created_node.setDisplayFlag(True)
                    created_node.setRenderFlag(True)
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
                        created_node.setDisplayFlag(True)
                        created_node.setRenderFlag(True)
                        geo.layoutChildren()
                        geo.moveToGoodPosition()
                        created_node.setSelected(True, clear_all_selected=True)
                        events.append({"title": "创建 Geometry 容器", "detail": geo.path(), "status": "success"})
                        events.append({"title": "创建输出节点", "detail": created_node.path(), "status": "success"})
                    else:
                        created_node = network.createNode("null", node_name="OUT_AGENT_PREVIEW")
                        created_node.setDisplayFlag(True)
                        created_node.setRenderFlag(True)
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

    def fix_error_preview(self, thinking_level: str) -> Dict[str, object]:
        hou = self.hou
        selected = hou.selectedNodes()
        if not selected:
            return {
                "title": "修复错误",
                "events": [{"title": "缺少选择", "detail": "Please select a node with an error first.", "status": "warning"}],
                "message": "当前没有选中节点。请先选中一个报错节点。",
            }

        node = selected[-1]
        events: List[Dict[str, str]] = [{"title": "读取节点", "detail": node.path(), "status": "success"}]
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
        applied = []
        for old, new in known_replacements.items():
            if old in updated:
                updated = updated.replace(old, new)
                applied.append(f"{old} -> {new}")

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
        for parm_name in ("snippet", "python", "code", "vexpression"):
            parm = node.parm(parm_name)
            if parm is not None:
                return parm
        return None

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


def create_best_adapter():
    try:
        import hou  # noqa: F401

        return HoudiniAdapter()
    except Exception:
        return MockHoudiniAdapter()
