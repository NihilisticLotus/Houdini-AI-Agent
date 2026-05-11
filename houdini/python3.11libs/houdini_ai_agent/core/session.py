"""Agent session and conversation state used by the panel."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
import uuid

from houdini_ai_agent.core.codex_cli import CodexCallError, send_codex_chat
from houdini_ai_agent.core.config import ProviderConfig, load_providers
from houdini_ai_agent.core.openai_compat import ProviderCallError, build_reasoning_effort, send_chat
from houdini_ai_agent.qt import QtCore


THINKING_LEVELS: Dict[str, Dict[str, str]] = {
    "低": {"effort": "low", "description": "快速、省 token，适合小操作"},
    "中": {"effort": "medium", "description": "默认档，适合常规工程解释"},
    "高": {"effort": "high", "description": "适合错误分析和多步操作"},
    "超高": {"effort": "xhigh", "description": "适合复杂诊断和自动修复"},
}

LEGACY_SESSION_FILE_NAME = "houdini_ai_agent_sessions.json"
SESSION_INDEX_FILE_NAME = "session_index.json"
SESSIONS_DIR_NAME = "sessions"
IMAGES_DIR_NAME = "images"


@dataclass
class AgentMessage:
    role: str
    content: str
    image_paths: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))


@dataclass
class ExecutionEvent:
    title: str
    detail: str
    status: str = "info"
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))


@dataclass
class Conversation:
    id: str
    title: str
    messages: List[AgentMessage] = field(default_factory=list)
    events: List[ExecutionEvent] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%H:%M"))


class ModelCallWorker(QtCore.QObject):
    finished = QtCore.Signal(str, str, str, str, str)

    def __init__(
        self,
        task_id: str,
        provider: ProviderConfig,
        prompt: str,
        system_prompt: str,
        image_paths: List[str],
        cwd: str,
        thinking_level: str,
        parent=None,
    ):
        super().__init__(parent)
        self.task_id = task_id
        self.provider = provider
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.image_paths = image_paths
        self.cwd = cwd
        self.thinking_level = thinking_level

    def run(self) -> None:
        try:
            if self.provider.source == "codex":
                response = send_codex_chat(
                    prompt=self.prompt,
                    image_paths=self.image_paths,
                    model=self.provider.model,
                    cwd=self.cwd,
                )
                detail = f"Local Codex reply received via {self.provider.model or 'default model'}."
                self.finished.emit(self.task_id, response, "生成回复", detail, "success")
            else:
                response = send_chat(
                    provider=self.provider,
                    system_prompt=self.system_prompt,
                    user_text=self.prompt,
                    image_paths=self.image_paths,
                    thinking_level=self.thinking_level,
                    max_tokens=1400,
                )
                detail = f"Live provider response received via {self.provider.name} ({build_reasoning_effort(self.thinking_level)} reasoning)."
                self.finished.emit(self.task_id, response, "生成回复", detail, "success")
        except (CodexCallError, ProviderCallError) as exc:
            self.finished.emit(self.task_id, f"模型调用失败：{exc}", "模型调用失败", str(exc), "error")
        except Exception as exc:
            self.finished.emit(self.task_id, f"模型调用异常：{exc}", "模型调用异常", str(exc), "error")


class AgentSession(QtCore.QObject):
    message_added = QtCore.Signal(object)
    event_added = QtCore.Signal(object)
    context_changed = QtCore.Signal(dict)
    providers_changed = QtCore.Signal(list)
    busy_changed = QtCore.Signal(bool)
    conversations_changed = QtCore.Signal(list)
    conversation_changed = QtCore.Signal(object)
    storage_status_changed = QtCore.Signal(str)

    def __init__(self, adapter, parent=None):
        super().__init__(parent)
        self.adapter = adapter
        self.providers: List[ProviderConfig] = load_providers()
        self.current_provider_index = 0
        self.current_thinking_level = "中"
        self.context: Dict[str, object] = {}
        self._busy = False
        self._active_task_id: Optional[str] = None
        self._active_thread = None
        self._active_worker = None
        self._pending_model_fix_context: Optional[Dict[str, object]] = None
        self._loading = False
        self.storage_status = ""
        self.conversations: List[Conversation] = []
        self.current_conversation_id = ""

        if not self.load_autosaved_conversations():
            self.create_conversation("新会话")

    @property
    def current_provider(self) -> ProviderConfig:
        if not self.providers:
            self.providers = load_providers()
        return self.providers[max(0, min(self.current_provider_index, len(self.providers) - 1))]

    @property
    def current_conversation(self) -> Conversation:
        for conversation in self.conversations:
            if conversation.id == self.current_conversation_id:
                return conversation
        return self.conversations[0]

    @property
    def messages(self) -> List[AgentMessage]:
        return self.current_conversation.messages

    @property
    def events(self) -> List[ExecutionEvent]:
        return self.current_conversation.events

    @property
    def busy(self) -> bool:
        return self._busy

    def create_conversation(self, title: str = "新会话") -> Conversation:
        if title == "新会话":
            title = self._next_conversation_title()
        conversation = Conversation(id=uuid.uuid4().hex, title=title)
        self.conversations.insert(0, conversation)
        self.current_conversation_id = conversation.id
        self.conversations_changed.emit(self.conversations)
        self.conversation_changed.emit(conversation)
        self.save_autosaved_conversations()
        return conversation

    def switch_conversation(self, conversation_id: str) -> None:
        if conversation_id == self.current_conversation_id:
            return
        if any(item.id == conversation_id for item in self.conversations):
            self.current_conversation_id = conversation_id
            self.conversation_changed.emit(self.current_conversation)
            self.save_autosaved_conversations()

    def rename_conversation(self, conversation_id: str, title: str) -> None:
        title = title.strip()
        if not title:
            return
        for conversation in self.conversations:
            if conversation.id == conversation_id:
                conversation.title = title
                self.conversations_changed.emit(self.conversations)
                if conversation.id == self.current_conversation_id:
                    self.conversation_changed.emit(conversation)
                self.save_autosaved_conversations()
                return

    def delete_conversation(self, conversation_id: str) -> bool:
        if len(self.conversations) <= 1:
            return False
        conversation = self._conversation_by_id(conversation_id)
        if conversation is None:
            return False

        self.conversations = [item for item in self.conversations if item.id != conversation_id]
        if self.current_conversation_id == conversation_id:
            self.current_conversation_id = self.conversations[0].id
            self.conversation_changed.emit(self.current_conversation)
        self.conversations_changed.emit(self.conversations)
        self._delete_conversation_files(conversation_id)
        self.save_autosaved_conversations()
        return True

    def clear_conversation_history(self, conversation_id: str) -> bool:
        conversation = self._conversation_by_id(conversation_id)
        if conversation is None:
            return False
        conversation.messages = []
        conversation.events = []
        self.conversations_changed.emit(self.conversations)
        if conversation.id == self.current_conversation_id:
            self.conversation_changed.emit(conversation)
        self.save_autosaved_conversations()
        return True

    def delete_message(self, conversation_id: str, message_index: int) -> bool:
        conversation = self._conversation_by_id(conversation_id)
        if conversation is None:
            return False
        if message_index < 0 or message_index >= len(conversation.messages):
            return False
        del conversation.messages[message_index]
        self.conversations_changed.emit(self.conversations)
        if conversation.id == self.current_conversation_id:
            self.conversation_changed.emit(conversation)
        self.save_autosaved_conversations()
        return True

    def import_conversations_from_file(self, file_path: str) -> int:
        path = Path(file_path)
        conversations, current_id = self._read_conversation_file(path)
        if not conversations:
            return 0

        existing_ids = {conversation.id for conversation in self.conversations}
        imported = 0
        for conversation in conversations:
            if conversation.id in existing_ids:
                conversation.id = uuid.uuid4().hex
            self.conversations.insert(0, conversation)
            imported += 1

        self.current_conversation_id = conversations[0].id if conversations else current_id
        self.conversations_changed.emit(self.conversations)
        self.conversation_changed.emit(self.current_conversation)
        self.save_autosaved_conversations()
        return imported

    def export_current_conversation_to_file(self, file_path: str) -> Optional[Path]:
        return self.export_conversation_to_file(self.current_conversation_id, file_path)

    def export_conversation_to_file(self, conversation_id: str, file_path: str) -> Optional[Path]:
        if not file_path:
            return None
        conversation = self._conversation_by_id(conversation_id)
        if conversation is None:
            return None
        export_path = Path(file_path)
        if export_path.suffix.lower() != ".json":
            export_path = export_path.with_suffix(".json")
        payload = {
            "version": 2,
            "format": "houdini_ai_agent_conversation",
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "current_conversation_id": conversation.id,
            "conversations": [self._conversation_to_dict(conversation, embed_images=True)],
        }
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.storage_status = f"已导出会话：{export_path}"
        self.storage_status_changed.emit(self.storage_status)
        return export_path

    def materialize_current_image_paths(self, image_paths: List[str]) -> List[str]:
        return self._materialize_image_paths(self.current_conversation_id, image_paths)

    def _conversation_by_id(self, conversation_id: str) -> Optional[Conversation]:
        for conversation in self.conversations:
            if conversation.id == conversation_id:
                return conversation
        return None

    def load_autosaved_conversations(self) -> bool:
        storage_dir = self._storage_dir()
        if storage_dir is None:
            self.storage_status = "会话自动保存：当前 HIP 未保存或无历史记录"
            self.storage_status_changed.emit(self.storage_status)
            return False
        conversations, current_id = self._read_per_conversation_storage(storage_dir)
        if not conversations:
            legacy_file = storage_dir / LEGACY_SESSION_FILE_NAME
            conversations, current_id = self._read_conversation_file(legacy_file) if legacy_file.exists() else ([], "")
        if not conversations:
            self.storage_status = "会话自动保存：当前 HIP 无历史记录"
            self.storage_status_changed.emit(self.storage_status)
            return False
        self._loading = True
        self.conversations = conversations
        self.current_conversation_id = current_id if current_id else conversations[0].id
        self._loading = False
        self.conversations_changed.emit(self.conversations)
        self.conversation_changed.emit(self.current_conversation)
        self.storage_status = f"已读取会话记录：{storage_dir}"
        self.storage_status_changed.emit(self.storage_status)
        return True

    def save_autosaved_conversations(self) -> Optional[Path]:
        if self._loading:
            return None
        storage_dir = self._storage_dir()
        if storage_dir is None:
            self.storage_status = "会话自动保存：请先保存 HIP 文件"
            self.storage_status_changed.emit(self.storage_status)
            return None
        sessions_dir = storage_dir / SESSIONS_DIR_NAME
        sessions_dir.mkdir(parents=True, exist_ok=True)
        for conversation in self.conversations:
            self._materialize_conversation_images(conversation, storage_dir)
            session_file = sessions_dir / f"{conversation.id}.json"
            payload = {
                "version": 2,
                "format": "houdini_ai_agent_conversation",
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "conversation": self._conversation_to_dict(conversation, embed_images=False),
            }
            session_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        index_payload = {
            "version": 2,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "current_conversation_id": self.current_conversation_id,
            "conversation_order": [conversation.id for conversation in self.conversations],
        }
        (storage_dir / SESSION_INDEX_FILE_NAME).write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.storage_status = f"会话已自动保存：{sessions_dir}"
        self.storage_status_changed.emit(self.storage_status)
        return sessions_dir

    def set_provider_index(self, index: int) -> None:
        self.current_provider_index = index

    def set_thinking_level(self, level: str) -> None:
        if level in THINKING_LEVELS:
            self.current_thinking_level = level

    def set_providers(self, providers: List[ProviderConfig]) -> None:
        self.providers = providers
        self.current_provider_index = min(self.current_provider_index, max(0, len(providers) - 1))
        self.providers_changed.emit(self.providers)

    def refresh_context(self) -> Dict[str, object]:
        self.context = self.adapter.get_context()
        self.context_changed.emit(self.context)
        return self.context

    def send_message(self, text: str, image_paths: Optional[List[str]] = None) -> None:
        image_paths = image_paths or []
        text = text.strip()
        if not text and not image_paths:
            return
        if not text and image_paths:
            text = "请识别并分析这些图片。"
        image_paths = self._materialize_image_paths(self.current_conversation_id, image_paths)

        self._set_busy(True)
        self._active_task_id = uuid.uuid4().hex
        self._add_message("user", text, image_paths)
        self._maybe_title_current_conversation(text, image_paths)
        self._add_event("收到请求", f"Thinking: {self.current_thinking_level} / Model: {self.current_provider.model}", "info")

        context = self.refresh_context()
        self._add_event("收集上下文", self.adapter.describe_context(context), "running")
        if image_paths:
            self._add_event("读取图片输入", f"{len(image_paths)} image(s) attached for vision analysis.", "running")

        if not image_paths and self._run_tool_intent_from_text(text):
            self.save_autosaved_conversations()
            if self._active_thread is None:
                self._set_busy(False)
            return

        if self.current_provider.source == "mock":
            response = self.adapter.mock_chat_response(
                prompt=text,
                thinking_level=self.current_thinking_level,
                provider=self.current_provider.name,
                context=context,
                image_paths=image_paths,
            )
            self._add_event("生成回复", "Preview response completed in mock mode.", "success")
            self._add_message("assistant", response)
            self.save_autosaved_conversations()
            self._set_busy(False)
            return

        prompt = self._build_codex_prompt(text, context) if self.current_provider.source == "codex" else text
        self._start_model_call(
            prompt=prompt,
            system_prompt=self._build_system_prompt(context),
            image_paths=image_paths,
            context=context,
        )

    def run_action(self, action: str) -> None:
        self._set_busy(True)
        self._active_task_id = uuid.uuid4().hex
        context = self.refresh_context()
        if action in {"create_nodes", "fix_error", "capture_viewport", "inspect_selection"}:
            if action == "create_nodes":
                result = self.adapter.create_node_preview(self.current_thinking_level)
            elif action == "fix_error":
                result = self.adapter.fix_error_preview(self.current_thinking_level)
            elif action == "inspect_selection":
                result = self.adapter.inspect_selection(self.current_thinking_level)
            else:
                result = self.adapter.capture_viewport_preview(self.current_thinking_level)
            self._add_event(result.get("title", action), "Started from toolbar action.", "info")
            for event in result.get("events", []):
                self._add_event(event.get("title", ""), event.get("detail", ""), event.get("status", "info"))
            self._add_message("assistant", result.get("message", "Done."), result.get("image_paths", []))
        elif self.current_provider.source == "codex" and action in {"analyze_scene"}:
            self._run_live_action(action, context)
            return
        elif self.current_provider.source not in {"mock", "codex"} and action in {"analyze_scene"}:
            self._run_live_action(action, context)
            return
        else:
            if action == "analyze_scene":
                result = self.adapter.analyze_scene(self.current_thinking_level)
            else:
                result = {"title": "未知操作", "events": [], "message": "No action was run."}

            self._add_event(result.get("title", action), "Started from toolbar action.", "info")
            for event in result.get("events", []):
                self._add_event(event.get("title", ""), event.get("detail", ""), event.get("status", "info"))
            self._add_message("assistant", result.get("message", "Done."), result.get("image_paths", []))
        self.save_autosaved_conversations()
        self._set_busy(False)

    def stop(self) -> None:
        if self._busy:
            self._add_event("停止任务", "Current preview task was marked as stopped.", "warning")
            self.save_autosaved_conversations()
        self._active_task_id = None
        self._set_busy(False)

    def _add_message(self, role: str, content: str, image_paths: Optional[List[str]] = None) -> None:
        message = AgentMessage(role=role, content=content, image_paths=image_paths or [])
        self.current_conversation.messages.append(message)
        self.message_added.emit(message)

    def _add_event(self, title: str, detail: str, status: str = "info") -> None:
        event = ExecutionEvent(title=title, detail=detail, status=status)
        self.current_conversation.events.append(event)
        self.event_added.emit(event)

    def _maybe_title_current_conversation(self, text: str, image_paths: List[str]) -> None:
        conversation = self.current_conversation
        if not conversation.title.startswith("新会话"):
            return
        if image_paths and not text:
            conversation.title = "图片识别"
        else:
            conversation.title = text[:18] + ("..." if len(text) > 18 else "")
        self.conversations_changed.emit(self.conversations)

    def _next_conversation_title(self) -> str:
        used = {conversation.title for conversation in self.conversations}
        index = len(self.conversations) + 1
        while f"新会话 {index}" in used:
            index += 1
        return f"新会话 {index}"

    def _set_busy(self, busy: bool) -> None:
        if self._busy != busy:
            self._busy = busy
            self.busy_changed.emit(busy)

    def _run_tool_intent_from_text(self, text: str) -> bool:
        normalized = text.lower()
        if any(keyword in normalized for keyword in ("修复", "fix", "repair", "错误", "error", "报错")):
            result = self.adapter.fix_error_preview(self.current_thinking_level)
            should_ask_model = self._tool_result_needs_model_followup(result)
        elif any(keyword in normalized for keyword in ("创建节点", "create node", "new node", "添加节点")):
            result = self.adapter.create_node_preview(self.current_thinking_level, request_text=text)
            should_ask_model = False
        elif any(keyword in normalized for keyword in ("创建", "建立", "生成", "create", "make", "add")) and self._looks_like_node_creation(text):
            result = self.adapter.create_node_preview(self.current_thinking_level, request_text=text)
            should_ask_model = False
        elif any(keyword in normalized for keyword in ("查看选中", "检查选中", "inspect selection", "selected node")):
            result = self.adapter.inspect_selection(self.current_thinking_level)
            should_ask_model = False
        elif any(keyword in normalized for keyword in ("截图", "捕获视口", "viewport", "capture")):
            result = self.adapter.capture_viewport_preview(self.current_thinking_level)
            should_ask_model = False
        else:
            return False

        self._add_event(result.get("title", "执行工具"), "Matched from chat request and executed in Houdini.", "info")
        for event in result.get("events", []):
            self._add_event(event.get("title", ""), event.get("detail", ""), event.get("status", "info"))
        self._add_message("assistant", result.get("message", "Done."), result.get("image_paths", []))
        self.refresh_context()
        if should_ask_model and self.current_provider.source != "mock":
            context = self.refresh_context()
            fix_context = self._error_fix_context()
            self._pending_model_fix_context = fix_context if fix_context.get("ok") else None
            prompt = self._build_fix_followup_prompt(text, context, fix_context, result)
            self._add_event("调用模型分析", "Local fix rules did not complete the repair; asking the selected model for diagnosis.", "running")
            self._start_model_call(
                prompt=self._build_codex_prompt(prompt, context) if self.current_provider.source == "codex" else prompt,
                system_prompt=self._build_system_prompt(context),
                image_paths=[],
                context=context,
            )
        else:
            self._set_busy(False)
        return True

    def _looks_like_node_creation(self, text: str) -> bool:
        lowered = text.lower()
        node_words = (
            "box",
            "cube",
            "sphere",
            "grid",
            "plane",
            "null",
            "merge",
            "transform",
            "wrangle",
            "attribwrangle",
            "立方体",
            "盒子",
            "球",
            "平面",
            "节点",
        )
        return any(word in lowered or word in text for word in node_words)

    def _tool_result_needs_model_followup(self, result: Dict[str, object]) -> bool:
        if any(event.get("status") == "success" and event.get("title") in {"更新代码参数", "重新 Cook"} for event in result.get("events", [])):
            return False
        message = str(result.get("message", ""))
        event_text = " ".join(f"{event.get('title', '')} {event.get('detail', '')}" for event in result.get("events", []))
        combined = f"{message} {event_text}"
        return any(fragment in combined for fragment in ("未匹配", "没有匹配", "仅诊断", "仍有错误", "失败"))

    def _error_fix_context(self) -> Dict[str, object]:
        getter = getattr(self.adapter, "error_fix_context", None)
        if getter is None:
            return {}
        try:
            return getter()
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def _build_fix_followup_prompt(
        self,
        user_text: str,
        context: Dict[str, object],
        fix_context: Dict[str, object],
        tool_result: Dict[str, object],
    ) -> str:
        return (
            "The Houdini plugin attempted its local executable repair tool, but it did not finish the repair.\n"
            "Analyze the error and produce a practical next repair. Be specific about the code line or parameter.\n"
            "If the code can be fixed by editing the shown snippet, provide the corrected full snippet in a fenced code block.\n"
            "Do not say the plugin has no Houdini interface; it just ran a Houdini tool and can apply supported edits.\n\n"
            f"User request: {user_text}\n"
            f"Scene context: {context}\n"
            f"Tool result: {tool_result}\n"
            f"Error/code context: {fix_context}\n"
        )

    def _start_model_call(
        self,
        prompt: str,
        system_prompt: str,
        image_paths: List[str],
        context: Dict[str, object],
    ) -> None:
        task_id = self._active_task_id or uuid.uuid4().hex
        self._active_task_id = task_id
        thread = QtCore.QThread(self)
        worker = ModelCallWorker(
            task_id=task_id,
            provider=self.current_provider,
            prompt=prompt,
            system_prompt=system_prompt,
            image_paths=image_paths,
            cwd=self._provider_workdir(context),
            thinking_level=self.current_thinking_level,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._model_call_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_worker_refs)
        self._active_thread = thread
        self._active_worker = worker
        self._add_event("后台思考", "Model call is running in a background thread; Houdini remains usable.", "running")
        thread.start()

    def _model_call_finished(self, task_id: str, response: str, event_title: str, event_detail: str, status: str) -> None:
        if task_id != self._active_task_id:
            return
        self._add_event(event_title, event_detail, status)
        self._add_message("assistant", response)
        if status == "success":
            self._apply_pending_model_fix(response)
        else:
            self._pending_model_fix_context = None
        self.save_autosaved_conversations()
        self._active_task_id = None
        self._set_busy(False)

    def _apply_pending_model_fix(self, response: str) -> None:
        fix_context = self._pending_model_fix_context
        self._pending_model_fix_context = None
        if not fix_context:
            return
        code = self._extract_first_code_block(response)
        if not code:
            self._add_event("模型修复未自动应用", "No fenced code block was found in the model response.", "warning")
            return
        applier = getattr(self.adapter, "apply_code_to_fix_target", None)
        if applier is None:
            self._add_event("模型修复未自动应用", "Current adapter does not support applying code edits.", "warning")
            return
        result = applier(fix_context, code)
        self._add_event(result.get("title", "Apply model fix"), "Applied from model response after repair analysis.", "info")
        for event in result.get("events", []):
            self._add_event(event.get("title", ""), event.get("detail", ""), event.get("status", "info"))
        self._add_message("assistant", result.get("message", "Model fix applied."))
        self.refresh_context()

    def _extract_first_code_block(self, text: str) -> str:
        match = re.search(r"```[^\n`]*\n(.*?)```", text, re.DOTALL)
        if not match:
            return ""
        return match.group(1).strip()

    def _clear_worker_refs(self) -> None:
        self._active_thread = None
        self._active_worker = None

    def _run_live_action(self, action: str, context: Dict[str, object]) -> None:
        action_titles = {
            "analyze_scene": "分析工程",
            "inspect_selection": "查看选中节点",
            "fix_error": "修复错误分析",
            "capture_viewport": "视口分析",
        }
        prompts = {
            "analyze_scene": (
                "Please analyze the current Houdini project context. "
                "Summarize what the scene appears to be doing, identify notable nodes or risks, "
                "and suggest the next 2-4 practical steps."
            ),
            "inspect_selection": (
                "Please inspect the selected Houdini nodes based on the provided context. "
                "Explain what the selection is likely responsible for, what to check next, "
                "and any likely parameter areas worth adjusting."
            ),
            "fix_error": (
                "Please analyze the current Houdini error and warning context. "
                "Give a likely root cause, a concrete repair plan, and the safest validation steps. "
                "Do not claim that the fix has already been executed."
            ),
            "capture_viewport": (
                "Please analyze the current viewport context. "
                "Describe what additional visual information would be useful, how to improve the view for diagnosis, "
                "and what viewport or render checks the user should perform next."
            ),
        }
        title = action_titles.get(action, action)
        self._add_event(title, "Started from toolbar action using live provider.", "info")
        self._add_event("收集上下文", self.adapter.describe_context(context), "running")
        if self.current_provider.source == "codex":
            self._start_model_call(
                prompt=self._build_codex_prompt(prompts[action], context),
                system_prompt=self._build_system_prompt(context),
                image_paths=[],
                context=context,
            )
        else:
            self._start_model_call(
                prompt=prompts[action],
                system_prompt=self._build_system_prompt(context),
                image_paths=[],
                context=context,
            )

    def _build_system_prompt(self, context: Dict[str, object]) -> str:
        selected_nodes = context.get("selected_nodes", [])
        if isinstance(selected_nodes, list):
            selected_summary = ", ".join(str(item) for item in selected_nodes[:8]) or "none"
        else:
            selected_summary = "none"
        return (
            "You are Houdini AI Agent, a helpful assistant working inside SideFX Houdini. "
            "Be concise, practical, and action-oriented. "
            "When the user attaches images, analyze them and relate them to Houdini workflows when relevant. "
            "When discussing the current project, use the provided scene context. "
            "Do not invent executed actions. If something is only a suggestion, say so clearly.\n\n"
            f"HIP: {context.get('hip_file', '')}\n"
            f"Network: {context.get('network', '')}\n"
            f"Selected nodes: {selected_summary}\n"
            f"Viewport: {context.get('viewport', '')}\n"
            f"Summary: {context.get('summary', '')}\n"
        )

    def _build_codex_prompt(self, user_text: str, context: Dict[str, object]) -> str:
        return (
            "You are Houdini AI Agent working inside SideFX Houdini.\n"
            "Be concise, practical, and honest about what has and has not been executed.\n"
            "The host plugin has executable Houdini tools for inspecting the selection, creating preview nodes, "
            "capturing the viewport, and applying first-pass error fixes. If the execution trace says a tool ran, "
            "treat that as already executed. If no tool ran, explain the next executable step instead of claiming "
            "there is no Houdini interface.\n"
            "Use the following Houdini context when answering.\n\n"
            f"HIP: {context.get('hip_file', '')}\n"
            f"Network: {context.get('network', '')}\n"
            f"Selected nodes: {', '.join(context.get('selected_nodes', [])) or 'none'}\n"
            f"Viewport: {context.get('viewport', '')}\n"
            f"Scene summary: {context.get('summary', '')}\n"
            f"Errors: {context.get('errors', [])}\n\n"
            f"User request:\n{user_text}"
        )

    def _provider_workdir(self, context: Dict[str, object]) -> str:
        hip_file = str(context.get("hip_file", "") or "").strip()
        if hip_file and hip_file.lower() != "unknown":
            path = Path(hip_file)
            if path.exists():
                return str(path.parent)
        return str(Path.home())

    def _storage_dir(self) -> Optional[Path]:
        getter = getattr(self.adapter, "get_session_storage_dir", None)
        if getter is None:
            return None
        storage_dir = getter()
        if storage_dir is None:
            return None
        return Path(storage_dir)

    def _read_per_conversation_storage(self, storage_dir: Path) -> tuple[List[Conversation], str]:
        sessions_dir = storage_dir / SESSIONS_DIR_NAME
        if not sessions_dir.exists():
            return [], ""

        index_path = storage_dir / SESSION_INDEX_FILE_NAME
        order = []
        current_id = ""
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text(encoding="utf-8"))
                order = list(index.get("conversation_order", []))
                current_id = str(index.get("current_conversation_id", ""))
            except Exception:
                order = []

        by_id = {}
        for path in sessions_dir.glob("*.json"):
            conversations, _ = self._read_conversation_file(path)
            for conversation in conversations:
                by_id[conversation.id] = conversation

        conversations = [by_id[item_id] for item_id in order if item_id in by_id]
        conversations.extend(conversation for item_id, conversation in by_id.items() if item_id not in order)
        return conversations, current_id

    def _legacy_payload(self) -> Dict[str, object]:
        return {
            "version": 1,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "current_conversation_id": self.current_conversation_id,
            "conversations": [self._conversation_to_dict(conversation, embed_images=False) for conversation in self.conversations],
        }

    def _conversation_to_dict(self, conversation: Conversation, embed_images: bool) -> Dict[str, object]:
        return {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "messages": [self._message_to_dict(message, embed_images) for message in conversation.messages],
            "events": [
                {
                    "title": event.title,
                    "detail": event.detail,
                    "status": event.status,
                    "timestamp": event.timestamp,
                }
                for event in conversation.events
            ],
        }

    def _message_to_dict(self, message: AgentMessage, embed_images: bool) -> Dict[str, object]:
        item = {
            "role": message.role,
            "content": message.content,
            "image_paths": list(message.image_paths),
            "timestamp": message.timestamp,
        }
        if embed_images:
            images = []
            for image_path in message.image_paths:
                path = Path(image_path)
                if not path.exists() or not path.is_file():
                    continue
                try:
                    images.append(
                        {
                            "file_name": path.name,
                            "original_path": str(path),
                            "data_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
                        }
                    )
                except Exception:
                    continue
            item["images"] = images
        return item

    def _read_conversation_file(self, path: Path) -> tuple[List[Conversation], str]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return [], ""

        if isinstance(raw, dict) and "conversation" in raw:
            entries = [raw["conversation"]]
        else:
            entries = raw.get("conversations", []) if isinstance(raw, dict) else raw
        if not isinstance(entries, list):
            return [], ""

        conversations = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            messages = [
                self._message_from_dict(message, str(item.get("id") or "imported"))
                for message in item.get("messages", [])
                if isinstance(message, dict)
            ]
            events = [
                ExecutionEvent(
                    title=str(event.get("title", "")),
                    detail=str(event.get("detail", "")),
                    status=str(event.get("status", "info")),
                    timestamp=str(event.get("timestamp", "")) or datetime.now().strftime("%H:%M:%S"),
                )
                for event in item.get("events", [])
                if isinstance(event, dict)
            ]
            conversations.append(
                Conversation(
                    id=str(item.get("id") or uuid.uuid4().hex),
                    title=str(item.get("title") or "导入会话"),
                    messages=messages,
                    events=events,
                    created_at=str(item.get("created_at") or datetime.now().strftime("%H:%M")),
                )
            )
        return conversations, str(raw.get("current_conversation_id", "")) if isinstance(raw, dict) else ""

    def _message_from_dict(self, message: Dict[str, object], conversation_id: str) -> AgentMessage:
        image_paths = list(message.get("image_paths", []))
        embedded = message.get("images", [])
        if isinstance(embedded, list) and embedded:
            image_paths = []
            for image in embedded:
                restored = self._restore_embedded_image(image, conversation_id)
                if restored:
                    image_paths.append(str(restored))
        return AgentMessage(
            role=str(message.get("role", "")),
            content=str(message.get("content", "")),
            image_paths=image_paths,
            timestamp=str(message.get("timestamp", "")) or datetime.now().strftime("%H:%M:%S"),
        )

    def _restore_embedded_image(self, image: object, conversation_id: str) -> Optional[Path]:
        if not isinstance(image, dict):
            return None
        data = str(image.get("data_base64", ""))
        if not data:
            return None
        file_name = Path(str(image.get("file_name", "image.png"))).name or "image.png"
        target_dir = self._image_dir(conversation_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = self._unique_path(target_dir / file_name)
        try:
            target.write_bytes(base64.b64decode(data))
            return target
        except Exception:
            return None

    def _materialize_conversation_images(self, conversation: Conversation, storage_dir: Path) -> None:
        for message in conversation.messages:
            message.image_paths = self._materialize_image_paths(conversation.id, message.image_paths, storage_dir=storage_dir)

    def _materialize_image_paths(
        self,
        conversation_id: str,
        image_paths: List[str],
        storage_dir: Optional[Path] = None,
    ) -> List[str]:
        if not image_paths:
            return []
        storage_dir = storage_dir or self._storage_dir()
        if storage_dir is None:
            return list(image_paths)

        materialized = []
        target_dir = Path(storage_dir) / IMAGES_DIR_NAME / conversation_id
        for image_path in image_paths:
            path = Path(image_path)
            if not path.exists() or not path.is_file():
                materialized.append(image_path)
                continue
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                try:
                    if target_dir.resolve() in path.resolve().parents:
                        materialized.append(str(path))
                        continue
                except Exception:
                    if target_dir in path.parents:
                        materialized.append(str(path))
                        continue
                target = self._unique_path(target_dir / path.name)
                shutil.copy2(str(path), str(target))
                materialized.append(str(target))
            except Exception:
                materialized.append(image_path)
        if materialized != list(image_paths):
            self.storage_status = f"图片已更新到：{target_dir}"
            self.storage_status_changed.emit(self.storage_status)
        return materialized

    def _image_dir(self, conversation_id: str) -> Path:
        storage_dir = self._storage_dir()
        if storage_dir is None:
            storage_dir = Path(tempfile.gettempdir()) / "houdini_ai_agent_imports"
        return Path(storage_dir) / IMAGES_DIR_NAME / conversation_id

    def _unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        for index in range(1, 10000):
            candidate = path.with_name(f"{stem}_{index}{suffix}")
            if not candidate.exists():
                return candidate
        return path.with_name(f"{stem}_{uuid.uuid4().hex}{suffix}")

    def _delete_conversation_files(self, conversation_id: str) -> None:
        storage_dir = self._storage_dir()
        if storage_dir is None:
            return
        candidates = [
            storage_dir / SESSIONS_DIR_NAME / f"{conversation_id}.json",
            storage_dir / IMAGES_DIR_NAME / conversation_id,
        ]
        for path in candidates:
            try:
                if path.is_dir():
                    shutil.rmtree(str(path))
                elif path.exists():
                    path.unlink()
            except Exception:
                continue
