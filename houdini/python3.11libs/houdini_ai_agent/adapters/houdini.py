"""Thin Houdini HOM adapter used when the panel runs inside Houdini."""

from __future__ import annotations

from typing import Dict, List
from pathlib import Path

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
        current_network = selected[0].parent().path() if selected else "/obj"
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
                {"title": "读取参数", "detail": ", ".join(parms) or "No parameters", "status": "success"},
            ],
            "message": f"选中节点：`{node.path()}`\n类型：`{node.type().nameWithCategory()}`\n参数预览：{', '.join(parms[:8])}",
        }

    def capture_viewport_preview(self, thinking_level: str) -> Dict[str, object]:
        return {
            "title": "捕获视口",
            "events": [
                {"title": "定位 Scene Viewer", "detail": self._viewport_summary(), "status": "success"},
                {"title": "截图导出", "detail": "Metadata capture is live. Image capture is planned for the next milestone.", "status": "warning"},
            ],
            "message": f"当前视口：{self._viewport_summary()}",
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


def create_best_adapter():
    try:
        import hou  # noqa: F401

        return HoudiniAdapter()
    except Exception:
        return MockHoudiniAdapter()
