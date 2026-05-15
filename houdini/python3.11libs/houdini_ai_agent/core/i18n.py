"""Lightweight bilingual (zh/en) translation system for Houdini AI Agent.

Design follows first principles adapted to the current project:
- Pure Python dicts (no external deps), consistent with urllib-based approach
- Qt fallback via qt.py compat layer, not direct PySide dependency
- tr(key, *args) for format-string interpolation
- language_changed signal for observer pattern when Qt available
- Persistence via config.py's load/save_app_config pattern

Usage:
    from houdini_ai_agent.core.i18n import tr, set_language, get_language
    label.setText(tr("settings.title"))
"""

from __future__ import annotations

from typing import Optional

from houdini_ai_agent.qt import PYSIDE_VERSION, QtCore

# ---------------------------------------------------------------------------
# Current language state
# ---------------------------------------------------------------------------

_current_lang: str = "zh"  # "zh" | "en"

# ---------------------------------------------------------------------------
# Language change signal (Qt observer pattern, optional)
# ---------------------------------------------------------------------------


class _LangSignals:
    """Namespace holding the language-changed Qt signal when Qt is available."""

    changed = None


if PYSIDE_VERSION > 0 and QtCore is not None:
    try:
        class _LanguageChangedEmitter(QtCore.QObject):
            language_changed = QtCore.Signal(str)

        _emitter = _LanguageChangedEmitter()
        _LangSignals.changed = _emitter.language_changed
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Translation dictionaries
# ---------------------------------------------------------------------------

_ZH: dict[str, str] = {
    # -- UI: main panel --
    "app.title": "Houdini AI Agent",
    "app.subtitle": "会话式工程助手，支持图片、自动保存和工程上下文读取",
    "button.settings": "设置",
    "button.focus_mode": "专注模式",
    "button.exit_focus": "退出专注",
    "button.send": "发送",
    "button.stop": "停止",
    "button.image": "图片",
    "button.clear": "清空",
    "button.clear_messages": "清空消息",
    "button.save": "保存",
    "button.cancel": "取消",
    "button.close": "关闭",

    # -- UI: action bar --
    "action.analyze_scene": "分析工程",
    "action.inspect_selection": "查看选中节点",
    "action.create_nodes": "创建节点",
    "action.fix_error": "修复错误",
    "action.capture_viewport": "捕获视口",

    # -- UI: composer --
    "composer.placeholder": "输入请求，Enter 发送，Alt+Enter 换行。也可以先添加图片让 Agent 识别。",
    "composer.model": "模型",
    "composer.mode": "模式",
    "composer.thinking": "思考",
    "composer.context": "上下文",

    # -- UI: conversations --
    "conv.new": "新建会话",
    "conv.new_session": "新会话",
    "conv.import": "导入会话",
    "conv.export": "导出",
    "conv.rename": "重命名",
    "conv.clear_msgs": "清空消息",
    "conv.delete": "删除会话",
    "conv.msg_count": "{0} 条消息",
    "conv.import_title": "导入会话记录",
    "conv.import_success": "已导入 {0} 个会话。",
    "conv.export_title": "导出会话记录",
    "conv.export_success": "已导出：{0}",
    "conv.delete_title": "删除会话",
    "conv.delete_confirm": "确定删除会话「{0}」吗？\n对应的自动保存文件和 Agent/images 下的会话图片也会被清理。",
    "conv.delete_min_one": "至少需要保留一个会话。",
    "conv.clear_title": "清空全部消息",
    "conv.clear_confirm": "确定清空会话「{0}」里的全部消息和执行轨迹吗？\n会话本身会保留。",
    "conv.delete_msg_title": "删除消息",
    "conv.delete_msg_confirm": "确定删除会话「{0}」中的这条消息吗？",
    "conv.rename_title": "重命名会话",
    "conv.rename_label": "会话名称",

    # -- UI: welcome --
    "welcome.text": (
        "欢迎使用 Houdini AI Agent。\n"
        "你可以创建多个会话、发送图片、切换思考档位，并在右侧查看工程上下文。"
    ),

    # -- UI: settings dialog --
    "settings.title": "Houdini AI Agent 设置",
    "settings.intro": "配置聊天模型和独立的视觉后端。主模型可以是纯文本模型，图片理解可以交给另一个多模态 provider。",
    "settings.add_provider": "添加 Provider",
    "settings.add_openai": "添加 OpenAI 示例",
    "settings.remove_selected": "删除选中",
    "settings.vision_group": "视觉后端",
    "settings.vision_mode": "模式",
    "settings.vision_target": "目标",
    "settings.vision_hint": "说明",
    "settings.external_group": "外部配置发现",
    "settings.col_name": "名称",
    "settings.col_base_url": "Base URL",
    "settings.col_api_key": "API Key / 环境变量",
    "settings.col_model": "模型",
    "settings.col_reasoning": "推理",
    "settings.col_vision": "视觉",
    "settings.col_fallback": "自动兜底",
    "settings.col_thinking": "默认思考",
    "settings.vision_auto": "自动（不使用 Codex）",
    "settings.vision_disabled": "禁用",
    "settings.vision_provider": "指定 Provider",
    "settings.vision_codex": "Codex Local（显式启用）",
    "settings.vision_mcp": "MCP（预留）",
    "settings.vision_skill": "Skill（预留）",
    "settings.vision_auto_hint": "自动模式不会把 Codex 当作其他主模型的隐式兜底；当主模型就是 Codex Local 时会直接读图。如需让 GLM 等文本模型借用 Codex，请显式选择 Codex Local。",
    "settings.vision_disabled_hint": "插件仍可正常聊天，但纯文本模型不会获得图片理解结果。",
    "settings.vision_provider_hint": "指定一个多模态 provider 专门读图，主聊天模型可以继续使用 glm-5.1 等文本模型。",
    "settings.vision_codex_hint": "显式使用本机 Codex 作为读图 companion。只有这个模式会调用 Codex 读图。",
    "settings.vision_mcp_hint": "预留给后续 MCP 视觉后端。当前版本不会执行 MCP 读图。",
    "settings.vision_skill_hint": "预留给后续本地 Skill 视觉后端。当前版本不会执行 Skill 读图。",
    "settings.vision_checkbox_tip": "勾选后表示该 provider 可以直接读取图片。",
    "settings.vision_fallback_tip": "仅在自动模式下作为优先提示；Codex Local 不会被自动模式隐式选中。",
    "settings.found": "已找到",
    "settings.not_found": "未找到",

    # -- UI: chat view --
    "chat.role_user": "You",
    "chat.role_agent": "Agent",
    "chat.role_thought": "已思考",
    "chat.role_plan": "Plan",
    "chat.thought_toggle": "已思考",
    "chat.delete_message": "删除此消息",
    "chat.pending_images": "待发送图片 {0}",
    "chat.image_unavailable": "无法读取图片",
    "chat.select_images": "选择图片",

    # -- UI: context panel --
    "context.usage_tooltip": (
        "本地估算：约 {0} tokens / {1} 上下文窗口。"
        " 当前版本还没有接入 provider 返回的真实 usage；TODO 中已有 token / context 管理计划。"
    ),

    # -- UI: language toggle --
    "lang.toggle_to_en": "English",
    "lang.toggle_to_zh": "中文",
    "lang.switch_to_en_tip": "切换到英文",
    "lang.switch_to_zh_tip": "Switch to Chinese",

    # -- UI: plan card --
    "plan.title": "执行计划",
    "plan.goal": "计划目标：{0}",
    "plan.no_steps": "暂无结构化步骤。",
    "plan.risks": "风险：{0}",
    "plan.confirm": "切换 Agent 执行",
    "plan.cancel_plan": "取消计划",
    "plan.confirmed": "已确认，正在切换到 Agent 模式执行。",
    "plan.cancelled": "已取消。",
    "plan.todos_progress": "To-dos {0}/{1} 已完成",
    "plan.depends": "依赖：{0}",
    "plan.status_label": "状态：{0}",
    "plan.result_label": "结果：{0}",
    "plan.tool_label": "工具/动作：{0}",
    "plan.status.draft": "等待确认。确认后会切换到 Agent 模式执行。",
    "plan.status.confirmed": "已确认，等待执行。",
    "plan.status.executing": "正在执行。",
    "plan.status.completed": "已完成。",
    "plan.status.cancelled": "已取消。",
    "plan.status.paused": "已暂停；再次确认可恢复。",
    "plan.status.blocked": "被阻塞；请调整后再次确认。",

    # -- UI: status --
    "status.codex_not_logged_in": "未检测到 Codex 本地登录状态。请先在这台机器上登录 Codex。",
    "status.codex_logged_in": "使用本机已登录的 Codex CLI，不需要单独填写 OpenAI API key。",
    "status.set_env_var": "请在启动 Houdini 前设置环境变量 {0}，或者先切回 Mock Preview。",

    # -- Action summaries (used by action_runner.summarize) --
    "action_summary.create_node": "创建 {0}，位置：{1}",
    "action_summary.apply_code": "把代码写入 {0} / {1}",
    "action_summary.set_parm": "设置 {0} 的 {1} = {2}",
    "action_summary.inspect_selection": "检查当前选中节点",
    "action_summary.capture_viewport": "捕获当前视口",
    "action_summary.analyze_scene": "分析当前场景上下文",
    "action_summary.add_todo": "添加任务：{0}",
    "action_summary.update_todo": "更新任务：{0}",
    "action_summary.get_network_structure": "读取网络结构：{0}",
    "action_summary.get_node_parameters": "读取参数：{0}",
    "action_summary.list_children": "列出子节点：{0}",
    "action_summary.check_errors": "检查错误：{0}",
    "action_summary.delete_node": "删除节点：{0}",
    "action_summary.connect_nodes": "连接 {0} → {1}",
    "action_summary.copy_node": "复制节点：{0}",
    "action_summary.batch_set_parameters": "批量设置 {0}",
    "action_summary.set_display_flag": "设置标志：{0}",
    "action_summary.layout_nodes": "布局节点：{0}",
    "action_summary.execute_python": "执行 Python 代码",
    "action_summary.execute_shell": "执行 Shell：{0}",
    "action_summary.save_hip": "保存 HIP",
    "action_summary.undo": "撤销",
    "action_summary.redo": "重做",
    "action_summary.find_nodes_by_param": "搜索参数 {0}",
    "action_summary.get_node_positions": "读取节点位置",
    "action_summary.default": "执行模型请求的工具动作",

    # -- Context manager messages --
    "ctx.round_trimmed": "[上下文已自动裁剪，移除了 {0} 个旧轮次]",
    "ctx.images_stripped": "[图片已从旧消息中移除以节省空间]",
    "ctx.result_compressed": "[工具结果已压缩]",
    "ctx.result_truncated": "…（已截断，原始 {0} 字符）",

    # -- Agent loop messages --
    "agent.max_iterations": "Agent 循环已达到最大迭代次数。",
    "agent.tool_budget_exhausted": "工具调用预算已耗尽。",
    "agent.cancelled": "已取消。",
    "agent.tool_not_allowed": "工具 '{0}' 在 {1} 模式下不被允许。",
    "agent.duplicate_readonly_skip": "跳过重复的只读调用：{0}",
    "agent.tool_execution_error": "工具执行错误：{0}",
    "agent.unknown_tool": "未知工具：{0}",
    "agent.missing_param": "工具 '{0}' 缺少必需参数 '{1}'",

    # -- Thread dispatch messages --
    "dispatch.main_thread_busy": "主线程正忙，无法调度工具执行。请稍后重试。",
    "dispatch.timeout": "主线程调度超时（{0}秒）。",

    # -- Thinking levels --
    "thinking.low": "更快、更省 token，适合小型操作",
    "thinking.medium": "默认档，适合常规工程解释",
    "thinking.high": "适合错误分析和多步操作",
    "thinking.xhigh": "适合复杂诊断和自动修复",
}

_EN: dict[str, str] = {
    # -- UI: main panel --
    "app.title": "Houdini AI Agent",
    "app.subtitle": "Conversational engineering assistant with image support, auto-save, and context reading",
    "button.settings": "Settings",
    "button.focus_mode": "Focus Mode",
    "button.exit_focus": "Exit Focus",
    "button.send": "Send",
    "button.stop": "Stop",
    "button.image": "Image",
    "button.clear": "Clear",
    "button.clear_messages": "Clear Messages",
    "button.save": "Save",
    "button.cancel": "Cancel",
    "button.close": "Close",

    # -- UI: action bar --
    "action.analyze_scene": "Analyze Scene",
    "action.inspect_selection": "Inspect Selection",
    "action.create_nodes": "Create Node",
    "action.fix_error": "Fix Error",
    "action.capture_viewport": "Capture Viewport",

    # -- UI: composer --
    "composer.placeholder": "Enter a request. Enter to send, Alt+Enter for newline. You can also add images first.",
    "composer.model": "Model",
    "composer.mode": "Mode",
    "composer.thinking": "Thinking",
    "composer.context": "Context",

    # -- UI: conversations --
    "conv.new": "New Chat",
    "conv.new_session": "New Chat",
    "conv.import": "Import Chats",
    "conv.export": "Export",
    "conv.rename": "Rename",
    "conv.clear_msgs": "Clear Messages",
    "conv.delete": "Delete Chat",
    "conv.msg_count": "{0} messages",
    "conv.import_title": "Import Chat History",
    "conv.import_success": "Imported {0} conversation(s).",
    "conv.export_title": "Export Chat History",
    "conv.export_success": "Exported: {0}",
    "conv.delete_title": "Delete Chat",
    "conv.delete_confirm": "Delete chat \"{0}\"?\nAuto-save files and session images under Agent/images will also be cleaned up.",
    "conv.delete_min_one": "At least one conversation must be kept.",
    "conv.clear_title": "Clear All Messages",
    "conv.clear_confirm": "Clear all messages and execution traces in \"{0}\"?\nThe conversation itself will be kept.",
    "conv.delete_msg_title": "Delete Message",
    "conv.delete_msg_confirm": "Delete this message in \"{0}\"?",
    "conv.rename_title": "Rename Chat",
    "conv.rename_label": "Chat name",

    # -- UI: welcome --
    "welcome.text": (
        "Welcome to Houdini AI Agent.\n"
        "You can create multiple sessions, send images, switch thinking levels, and view engineering context on the right."
    ),

    # -- UI: settings dialog --
    "settings.title": "Houdini AI Agent Settings",
    "settings.intro": "Configure chat models and a separate vision backend. The main model can be text-only; image understanding can use a different multimodal provider.",
    "settings.add_provider": "Add Provider",
    "settings.add_openai": "Add OpenAI Example",
    "settings.remove_selected": "Remove Selected",
    "settings.vision_group": "Vision Backend",
    "settings.vision_mode": "Mode",
    "settings.vision_target": "Target",
    "settings.vision_hint": "Hint",
    "settings.external_group": "External Config Discovery",
    "settings.col_name": "Name",
    "settings.col_base_url": "Base URL",
    "settings.col_api_key": "API Key / Env Var",
    "settings.col_model": "Model",
    "settings.col_reasoning": "Reasoning",
    "settings.col_vision": "Vision",
    "settings.col_fallback": "Auto Fallback",
    "settings.col_thinking": "Default Thinking",
    "settings.vision_auto": "Auto (no Codex)",
    "settings.vision_disabled": "Disabled",
    "settings.vision_provider": "Specify Provider",
    "settings.vision_codex": "Codex Local (explicit)",
    "settings.vision_mcp": "MCP (reserved)",
    "settings.vision_skill": "Skill (reserved)",
    "settings.vision_auto_hint": "Auto mode does not implicitly use Codex as fallback for other models. When the main model is Codex Local, it reads images directly. To let text models like GLM use Codex for vision, explicitly select Codex Local.",
    "settings.vision_disabled_hint": "The plugin can still chat normally, but text-only models will not receive image analysis results.",
    "settings.vision_provider_hint": "Specify a multimodal provider dedicated to reading images. The main chat model can continue using text models like glm-5.1.",
    "settings.vision_codex_hint": "Explicitly use local Codex as the image-reading companion. Only this mode invokes Codex for vision.",
    "settings.vision_mcp_hint": "Reserved for a future MCP vision backend. Current version does not execute MCP image reading.",
    "settings.vision_skill_hint": "Reserved for a future local Skill vision backend. Current version does not execute Skill image reading.",
    "settings.vision_checkbox_tip": "Check to indicate this provider can directly read images.",
    "settings.vision_fallback_tip": "Only used as priority hint in auto mode; Codex Local is not implicitly selected by auto mode.",
    "settings.found": "Found",
    "settings.not_found": "Not found",

    # -- UI: chat view --
    "chat.role_user": "You",
    "chat.role_agent": "Agent",
    "chat.role_thought": "Thought",
    "chat.role_plan": "Plan",
    "chat.thought_toggle": "Thought",
    "chat.delete_message": "Delete this message",
    "chat.pending_images": "Pending images {0}",
    "chat.image_unavailable": "Cannot read image",
    "chat.select_images": "Select Images",

    # -- UI: context panel --
    "context.usage_tooltip": (
        "Local estimate: about {0} tokens / {1} context window. "
        "Provider-reported usage is not wired yet; TODO already tracks token/context management."
    ),

    # -- UI: language toggle --
    "lang.toggle_to_en": "English",
    "lang.toggle_to_zh": "中文",
    "lang.switch_to_en_tip": "Switch to English",
    "lang.switch_to_zh_tip": "切换到中文",

    # -- UI: plan card --
    "plan.title": "Execution Plan",
    "plan.goal": "Goal: {0}",
    "plan.no_steps": "No structured steps available.",
    "plan.risks": "Risks: {0}",
    "plan.confirm": "Switch to Agent Execution",
    "plan.cancel_plan": "Cancel Plan",
    "plan.confirmed": "Confirmed. Switching to Agent mode for execution.",
    "plan.cancelled": "Cancelled.",
    "plan.todos_progress": "To-dos {0}/{1} completed",
    "plan.depends": "Depends on: {0}",
    "plan.status_label": "Status: {0}",
    "plan.result_label": "Result: {0}",
    "plan.tool_label": "Tool/Action: {0}",
    "plan.status.draft": "Awaiting confirmation. Will switch to Agent mode upon confirmation.",
    "plan.status.confirmed": "Confirmed, awaiting execution.",
    "plan.status.executing": "Executing.",
    "plan.status.completed": "Completed.",
    "plan.status.cancelled": "Cancelled.",
    "plan.status.paused": "Paused; confirm again to resume.",
    "plan.status.blocked": "Blocked; revise or confirm again after adjustment.",

    # -- UI: status --
    "status.codex_not_logged_in": "Codex local login not detected. Please log in to Codex on this machine first.",
    "status.codex_logged_in": "Using locally logged-in Codex CLI. No separate OpenAI API key needed.",
    "status.set_env_var": "Set environment variable {0} before launching Houdini, or switch back to Mock Preview.",

    # -- Action summaries --
    "action_summary.create_node": "Create {0}, location: {1}",
    "action_summary.apply_code": "Write code to {0} / {1}",
    "action_summary.set_parm": "Set {0}.{1} = {2}",
    "action_summary.inspect_selection": "Inspect selected nodes",
    "action_summary.capture_viewport": "Capture current viewport",
    "action_summary.analyze_scene": "Analyze current scene context",
    "action_summary.add_todo": "Add task: {0}",
    "action_summary.update_todo": "Update task: {0}",
    "action_summary.get_network_structure": "Read network structure: {0}",
    "action_summary.get_node_parameters": "Read parameters: {0}",
    "action_summary.list_children": "List children: {0}",
    "action_summary.check_errors": "Check errors: {0}",
    "action_summary.delete_node": "Delete node: {0}",
    "action_summary.connect_nodes": "Connect {0} → {1}",
    "action_summary.copy_node": "Copy node: {0}",
    "action_summary.batch_set_parameters": "Batch set {0}",
    "action_summary.set_display_flag": "Set flags: {0}",
    "action_summary.layout_nodes": "Layout nodes: {0}",
    "action_summary.execute_python": "Execute Python code",
    "action_summary.execute_shell": "Execute shell: {0}",
    "action_summary.save_hip": "Save HIP",
    "action_summary.undo": "Undo",
    "action_summary.redo": "Redo",
    "action_summary.find_nodes_by_param": "Search param {0}",
    "action_summary.get_node_positions": "Read node positions",
    "action_summary.default": "Execute model-requested tool action",

    # -- Context manager messages --
    "ctx.round_trimmed": "[Context auto-trimmed, removed {0} old round(s)]",
    "ctx.images_stripped": "[Images removed from older messages to save space]",
    "ctx.result_compressed": "[Tool result compressed]",
    "ctx.result_truncated": "...(truncated, original {0} chars)",

    # -- Agent loop messages --
    "agent.max_iterations": "Agent loop reached maximum iterations.",
    "agent.tool_budget_exhausted": "Tool call budget exhausted.",
    "agent.cancelled": "Cancelled.",
    "agent.tool_not_allowed": "Tool '{0}' is not allowed in {1} mode.",
    "agent.duplicate_readonly_skip": "Skipping duplicate readonly call: {0}",
    "agent.tool_execution_error": "Tool execution error: {0}",
    "agent.unknown_tool": "Unknown tool: {0}",
    "agent.missing_param": "Missing required parameter '{1}' for tool '{0}'",

    # -- Thread dispatch messages --
    "dispatch.main_thread_busy": "Main thread is busy, cannot dispatch tool execution. Please retry later.",
    "dispatch.timeout": "Main thread dispatch timed out ({0}s).",

    # -- Thinking levels --
    "thinking.low": "Faster, fewer tokens, suitable for small operations",
    "thinking.medium": "Default, suitable for routine engineering explanations",
    "thinking.high": "Suitable for error analysis and multi-step operations",
    "thinking.xhigh": "Suitable for complex diagnosis and auto-repair",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tr(key: str, *args: object) -> str:
    """Translate a key into the current language with optional format args.

    Falls back to the key itself if no translation is found.
    """
    template = _get_template(key)
    if args:
        try:
            return template.format(*args)
        except (IndexError, KeyError, ValueError):
            return template
    return template


def _get_template(key: str) -> str:
    """Return the template string for the given key in the current language."""
    if _current_lang == "en":
        return _EN.get(key, _ZH.get(key, key))
    return _ZH.get(key, _EN.get(key, key))


def get_language() -> str:
    """Return the current UI language code ('zh' or 'en')."""
    return _current_lang


def set_language(lang: str) -> None:
    """Set the UI language and emit language_changed signal if available."""
    global _current_lang
    normalized = (lang or "zh").strip().lower()
    if normalized not in ("zh", "en"):
        normalized = "zh"
    if normalized == _current_lang:
        return
    _current_lang = normalized
    if _LangSignals.changed is not None:
        try:
            _LangSignals.changed.emit(normalized)
        except Exception:
            pass


def load_language() -> None:
    """Load persisted language preference from config."""
    from houdini_ai_agent.core.config import load_ui_language
    global _current_lang
    _current_lang = load_ui_language()


def save_language(lang: Optional[str] = None) -> None:
    """Persist language preference to config."""
    from houdini_ai_agent.core.config import save_ui_language
    save_ui_language(lang or _current_lang)


def is_english() -> bool:
    """Check if the current UI language is English."""
    return _current_lang == "en"


def all_keys() -> list[str]:
    """Return all translation keys (union of zh and en)."""
    return sorted(set(_ZH.keys()) | set(_EN.keys()))


def has_key(key: str) -> bool:
    """Check if a translation key exists."""
    return key in _ZH or key in _EN
