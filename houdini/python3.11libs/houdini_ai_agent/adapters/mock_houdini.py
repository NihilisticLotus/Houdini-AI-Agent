"""Mock Houdini adapter for the first UI milestone."""

from __future__ import annotations

from typing import Dict, List, Optional
from pathlib import Path


class MockHoudiniAdapter:
    name = "Mock Houdini"

    def get_session_storage_dir(self):
        return None

    def navigate_to_node(self, node_path: str) -> Dict[str, object]:
        return {
            "ok": True,
            "message": f"Mock mode focused node: {node_path}",
        }

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

    def create_node_preview(self, thinking_level: str) -> Dict[str, object]:
        return {
            "title": "创建节点预演",
            "events": [
                {"title": "规划节点", "detail": "Create null OUT_AGENT_PREVIEW after selected node.", "status": "running"},
                {"title": "模拟创建", "detail": "No real Houdini node was modified in mock mode.", "status": "success"},
            ],
            "message": "已完成节点创建预演：下一阶段会在真实 Houdini adapter 中创建并连接 `OUT_AGENT_PREVIEW`。",
        }

    def set_node_parameter(self, target_node: str, parm_name: str, value) -> Dict[str, object]:
        return {
            "title": "Set parameter",
            "events": [{"title": "Mock set parameter", "detail": f"{target_node}.{parm_name} = {value}", "status": "success"}],
            "message": f"Mock mode set `{target_node}.{parm_name}` to `{value}`.",
        }

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

    def capture_viewport_preview(self, thinking_level: str) -> Dict[str, object]:
        return {
            "title": "捕获视口预演",
            "events": [
                {"title": "定位 Scene Viewer", "detail": "Mock viewport persp1 found.", "status": "success"},
                {"title": "捕获画面", "detail": "Viewport capture is mocked in this milestone.", "status": "success"},
            ],
            "message": "已读取当前视口预览信息。真实截图导出会在 Houdini 接入阶段实现。",
        }
