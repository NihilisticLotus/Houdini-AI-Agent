"""Agent session and conversation state used by the panel."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime
import json
import locale
import re
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional
import uuid

from houdini_ai_agent.core.action_runner import ActionRunner
from houdini_ai_agent.core.codex_cli import CodexCallError, send_codex_chat
from houdini_ai_agent.core.config import (
    LastSelectionConfig,
    ProviderConfig,
    VisionBackendConfig,
    load_last_selection,
    load_providers,
    load_ui_language,
    load_vision_backend,
    load_work_mode,
    save_last_selection,
    save_ui_language,
    save_work_mode,
)
from houdini_ai_agent.core.openai_compat import (
    ProviderCallError,
    build_reasoning_effort,
    describe_images,
    send_chat,
)
from houdini_ai_agent.core.plan_store import PlanStore
from houdini_ai_agent.core.tool_registry import WORK_MODE_AGENT, WORK_MODE_PLAN, WORK_MODES, get_default_tool_registry
from houdini_ai_agent.core.vision_router import (
    VisionBackendResolution,
    VisionRouter,
    provider_can_read_images,
)
from houdini_ai_agent.qt import QtCore


THINKING_LEVELS: Dict[str, Dict[str, str]] = {
    "\u4f4e": {"effort": "low", "description": "\u66f4\u5feb\u3001\u66f4\u7701 token\uff0c\u9002\u5408\u5c0f\u578b\u64cd\u4f5c"},
    "\u4e2d": {"effort": "medium", "description": "\u9ed8\u8ba4\u6863\uff0c\u9002\u5408\u5e38\u89c4\u5de5\u7a0b\u89e3\u91ca"},
    "\u9ad8": {"effort": "high", "description": "\u9002\u5408\u9519\u8bef\u5206\u6790\u548c\u591a\u6b65\u64cd\u4f5c"},
    "\u8d85\u9ad8": {"effort": "xhigh", "description": "\u9002\u5408\u590d\u6742\u8bca\u65ad\u548c\u81ea\u52a8\u4fee\u590d"},
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
    plans: Dict[str, Dict[str, object]] = field(default_factory=dict)
    todos: List[Dict[str, object]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%H:%M"))


class ModelCallWorker(QtCore.QObject):
    finished = QtCore.Signal(str, str, str, str, str)
    progress = QtCore.Signal(str, str, str)

    def __init__(
        self,
        task_id: str,
        provider: ProviderConfig,
        prompt: str,
        vision_prompt: str,
        system_prompt: str,
        image_paths: List[str],
        vision_provider: Optional[ProviderConfig],
        response_language: str,
        cwd: str,
        thinking_level: str,
        parent=None,
    ):
        super().__init__(parent)
        self.task_id = task_id
        self.provider = provider
        self.prompt = prompt
        self.vision_prompt = vision_prompt
        self.system_prompt = system_prompt
        self.image_paths = image_paths
        self.vision_provider = vision_provider
        self.response_language = response_language
        self.cwd = cwd
        self.thinking_level = thinking_level
        self._cancel_event = threading.Event()
        self._process_holder: Dict[str, object] = {}

    def cancel(self) -> None:
        self._cancel_event.set()
        process = self._process_holder.get("process")
        if process is not None:
            try:
                process.terminate()
            except Exception:
                pass

    def run(self) -> None:
        try:
            prompt = self.prompt
            image_paths = list(self.image_paths)
            if image_paths and not provider_can_read_images(self.provider):
                if self.vision_provider is not None:
                    self.progress.emit(
                        "Vision fallback",
                        f"Using {self.vision_provider.name} to interpret {len(image_paths)} image(s) for {self.provider.name}.",
                        "running",
                    )
                    summary = describe_images(
                        provider=self.vision_provider,
                        user_text=self.vision_prompt,
                        image_paths=image_paths,
                        response_language=self.response_language,
                        cwd=self.cwd,
                        cancel_event=self._cancel_event,
                        process_holder=self._process_holder,
                    )
                    prompt = f"{prompt}\n\nVision companion notes:\n{summary}"
                    image_paths = []
                    self.progress.emit(
                        "Vision fallback completed",
                        f"Collected image notes from {self.vision_provider.name}.",
                        "success",
                    )
                else:
                    prompt = (
                        f"{prompt}\n\n"
                        "Note: The user attached image files, but the current model cannot read images and no fallback vision provider is configured. "
                        "Do not claim to have seen the images; explain that a vision-capable provider is needed for image understanding."
                    )
                    image_paths = []
                    self.progress.emit(
                        "Vision unavailable",
                        f"{self.provider.name} does not support image input and no vision fallback provider is configured.",
                        "warning",
                    )

            if self.provider.source == "codex":
                response = send_codex_chat(
                    prompt=prompt,
                    image_paths=image_paths,
                    model=self.provider.model,
                    cwd=self.cwd,
                    cancel_event=self._cancel_event,
                    process_holder=self._process_holder,
                )
                if (
                    image_paths
                    and self.vision_provider is not None
                    and self.vision_provider.name != self.provider.name
                    and self._response_indicates_missing_image(response)
                ):
                    self.progress.emit(
                        "Vision retry",
                        f"{self.provider.name} replied as if no image was received; retrying through {self.vision_provider.name}.",
                        "warning",
                    )
                    summary = describe_images(
                        provider=self.vision_provider,
                        user_text=self.vision_prompt,
                        image_paths=image_paths,
                        response_language=self.response_language,
                        cwd=self.cwd,
                        cancel_event=self._cancel_event,
                        process_holder=self._process_holder,
                    )
                    response = send_codex_chat(
                        prompt=f"{self.prompt}\n\nVision companion notes:\n{summary}",
                        image_paths=[],
                        model=self.provider.model,
                        cwd=self.cwd,
                        cancel_event=self._cancel_event,
                        process_holder=self._process_holder,
                    )
                if self._cancel_event.is_set():
                    self.finished.emit(self.task_id, "\u8bf7\u6c42\u5df2\u505c\u6b62\u3002", "\u5df2\u505c\u6b62", "Model call was stopped before completion.", "warning")
                    return
                detail = f"Local Codex reply received via {self.provider.model or 'default model'}."
                self.finished.emit(self.task_id, response, "\u751f\u6210\u56de\u590d", detail, "success")
            else:
                if self._cancel_event.is_set():
                    self.finished.emit(self.task_id, "\u8bf7\u6c42\u5df2\u505c\u6b62\u3002", "\u5df2\u505c\u6b62", "Model call was stopped before completion.", "warning")
                    return
                response = send_chat(
                    provider=self.provider,
                    system_prompt=self.system_prompt,
                    user_text=prompt,
                    image_paths=image_paths,
                    thinking_level=self.thinking_level,
                    max_tokens=1400,
                )
                if (
                    image_paths
                    and self.vision_provider is not None
                    and self.vision_provider.name != self.provider.name
                    and self._response_indicates_missing_image(response)
                ):
                    self.progress.emit(
                        "Vision retry",
                        f"{self.provider.name} replied as if no image was received; retrying through {self.vision_provider.name}.",
                        "warning",
                    )
                    summary = describe_images(
                        provider=self.vision_provider,
                        user_text=self.vision_prompt,
                        image_paths=image_paths,
                        response_language=self.response_language,
                        cwd=self.cwd,
                        cancel_event=self._cancel_event,
                        process_holder=self._process_holder,
                    )
                    response = send_chat(
                        provider=self.provider,
                        system_prompt=self.system_prompt,
                        user_text=f"{self.prompt}\n\nVision companion notes:\n{summary}",
                        image_paths=[],
                        thinking_level=self.thinking_level,
                        max_tokens=1400,
                    )
                if self._cancel_event.is_set():
                    self.finished.emit(self.task_id, "\u8bf7\u6c42\u5df2\u505c\u6b62\u3002", "\u5df2\u505c\u6b62", "Model call was stopped before completion.", "warning")
                    return
                detail = f"Live provider response received via {self.provider.name} ({build_reasoning_effort(self.thinking_level)} reasoning)."
                self.finished.emit(self.task_id, response, "\u751f\u6210\u56de\u590d", detail, "success")
        except (CodexCallError, ProviderCallError) as exc:
            if self._cancel_event.is_set():
                self.finished.emit(self.task_id, "\u8bf7\u6c42\u5df2\u505c\u6b62\u3002", "\u5df2\u505c\u6b62", "Model call was stopped before completion.", "warning")
                return
            self.finished.emit(self.task_id, f"\u6a21\u578b\u8c03\u7528\u5931\u8d25\uff1a{exc}", "\u6a21\u578b\u8c03\u7528\u5931\u8d25", str(exc), "error")
        except Exception as exc:
            if self._cancel_event.is_set():
                self.finished.emit(self.task_id, "\u8bf7\u6c42\u5df2\u505c\u6b62\u3002", "\u5df2\u505c\u6b62", "Model call was stopped before completion.", "warning")
                return
            self.finished.emit(self.task_id, f"\u6a21\u578b\u8c03\u7528\u5f02\u5e38\uff1a{exc}", "\u6a21\u578b\u8c03\u7528\u5f02\u5e38", str(exc), "error")


    def _response_indicates_missing_image(self, response: str) -> bool:
        normalized = (response or "").lower()
        markers = [
            "didn't receive",
            "did not receive",
            "can't see the image",
            "cannot see the image",
            "no image was provided",
            "image was not attached",
            "i could not access the image",
            "i couldn't access the image",
            "\u6ca1\u6709\u68c0\u6d4b\u5230\u56fe\u7247",
            "\u6ca1\u6709\u6536\u5230\u56fe\u7247",
            "\u672a\u6536\u5230\u56fe\u7247",
            "\u65e0\u6cd5\u770b\u5230\u56fe\u7247",
            "\u65e0\u6cd5\u8bc6\u522b\u4f60\u9644\u5e26\u7684\u56fe\u7247",
            "\u56fe\u7247\u6ca1\u6709\u4f20\u8fc7\u6765",
            "\u6ca1\u6709\u63a5\u6536\u5230\u56fe\u7247",
        ]
        return any(marker in normalized for marker in markers)

class AgentSession(QtCore.QObject):
    message_added = QtCore.Signal(object)
    event_added = QtCore.Signal(object)
    context_changed = QtCore.Signal(dict)
    providers_changed = QtCore.Signal(list)
    busy_changed = QtCore.Signal(bool)
    conversations_changed = QtCore.Signal(list)
    conversation_changed = QtCore.Signal(object)
    storage_status_changed = QtCore.Signal(str)
    work_mode_changed = QtCore.Signal(str)
    todo_changed = QtCore.Signal(list)

    def __init__(self, adapter, parent=None):
        super().__init__(parent)
        self.adapter = adapter
        self.providers: List[ProviderConfig] = load_providers()
        self.vision_backend = load_vision_backend()
        self.ui_language = load_ui_language()
        self.plan_store = PlanStore()
        self.tool_registry = get_default_tool_registry()
        self.work_mode = self.tool_registry.normalize_mode(load_work_mode())
        self.current_provider_index = 0
        self.current_thinking_level = "中"
        self._restore_last_selection(load_last_selection())
        self.context: Dict[str, object] = {}
        self._busy = False
        self._active_task_id: Optional[str] = None
        self._active_thread = None
        self._active_worker = None
        self._pending_model_fix_context: Optional[Dict[str, object]] = None
        self._pending_plans: Dict[str, Dict[str, object]] = {}
        self._active_plan_execution: Optional[Dict[str, object]] = None
        self._last_user_text = ""
        self._queued_followup_call: Optional[Dict[str, object]] = None
        self._tool_repair_attempts = 0
        self._max_tool_repair_attempts = 2
        self._loading = False
        self.storage_status = ""
        self.conversations: List[Conversation] = []
        self.current_conversation_id = ""
        self._needs_pending_plan_rebuild = True

        if not self.load_autosaved_conversations():
            self.create_conversation("新会话")

        if self._needs_pending_plan_rebuild:
            self._rebuild_pending_plans()

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
        self.todo_changed.emit([])
        self.save_autosaved_conversations()
        return conversation

    def switch_conversation(self, conversation_id: str) -> None:
        if conversation_id == self.current_conversation_id:
            return
        if any(item.id == conversation_id for item in self.conversations):
            self.current_conversation_id = conversation_id
            self.conversation_changed.emit(self.current_conversation)
            self.todo_changed.emit(list(self.current_conversation.todos))
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
            self.todo_changed.emit(list(self.current_conversation.todos))
        self.conversations_changed.emit(self.conversations)
        self._rebuild_pending_plans()
        self._delete_conversation_files(conversation_id)
        self.save_autosaved_conversations()
        return True

    def clear_conversation_history(self, conversation_id: str) -> bool:
        conversation = self._conversation_by_id(conversation_id)
        if conversation is None:
            return False
        conversation.messages = []
        conversation.events = []
        conversation.plans = {}
        conversation.todos = []
        self._rebuild_pending_plans()
        self.conversations_changed.emit(self.conversations)
        if conversation.id == self.current_conversation_id:
            self.conversation_changed.emit(conversation)
            self.todo_changed.emit([])
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
        self._rebuild_pending_plans()
        self.conversations_changed.emit(self.conversations)
        self.conversation_changed.emit(self.current_conversation)
        self.todo_changed.emit(list(self.current_conversation.todos))
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
        self._rebuild_pending_plans()
        self._loading = False
        self.conversations_changed.emit(self.conversations)
        self.conversation_changed.emit(self.current_conversation)
        self.todo_changed.emit(list(self.current_conversation.todos))
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
        if not self.providers:
            return
        self.current_provider_index = max(0, min(index, len(self.providers) - 1))
        self._save_last_selection()

    def set_current_model(self, model: str) -> None:
        model = model.strip()
        if not model:
            return
        self.current_provider.model = model
        self._save_last_selection()
        self.providers_changed.emit(self.providers)

    def set_thinking_level(self, level: str) -> None:
        if level in THINKING_LEVELS:
            self.current_thinking_level = level
            self._save_last_selection()

    def set_providers(self, providers: List[ProviderConfig]) -> None:
        self.providers = providers
        self.current_provider_index = min(self.current_provider_index, max(0, len(providers) - 1))
        self._restore_last_selection(load_last_selection())
        self.providers_changed.emit(self.providers)

    def set_runtime_settings(self, providers: List[ProviderConfig], vision_backend: VisionBackendConfig) -> None:
        self.providers = providers
        self.vision_backend = vision_backend
        self.current_provider_index = min(self.current_provider_index, max(0, len(providers) - 1))
        self._restore_last_selection(load_last_selection())
        self._save_last_selection()
        self.providers_changed.emit(self.providers)

    def _restore_last_selection(self, selection: LastSelectionConfig) -> None:
        if not self.providers:
            return
        provider_index = self._find_provider_index(selection)
        if provider_index is not None:
            self.current_provider_index = provider_index
            model = selection.model.strip()
            if model:
                self.providers[provider_index].model = model
        if selection.thinking_level in THINKING_LEVELS:
            self.current_thinking_level = selection.thinking_level

    def _find_provider_index(self, selection: LastSelectionConfig) -> Optional[int]:
        matches = [
            (selection.provider_source or "").strip().lower(),
            (selection.provider_name or "").strip().lower(),
            (selection.provider_base_url or "").strip().lower(),
        ]
        if not any(matches):
            return None
        for index, provider in enumerate(self.providers):
            source = provider.source.strip().lower()
            name = provider.name.strip().lower()
            base_url = provider.base_url.strip().lower()
            if matches[0] and source != matches[0]:
                continue
            if matches[1] and name != matches[1]:
                continue
            if matches[2] and base_url != matches[2]:
                continue
            return index
        for index, provider in enumerate(self.providers):
            if matches[1] and provider.name.strip().lower() == matches[1]:
                return index
        return None

    def _save_last_selection(self) -> None:
        if not self.providers:
            return
        provider = self.current_provider
        save_last_selection(
            LastSelectionConfig(
                provider_name=provider.name,
                provider_source=provider.source,
                provider_base_url=provider.base_url,
                model=provider.model,
                thinking_level=self.current_thinking_level,
            )
        )

    def set_ui_language(self, language: str) -> None:
        self.ui_language = "en" if language == "en" else "zh"
        save_ui_language(self.ui_language)

    def set_work_mode(self, mode: str) -> None:
        normalized = self.tool_registry.normalize_mode(mode)
        if normalized == self.work_mode:
            return
        self.work_mode = normalized
        save_work_mode(normalized)
        self.work_mode_changed.emit(normalized)
        self._add_event("切换工作模式", self._mode_status_text(), "info")
        self.save_autosaved_conversations()

    def toolbar_action_allowed(self, action: str) -> bool:
        return self.tool_registry.is_toolbar_action_allowed(self.work_mode, action)

    def toolbar_action_tooltip(self, action: str) -> str:
        tool_name = self.tool_registry.toolbar_tool_name(action)
        if not tool_name:
            return ""
        tool = self.tool_registry.get(tool_name)
        if tool is None:
            return ""
        if self.tool_registry.is_tool_allowed(self.work_mode, tool_name):
            return f"{tool.label}: {tool.description}"
        return self._blocked_message(tool_name)

    def _rebuild_pending_plans(self) -> None:
        self._pending_plans = self.plan_store.rebuild_pending(self.conversations)
        self._needs_pending_plan_rebuild = False

    def _store_plan(self, plan: Dict[str, object]) -> None:
        self.plan_store.store(self.current_conversation, self._pending_plans, plan)

    def _sync_plan_message(self, plan: Dict[str, object]) -> None:
        if self.plan_store.update_plan_message(self.current_conversation.messages, plan):
            self.conversation_changed.emit(self.current_conversation)

    def _set_plan_step_status(self, plan: Dict[str, object], index: int, status: str, message: str = "") -> None:
        self.plan_store.set_step_status(plan, index, status, message)
        self._sync_plan_message(plan)

    def _add_todo(self, title: str, detail: str = "", status: str = "pending") -> Dict[str, object]:
        allowed = {"pending", "in_progress", "done", "error"}
        todo = {
            "id": uuid.uuid4().hex,
            "title": (title or "Task").strip(),
            "detail": (detail or "").strip(),
            "status": status if status in allowed else "pending",
        }
        self.current_conversation.todos.append(todo)
        self.todo_changed.emit(list(self.current_conversation.todos))
        self.save_autosaved_conversations()
        return {
            "title": "Update todo",
            "events": [{"title": "Add todo", "detail": todo["title"], "status": "success"}],
            "message": f"Added todo: {todo['title']}",
        }

    def _update_todo(self, todo_id: str = "", title: str = "", status: str = "", detail: str = "") -> Dict[str, object]:
        allowed = {"pending", "in_progress", "done", "error"}
        normalized_id = (todo_id or "").strip()
        normalized_title = (title or "").strip().lower()
        target = None
        for todo in self.current_conversation.todos:
            if normalized_id and str(todo.get("id") or "") == normalized_id:
                target = todo
                break
            if normalized_title and str(todo.get("title") or "").strip().lower() == normalized_title:
                target = todo
                break
        if target is None:
            return {
                "title": "Update todo",
                "events": [{"title": "Todo not found", "detail": normalized_id or title or "<empty>", "status": "warning"}],
                "message": "Todo was not found; add it first if this task should be tracked.",
            }
        if status:
            target["status"] = status if status in allowed else str(target.get("status") or "pending")
        if title:
            target["title"] = title
        if detail:
            target["detail"] = detail
        self.todo_changed.emit(list(self.current_conversation.todos))
        self.save_autosaved_conversations()
        return {
            "title": "Update todo",
            "events": [{"title": "Todo updated", "detail": str(target.get("title") or ""), "status": "success"}],
            "message": f"Updated todo: {target.get('title')}",
        }

    def confirm_plan(self, plan_id: str) -> None:
        plan = self._pending_plans.get(plan_id)
        if plan is None:
            self._add_event("计划确认失败", f"找不到计划：{plan_id}", "warning")
            self._add_message("assistant", "这个计划已经不存在或会话已刷新。请重新生成计划。")
            return
        if plan.get("status") not in {"draft", "confirmed", "paused"}:
            self._add_event("计划已处理", f"计划状态：{plan.get('status')}", "info")
            return
        plan["status"] = "executing"
        self._sync_plan_message(plan)
        self.set_work_mode(WORK_MODE_AGENT)
        self._add_event("确认计划", f"已确认计划：{plan.get('title') or plan_id}，切换到 Agent 模式执行。", "success")
        self._add_message("assistant", "已切换到 Agent 模式。我会按计划顺序执行，并在每一步后回报实际结果。")
        self.save_autosaved_conversations()
        self._start_plan_execution(plan)

    def cancel_plan(self, plan_id: str) -> None:
        plan = self._pending_plans.get(plan_id)
        if plan is None:
            return
        plan["status"] = "cancelled"
        self._sync_plan_message(plan)
        self._add_event("取消计划", f"已取消计划：{plan.get('title') or plan_id}", "warning")
        self._add_message("assistant", "已取消这个计划，不会切换到 Agent 执行。")
        self.save_autosaved_conversations()

    def _start_plan_execution(self, plan: Dict[str, object]) -> None:
        steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
        if not steps:
            self._add_event("计划执行停止", "计划没有可执行步骤。", "warning")
            return
        self._active_plan_execution = {"plan": plan, "step_index": 0, "completed": []}
        self._tool_repair_attempts = 0
        self._set_busy(True)
        self._run_next_plan_step()

    def _run_next_plan_step(self) -> bool:
        execution = self._active_plan_execution
        if not execution:
            return False
        plan = execution.get("plan") if isinstance(execution.get("plan"), dict) else {}
        steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
        index = int(execution.get("step_index") or 0)
        if index >= len(steps):
            plan["status"] = "completed"
            self._sync_plan_message(plan)
            self._active_plan_execution = None
            self._add_event("计划执行完成", f"已完成 {len(steps)} 个步骤。", "success")
            self._add_message("assistant", "计划步骤已按顺序执行完。请在 Houdini 里检查结果；如果视觉效果还需要调整，可以继续让我细化。")
            self.save_autosaved_conversations()
            self._set_busy(False)
            return True

        step = steps[index]
        if not isinstance(step, dict):
            step = {"title": str(step), "detail": ""}
            steps[index] = step
        execution["step_index"] = index + 1
        self._set_plan_step_status(plan, index, "in_progress")
        title = str(step.get("title") or f"Step {index + 1}")
        self._add_message("thought", self._format_plan_step_thought(plan, step, index, len(steps)))
        self._add_event("执行计划步骤", f"{index + 1}/{len(steps)}：{title}", "running")
        context = self.refresh_context()
        prompt = self._build_plan_step_prompt(plan, step, index, steps, context)
        self._start_model_call(
            prompt=prompt,
            vision_prompt=title,
            system_prompt=self._build_system_prompt(context, str(plan.get("goal") or self._last_user_text or title)),
            image_paths=[],
            context=context,
            show_thought=False,
        )
        return True

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
        image_paths = self._resolve_followup_image_paths(text, image_paths)
        image_paths = self._materialize_image_paths(self.current_conversation_id, image_paths)
        self._last_user_text = text

        self._set_busy(True)
        self._active_task_id = uuid.uuid4().hex
        self._add_message("user", text, image_paths)
        self._maybe_title_current_conversation(text, image_paths)
        self._add_event("收到请求", f"Thinking: {self.current_thinking_level} / Model: {self.current_provider.model}", "info")

        context = self.refresh_context()
        self._add_event("收集上下文", self.adapter.describe_context(context), "running")
        if image_paths:
            self._add_event("读取图片输入", f"{len(image_paths)} image(s) attached for vision analysis.", "running")

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

        prompt = self._build_agent_tool_prompt(text, context, has_images=bool(image_paths))
        self._start_model_call(
            prompt=prompt,
            vision_prompt=text,
            system_prompt=self._build_system_prompt(context, text),
            image_paths=image_paths,
            context=context,
        )

    def run_action(self, action: str) -> None:
        if not self._toolbar_action_allowed_or_report(action):
            return
        self._set_busy(True)
        self._active_task_id = uuid.uuid4().hex
        context = self.refresh_context()
        if self.current_provider.source != "mock":
            self._run_live_action(action, context)
            return

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
            worker = self._active_worker
            if worker is not None:
                try:
                    worker.cancel()
                except Exception:
                    pass
            self._add_message("assistant", "已停止当前模型请求。")
            self._add_event("停止任务", "Current preview task was marked as stopped.", "warning")
            self.save_autosaved_conversations()
        self._active_task_id = None
        self._set_busy(False)

    def _add_message(self, role: str, content: str, image_paths: Optional[List[str]] = None) -> None:
        message = AgentMessage(role=role, content=content, image_paths=image_paths or [])
        self.current_conversation.messages.append(message)
        self.message_added.emit(message)

    def _resolve_followup_image_paths(self, text: str, image_paths: List[str]) -> List[str]:
        if image_paths:
            return image_paths
        if not self._looks_like_image_followup(text):
            return []
        recent_images = self._recent_conversation_image_paths()
        if recent_images:
            self._add_event("沿用上一条图片", f"Reusing {len(recent_images)} recent image(s) because the request refers to a previous image.", "info")
        return recent_images

    def _looks_like_image_followup(self, text: str) -> bool:
        normalized = (text or "").lower()
        if not normalized:
            return False
        markers = (
            "这张图",
            "这个图",
            "这幅图",
            "上一张图",
            "刚才那张图",
            "刚刚那张图",
            "上图",
            "前面的图",
            "这张截图",
            "这个截图",
            "那张图",
            "那幅图",
            "图片",
            "截图",
            "that image",
            "this image",
            "the image",
            "that screenshot",
            "this screenshot",
            "the screenshot",
            "previous image",
            "previous screenshot",
            "above image",
        )
        return any(marker in normalized or marker in text for marker in markers)

    def _recent_conversation_image_paths(self) -> List[str]:
        for message in reversed(self.current_conversation.messages[:-1]):
            if message.role == "user" and message.image_paths:
                return list(message.image_paths)
        return []

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

    def _mode_status_text(self) -> str:
        meta = WORK_MODES.get(self.work_mode)
        if meta is None:
            return f"Current mode: {self.work_mode}"
        return f"当前模式：{meta.label}。{meta.description}"

    def _blocked_message(self, tool_or_action: str) -> str:
        tool_label = self.tool_registry.tool_label(tool_or_action)
        mode_label = self.tool_registry.mode_label(self.work_mode)
        return f"当前 {mode_label} 模式不允许执行 {tool_label}。请切换到 Agent 模式后再运行会改变 Houdini 场景的工具。"

    def _toolbar_action_allowed_or_report(self, action: str) -> bool:
        if self.toolbar_action_allowed(action):
            return True
        tool_name = self.tool_registry.toolbar_tool_name(action) or action
        message = self._blocked_message(tool_name)
        self._add_event("工具被模式拦截", message, "warning")
        self._add_message("assistant", message)
        self.save_autosaved_conversations()
        return False

    def _model_action_allowed_or_report(self, action: str) -> bool:
        if not self.tool_registry.has_tool(action):
            return True
        if self.tool_registry.is_tool_allowed(self.work_mode, action):
            return True
        message = self._blocked_message(action)
        self._add_event("模型工具被模式拦截", message, "warning")
        return False

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
                vision_prompt=text,
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
        vision_prompt: str,
        system_prompt: str,
        image_paths: List[str],
        context: Dict[str, object],
        show_thought: bool = True,
    ) -> None:
        task_id = self._active_task_id or uuid.uuid4().hex
        self._active_task_id = task_id
        vision_resolution = self._resolve_vision_backend(self.current_provider) if image_paths else VisionBackendResolution(None, "disabled")
        vision_provider = vision_resolution.provider
        response_language = self._preferred_response_language(vision_prompt)
        thread = QtCore.QThread(self)
        worker = ModelCallWorker(
            task_id=task_id,
            provider=self.current_provider,
            prompt=prompt,
            vision_prompt=vision_prompt,
            system_prompt=system_prompt,
            image_paths=image_paths,
            vision_provider=vision_provider,
            response_language=response_language,
            cwd=self._provider_workdir(context),
            thinking_level=self.current_thinking_level,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._add_event)
        worker.finished.connect(self._model_call_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda task_id=task_id, thread=thread: self._clear_worker_refs(task_id, thread))
        self._active_thread = thread
        self._active_worker = worker
        if vision_resolution.status and image_paths and not provider_can_read_images(self.current_provider):
            self._add_event("Vision backend", vision_resolution.status, "warning")
        if show_thought:
            self._add_message("thought", self._format_live_request_plan(context, image_paths, vision_resolution))
        self._add_event("后台思考", "Model call is running in a background thread; Houdini remains usable.", "running")
        thread.start()

    def _format_live_request_plan(
        self,
        context: Dict[str, object],
        image_paths: List[str],
        vision_resolution: VisionBackendResolution,
    ) -> str:
        if image_paths and provider_can_read_images(self.current_provider):
            vision_text = "\u5f53\u524d\u6a21\u578b\u76f4\u63a5\u8bfb\u56fe"
        elif image_paths and vision_resolution.provider is not None:
            vision_text = f"\u5148\u7531 {vision_resolution.provider.name} \u8bfb\u56fe\uff0c\u518d\u4ea4\u7ed9\u5f53\u524d\u6a21\u578b\u7ee7\u7eed\u5206\u6790"
        elif image_paths and vision_resolution.status:
            vision_text = vision_resolution.status
        elif image_paths:
            vision_text = "\u5f53\u524d\u6ca1\u6709\u53ef\u7528\u7684\u89c6\u89c9\u80fd\u529b"
        else:
            vision_text = "\u672c\u8f6e\u6ca1\u6709\u56fe\u7247\u8f93\u5165"
        selected = context.get("selected_nodes", []) or []
        errors = context.get("errors", []) or []
        _unknown = "\u672a\u77e5"
        _none = "\u65e0"
        mode_label = self.tool_registry.mode_label(self.work_mode)
        available_tools = ", ".join(self.tool_registry.action_names_for_mode(self.work_mode)) or "无"
        if self.work_mode == WORK_MODE_PLAN:
            next_step = "生成可确认的结构化计划"
        elif self.work_mode == WORK_MODE_AGENT:
            next_step = "判断并执行可用工具动作"
        else:
            next_step = "回答问题或执行只读检查"
        lines = [
            f"模式：{mode_label}",
            f"已读取当前网络：{context.get('network', '') or _unknown}",
            f"已检查选择与错误：选中 {', '.join(selected[:3]) if selected else _none}，错误/警告 {len(errors)} 条",
            f"输入：图片 {len(image_paths)} 张，{vision_text}",
            f"可用工具：{available_tools}",
            f"下一步：{next_step}",
        ]
        return "\n".join(lines)

    def _model_call_finished(self, task_id: str, response: str, event_title: str, event_detail: str, status: str) -> None:
        if task_id != self._active_task_id:
            return
        self._add_event(event_title, event_detail, status)
        if status == "success":
            if self.work_mode == WORK_MODE_PLAN and self._handle_plan_response(response):
                pass
            elif not self._execute_model_action_response(response):
                if self._active_plan_execution:
                    blocker = "这一步没有返回可执行的 Houdini 工具动作，所以我已暂停计划，没有继续假装执行。请重新确认或调整这一步。"
                    self._handle_plan_step_without_actions(blocker)
                    self._add_message("assistant", blocker)
                else:
                    self._add_message("assistant", response)
                    self._apply_pending_model_fix(response)
        else:
            self._add_message("assistant", response)
            self._pending_model_fix_context = None
        self.save_autosaved_conversations()
        self._active_task_id = None
        followup = self._queued_followup_call
        self._queued_followup_call = None
        if followup:
            self._add_event("继续自我修复", "Tool execution failed; asking the model to diagnose and retry with corrected actions.", "running")
            self._start_model_call(
                prompt=str(followup.get("prompt") or ""),
                vision_prompt=str(followup.get("vision_prompt") or ""),
                system_prompt=str(followup.get("system_prompt") or ""),
                image_paths=[],
                context=followup.get("context") if isinstance(followup.get("context"), dict) else self.context,
                show_thought=False,
            )
            return
        if self._active_plan_execution and self._run_next_plan_step():
            return
        self._set_busy(False)

    def _execute_model_action_response(self, response: str) -> bool:
        payload = self._extract_model_json(response)
        if not payload:
            return False
        actions = payload.get("actions", [])
        if isinstance(payload.get("action"), str):
            actions = [payload]
        if not isinstance(actions, list) or not actions:
            reply = str(payload.get("response", "") or "").strip()
            if reply:
                self._add_message("assistant", reply)
                self._handle_plan_step_without_actions(reply)
                return True
            return False

        self._add_message("thought", self._format_model_plan(payload))
        reply_parts: List[str] = []
        failed_results: List[Dict[str, object]] = []
        executed_non_task_action = False

        for action in actions:
            if not isinstance(action, dict):
                continue
            action_name = str(action.get("action", "") or "").strip().lower()
            if not self._model_action_allowed_or_report(action_name):
                reply_parts.append(self._blocked_message(action_name))
                continue
            result = self._execute_model_action(action)
            self._add_event(result.get("title", "Model action"), "Selected by model plan.", "info")
            for event in result.get("events", []):
                self._add_event(event.get("title", ""), event.get("detail", ""), event.get("status", "info"))
            message = str(result.get("message", "") or "").strip()
            if message:
                reply_parts.append(message)
            if self._tool_result_has_error(result):
                failed_results.append({"action": action, "result": result})
            elif action_name not in {"add_todo", "update_todo"}:
                executed_non_task_action = True
            self.refresh_context()

        if self._active_plan_execution and not failed_results and not executed_non_task_action:
            reply = str(payload.get("response", "") or "").strip() or "这一步没有执行任何 Houdini 工具动作。"
            self._handle_plan_step_without_actions(reply)
            self._add_message("assistant", reply)
            return True

        if failed_results and self._schedule_tool_repair(actions, failed_results, payload):
            reply_parts.append("工具执行遇到错误。我会分析失败原因并尝试修正，不会停在这一步。")
        elif not failed_results:
            self._tool_repair_attempts = 0
            self._mark_current_plan_step_completed(reply_parts)

        self._add_message("assistant", "\n\n".join(reply_parts) if reply_parts else "Action completed.")
        return True

    def _mark_current_plan_step_completed(self, reply_parts: List[str]) -> None:
        execution = self._active_plan_execution
        if not execution:
            return
        plan = execution.get("plan") if isinstance(execution.get("plan"), dict) else {}
        steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
        completed_index = int(execution.get("step_index") or 0) - 1
        if completed_index < 0 or completed_index >= len(steps):
            return
        step = steps[completed_index]
        if isinstance(step, dict):
            step["status"] = "completed"
            if reply_parts:
                step["result"] = "\n".join(str(item) for item in reply_parts)[-500:]
            title = str(step.get("title") or f"Step {completed_index + 1}")
        else:
            title = str(step)
        completed = execution.get("completed")
        if not isinstance(completed, list):
            completed = []
            execution["completed"] = completed
        completed.append(f"{completed_index + 1}. {title}")
        self._sync_plan_message(plan)
        self._add_event("计划步骤完成", f"{completed_index + 1}/{len(steps)}：{title}", "success")
        if int(execution.get("step_index") or 0) < len(steps):
            reply_parts.append("我会继续执行下一步。")

    def _handle_plan_step_without_actions(self, reply: str) -> None:
        execution = self._active_plan_execution
        if not execution:
            return
        plan = execution.get("plan") if isinstance(execution.get("plan"), dict) else {}
        steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
        current_index = int(execution.get("step_index") or 0) - 1
        title = "当前步骤"
        if 0 <= current_index < len(steps) and isinstance(steps[current_index], dict):
            steps[current_index]["status"] = "blocked"
            steps[current_index]["result"] = reply[:500]
            title = str(steps[current_index].get("title") or title)
        plan["status"] = "blocked"
        self._sync_plan_message(plan)
        self._active_plan_execution = None
        self._add_event("计划步骤暂停", f"{title} 没有返回可执行动作：{reply[:180]}", "warning")

    def _tool_result_has_error(self, result: Dict[str, object]) -> bool:
        return self._action_runner().has_error(result)

    def _schedule_tool_repair(
        self,
        actions: List[object],
        failed_results: List[Dict[str, object]],
        payload: Dict[str, object],
    ) -> bool:
        if self.current_provider.source == "mock":
            return False
        if self._tool_repair_attempts >= self._max_tool_repair_attempts:
            self._add_event("自我修复已停止", f"已达到 {self._max_tool_repair_attempts} 次重试上限。", "warning")
            self._tool_repair_attempts = 0
            return False
        self._tool_repair_attempts += 1
        context = self.refresh_context()
        prompt = self._build_tool_repair_prompt(actions, failed_results, payload, context)
        self._queued_followup_call = {
            "prompt": prompt,
            "vision_prompt": "Analyze the failed Houdini tool call and return a corrected JSON action.",
            "system_prompt": self._build_system_prompt(context, "repair failed Houdini tool call"),
            "context": context,
        }
        self._add_event("准备自我修复", f"第 {self._tool_repair_attempts}/{self._max_tool_repair_attempts} 次：模型将分析工具错误并返回修正动作。", "warning")
        return True

    def _build_tool_repair_prompt(
        self,
        actions: List[object],
        failed_results: List[Dict[str, object]],
        payload: Dict[str, object],
        context: Dict[str, object],
    ) -> str:
        language = self._preferred_response_language(str(payload.get("response", "")))
        return (
            "A Houdini tool action just failed during Agent execution. Diagnose the failure and retry with a corrected action.\n"
            "Return ONLY one fenced JSON object that follows the available action schema. Do not give up after the first failure.\n"
            "If the failure means the requested operation needs a different node type, parent path, or safer fallback, choose that correction.\n"
            "If no safe executable correction exists, return an empty actions array and explain the blocker clearly.\n\n"
            "Important HOM hint: not every Houdini node supports every flag or parameter; object-level nodes and SOP nodes differ. Prefer supported HOM operations.\n\n"
            "JSON schema:\n"
            "{\n"
            '  "response": "short diagnosis and intended correction",\n'
            f"{self.tool_registry.format_action_schema(self.work_mode)}\n"
            "}\n\n"
            "Rules:\n"
            f"- User-facing response text must be in {language}.\n"
            "- Prefer one corrected action.\n"
            "- Do not repeat an action unchanged if the error shows it cannot work.\n"
            "- Use only actions listed in the schema.\n\n"
            f"Previous model payload: {json.dumps(payload, ensure_ascii=False)}\n"
            f"Actions attempted: {json.dumps(actions, ensure_ascii=False)}\n"
            f"Failed results: {json.dumps(failed_results, ensure_ascii=False)}\n"
            f"Current scene context after failure: {json.dumps(context, ensure_ascii=False)}\n"
        )

    def _handle_plan_response(self, response: str) -> bool:
        payload = self._extract_model_json(response)
        if payload:
            plan_data = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
            if isinstance(plan_data, dict):
                plan = self._normalize_plan(plan_data, response)
            else:
                plan = self._plan_from_text(response)
        else:
            plan = self._plan_from_text(response)

        steps = plan.get("steps", [])
        if not isinstance(steps, list) or not steps:
            return False

        self._store_plan(plan)
        self._add_message("plan", json.dumps(plan, ensure_ascii=False))
        self._add_event("生成执行计划", f"等待用户确认：{len(steps)} 个步骤。", "success")
        return True

    def _normalize_plan(self, data: Dict[str, object], source_text: str) -> Dict[str, object]:
        goal = str(data.get("goal") or data.get("summary") or data.get("response") or "").strip()
        language = self._preferred_response_language(self._last_user_text or goal or source_text)
        return self.plan_store.normalize_plan(data, source_text, language)

    def _plan_from_text(self, text: str) -> Dict[str, object]:
        return self.plan_store.plan_from_text(text, self._preferred_response_language(self._last_user_text or text))

    def _extract_steps_from_text(self, text: str) -> List[Dict[str, object]]:
        return self.plan_store.extract_steps_from_text(text)

    def _strip_plan_prefix(self, text: str) -> str:
        return self.plan_store.strip_plan_prefix(text)

    def _split_step_title_detail(self, text: str) -> tuple[str, str]:
        return self.plan_store.split_step_title_detail(text)

    def _format_plan_reasoning(self, plan: Dict[str, object]) -> str:
        steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
        selected = self.context.get("selected_nodes", []) or []
        errors = self.context.get("errors", []) or []
        lines = [
            "我把这轮请求按 Plan 模式处理。",
            f"目标：{plan.get('goal') or plan.get('title')}",
            "当前模式只允许观察和规划，不会直接修改 Houdini 场景。",
            f"上下文依据：网络 {self.context.get('network', '') or '未知'}；选中节点 {', '.join(selected[:3]) if selected else '无'}；错误 {len(errors)} 条。",
            f"执行顺序：共 {len(steps)} 步，按编号从上到下执行；每步默认依赖上一 步完成。",
            "下一步：你确认后，我会切换到 Agent 模式，并把这个计划作为执行约束传给模型。",
        ]
        return "\n".join(lines)

    def _format_plan_step_thought(self, plan: Dict[str, object], step: Dict[str, object], index: int, total: int) -> str:
        completed = []
        execution = self._active_plan_execution
        if execution and isinstance(execution.get("completed"), list):
            completed = list(execution.get("completed") or [])
        lines = [
            f"执行计划步骤 {index + 1}/{total}。",
            f"当前步骤：{step.get('title') or f'Step {index + 1}'}",
        ]
        detail = str(step.get("detail") or "").strip()
        if detail:
            lines.append(f"意图：{detail}")
        if completed:
            lines.append(f"已完成：{', '.join(str(item) for item in completed[-3:])}")
        lines.append("本轮只处理当前步骤；完成后我会自动进入下一步，不需要你再次发送。")
        return "\n".join(lines)

    def _build_plan_step_prompt(
        self,
        plan: Dict[str, object],
        step: Dict[str, object],
        index: int,
        steps: List[object],
        context: Dict[str, object],
    ) -> str:
        language = str(plan.get("language") or "").strip() or self._preferred_response_language(str(plan.get("goal") or plan.get("title") or self._last_user_text or ""))
        prior_steps = steps[:index]
        remaining_steps = steps[index + 1 :]
        return (
            "You are executing a confirmed Houdini plan one step at a time.\n"
            "Execute ONLY the current step, then stop. The host application will automatically call you again for the next step.\n"
            "Return ONLY one fenced JSON object. No prose outside the JSON. Use actions when a listed tool can make concrete progress.\n"
            "If this step needs multiple tightly coupled actions, include them in order. If a tool is not sufficient, explain the blocker in response with an empty actions array.\n\n"
            "JSON schema:\n"
            "{\n"
            '  "response": "short result summary for this step",\n'
            f"{self.tool_registry.format_action_schema(self.work_mode)}\n"
            "}\n\n"
            "Rules:\n"
            f"- User-facing response text must be in {language}.\n"
            "- Never write analysis paragraphs instead of actions. If you cannot execute, return an empty actions array and a short blocker.\n"
            "- Do not repeat already completed steps unless needed to repair a failure.\n"
            "- Do not jump ahead to later plan steps; the host will continue the sequence.\n"
            "- If a Houdini action fails, the host will ask you to diagnose and retry.\n\n"
            f"Plan title: {plan.get('title', '')}\n"
            f"Plan goal: {plan.get('goal', '')}\n"
            f"Current step index: {index + 1} of {len(steps)}\n"
            f"Current step: {json.dumps(step, ensure_ascii=False)}\n"
            f"Prior steps: {json.dumps(prior_steps, ensure_ascii=False)}\n"
            f"Remaining steps: {json.dumps(remaining_steps, ensure_ascii=False)}\n"
            f"Scene context: {json.dumps(context, ensure_ascii=False)}\n"
        )

    def _build_plan_execution_request(self, plan: Dict[str, object]) -> str:
        steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
        lines = [
            "执行刚才用户确认的 Houdini 计划。",
            f"目标：{plan.get('goal') or plan.get('title')}",
            "请严格按顺序推进；如果某步缺少必要信息，先停下说明，不要随意猜测。",
            "计划步骤：",
        ]
        for index, step in enumerate(steps, 1):
            if isinstance(step, dict):
                title = str(step.get("title") or f"Step {index}")
                detail = str(step.get("detail") or "")
                lines.append(f"{index}. {title}" + (f" - {detail}" if detail else ""))
            else:
                lines.append(f"{index}. {step}")
        return "\n".join(lines)

    def _format_model_plan(self, payload: Dict[str, object]) -> str:
        response = str(payload.get("response", "") or "").strip()
        actions = payload.get("actions", [])
        if isinstance(payload.get("action"), str):
            actions = [payload]
        lines = ["已处理模型回复"]
        if response:
            lines.append(f"模型摘要：{response}")
        if isinstance(actions, list) and actions:
            lines.append("准备执行工具动作：")
            for index, action in enumerate(actions, 1):
                if not isinstance(action, dict):
                    continue
                lines.append(f"{index}. {self._summarize_model_action(action)}")
        else:
            lines.append("本轮没有工具动作")
        return "\n".join(lines)

    def _summarize_model_action(self, action: Dict[str, object]) -> str:
        return self._action_runner().summarize(action)

    def _execute_model_action(self, action: Dict[str, object]) -> Dict[str, object]:
        return self._action_runner().execute(action)

    def _action_runner(self) -> ActionRunner:
        return ActionRunner(
            self.adapter,
            thinking_level=lambda: self.current_thinking_level,
            add_todo=self._add_todo,
            update_todo=self._update_todo,
        )

    def _extract_model_json(self, text: str) -> Dict[str, object]:
        candidates = []
        for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
            candidates.append(match.group(1).strip())
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            candidates.append(stripped)
        candidates.extend(self._extract_balanced_json_candidates(stripped))
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except Exception:
                continue
            if isinstance(payload, dict):
                nested_response = payload.get("response")
                if isinstance(nested_response, str) and ("```" in nested_response or "{" in nested_response):
                    nested = self._extract_model_json(nested_response)
                    if nested:
                        return nested
                return payload
        return {}

    def _extract_balanced_json_candidates(self, text: str) -> List[str]:
        candidates: List[str] = []
        starts = [index for index, char in enumerate(text) if char == "{"]
        for start in starts[:8]:
            depth = 0
            in_string = False
            escaped = False
            for index in range(start, len(text)):
                char = text[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start : index + 1])
                        break
        return candidates

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
        if not self._model_action_allowed_or_report("apply_code"):
            self._add_message("assistant", self._blocked_message("apply_code"))
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

    def _clear_worker_refs(self, task_id: str = "", thread=None) -> None:
        if thread is not None and self._active_thread is not thread:
            return
        if task_id and self._active_task_id not in {"", None, task_id}:
            return
        self._active_thread = None
        self._active_worker = None

    def _run_live_action(self, action: str, context: Dict[str, object]) -> None:
        action_titles = {
            "analyze_scene": "分析工程",
            "inspect_selection": "查看选中节点",
            "create_nodes": "创建节点",
            "fix_error": "修复错误分析",
            "capture_viewport": "视口分析",
        }
        prompt = self._toolbar_action_request(action)
        title = action_titles.get(action, action)
        self._add_event(title, "Started from toolbar action using live provider.", "info")
        self._add_event("收集上下文", self.adapter.describe_context(context), "running")
        self._start_model_call(
            prompt=self._build_agent_tool_prompt(prompt, context),
            vision_prompt=prompt,
            system_prompt=self._build_system_prompt(context, prompt),
            image_paths=[],
            context=context,
        )

    def _toolbar_action_request(self, action: str) -> str:
        requests = {
            "analyze_scene": "用户点击了“分析工程”。请基于当前 Houdini 上下文分析工程结构、风险和下一步建议。通常不需要调用工具，除非你判断必须执行可用工具。",
            "inspect_selection": "用户点击了“查看选中节点”。请基于当前 Houdini 上下文检查选中节点；如果需要读取选择信息，请调用 inspect_selection。",
            "create_nodes": "用户点击了“创建节点”。请基于当前 Houdini 上下文判断是否应创建节点；如果缺少具体节点类型，请给出简短澄清，不要随意创建。",
            "fix_error": "用户点击了“修复错误”。请分析当前选中节点和当前网络中的错误；如果可编辑代码参数可修复，请返回 apply_code action 写入完整修复代码并让插件执行。",
            "capture_viewport": "用户点击了“捕获视口”。请判断是否需要捕获当前视口；如需要，请调用 capture_viewport。",
        }
        return requests.get(action, f"用户点击了工具栏动作：{action}。请基于当前 Houdini 上下文决定是否调用可用工具。")

    def _preferred_response_language(self, user_text: str = "") -> str:
        if user_text and re.search(r"[\u4e00-\u9fff]", user_text):
            return "Simplified Chinese"
        if user_text and re.search(r"[A-Za-z]", user_text) and not re.search(r"[\u4e00-\u9fff]", user_text):
            return "English"
        try:
            qt_locale = QtCore.QLocale.system().name().lower()
        except Exception:
            qt_locale = ""
        try:
            py_locale = (locale.getlocale()[0] or "").lower()
        except Exception:
            py_locale = ""
        combined = f"{qt_locale} {py_locale}"
        if any(marker in combined for marker in ("zh", "chinese", "cn", "hans")):
            return "Simplified Chinese"
        return "English"

    def _build_system_prompt(self, context: Dict[str, object], user_text: str = "") -> str:
        selected_nodes = context.get("selected_nodes", [])
        if isinstance(selected_nodes, list):
            selected_summary = ", ".join(str(item) for item in selected_nodes[:8]) or "none"
        else:
            selected_summary = "none"
        language = self._preferred_response_language(user_text)
        return (
            "You are Houdini AI Agent, a helpful assistant working inside SideFX Houdini. "
            "Be concise, practical, and action-oriented. "
            "When the user attaches images, analyze them and relate them to Houdini workflows when relevant. "
            "When discussing the current project, use the provided scene context. "
            "Do not invent executed actions. If something is only a suggestion, say so clearly.\n\n"
            f"Response language: {language}. Always answer user-facing text in this language unless the user explicitly asks otherwise.\n\n"
            f"HIP: {context.get('hip_file', '')}\n"
            f"Network: {context.get('network', '')}\n"
            f"Selected nodes: {selected_summary}\n"
            f"Viewport: {context.get('viewport', '')}\n"
            f"Summary: {context.get('summary', '')}\n"
        )

    def _build_agent_tool_prompt(self, user_text: str, context: Dict[str, object], has_images: bool = False) -> str:
        fix_context = self._error_fix_context()
        language = self._preferred_response_language(user_text)
        image_instruction = ""
        if has_images:
            image_instruction = (
                "The user attached image files to this request. Analyze the attached image content before deciding whether a Houdini tool is needed. "
                "If you cannot access the image, return a concise response saying the image transport failed instead of pretending no image was attached.\n"
            )
        return (
            "You are controlling a Houdini plugin that can execute a small set of real HOM tools.\n"
            f"Work mode: {self.tool_registry.mode_label(self.work_mode)}. {self.tool_registry.mode_instruction(self.work_mode)}\n"
            "First decide from the user's request and scene context whether a tool should be executed.\n"
            f"{image_instruction}"
            "If a tool should run, return ONLY one fenced JSON object and no prose outside it.\n"
            "If no tool should run, return ONLY one fenced JSON object with an empty actions array and a concise response.\n\n"
            "JSON schema:\n"
            "{\n"
            '  "response": "short user-facing text, or empty string when the tool result is enough",\n'
            '  "plan": {"title": "only in Plan mode", "goal": "user goal", "steps": [{"id": "1", "title": "short step", "detail": "what will be done", "tool_hint": "likely Houdini action", "depends_on": []}], "risks": ["risk or validation note"]},\n'
            f"{self.tool_registry.format_action_schema(self.work_mode)}\n"
            "}\n\n"
            "Available tools in this mode:\n"
            f"{self.tool_registry.format_tool_summary(self.work_mode)}\n\n"
            "Rules:\n"
            f"- User-facing response text must be in {language} unless the user explicitly asks for another language.\n"
            "- Only use actions listed in the schema for the current mode.\n"
            "- For multi-step work, use add_todo/update_todo to expose compact progress; these internal task tools do not modify the Houdini scene.\n"
            "- In Agent mode, for creation requests choose the actual Houdini node type from intent. Examples: box -> box, plane/planar surface -> grid, sphere -> sphere.\n"
            "- In Agent mode, for error repair inspect the provided error/code context and return apply_code with the full corrected snippet when the target/code parameter is editable.\n"
            "- In Ask or Plan mode, do not return create_node or apply_code. Describe the proposed change instead.\n"
            "- In Plan mode, always return a structured plan object with ordered steps. Keep response empty or one short sentence; never put JSON text inside response.\n"
            "- Plan steps must be concise user-facing tasks, not raw JSON, not code, and not long paragraphs.\n"
            "- Do not say the plugin has no executable tools. Use actions when a tool matches.\n"
            "- Do not wrap code in Markdown inside the JSON; put the raw replacement string in the code field.\n"
            "- Prefer one action unless the user explicitly requests multiple operations.\n\n"
            f"User request: {user_text}\n"
            f"Scene context: {json.dumps(context, ensure_ascii=False)}\n"
            f"Editable error/code context: {json.dumps(fix_context, ensure_ascii=False)}\n"
        )

    def _build_codex_prompt(self, user_text: str, context: Dict[str, object], source_text: str = "") -> str:
        language = self._preferred_response_language(source_text or user_text)
        return (
            "You are Houdini AI Agent working inside SideFX Houdini.\n"
            "Be concise, practical, and honest about what has and has not been executed.\n"
            f"Current work mode: {self.tool_registry.mode_label(self.work_mode)}. {self.tool_registry.mode_instruction(self.work_mode)}\n"
            "The host plugin exposes mode-limited Houdini tools. "
            f"Available now: {', '.join(self.tool_registry.action_names_for_mode(self.work_mode)) or 'none'}. "
            "If the execution trace says a tool ran, "
            "treat that as already executed. If no tool ran, explain the next executable step instead of claiming "
            "there is no Houdini interface.\n"
            f"Respond in {language} unless the user explicitly asks for another language.\n"
            "Use the following Houdini context when answering.\n\n"
            f"HIP: {context.get('hip_file', '')}\n"
            f"Network: {context.get('network', '')}\n"
            f"Selected nodes: {', '.join(context.get('selected_nodes', [])) or 'none'}\n"
            f"Viewport: {context.get('viewport', '')}\n"
            f"Scene summary: {context.get('summary', '')}\n"
            f"Errors: {context.get('errors', [])}\n\n"
            f"User request:\n{user_text}"
        )

    def _resolve_vision_backend(self, primary: ProviderConfig) -> VisionBackendResolution:
        return VisionRouter(self.providers, self.vision_backend).resolve(primary)

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
            "plans": conversation.plans,
            "todos": conversation.todos,
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
                    plans=self._plans_from_dict(item.get("plans", {})),
                    todos=self._todos_from_list(item.get("todos", [])),
                    created_at=str(item.get("created_at") or datetime.now().strftime("%H:%M")),
                )
            )
        return conversations, str(raw.get("current_conversation_id", "")) if isinstance(raw, dict) else ""

    def _plans_from_dict(self, raw: object) -> Dict[str, Dict[str, object]]:
        return self.plan_store.plans_from_dict(raw)

    def _todos_from_list(self, raw: object) -> List[Dict[str, object]]:
        if not isinstance(raw, list):
            return []
        todos = []
        allowed = {"pending", "in_progress", "done", "error"}
        for index, item in enumerate(raw, 1):
            if not isinstance(item, dict):
                item = {"title": str(item)}
            todo_id = str(item.get("id") or uuid.uuid4().hex)
            status = str(item.get("status") or "pending")
            todos.append(
                {
                    "id": todo_id,
                    "title": str(item.get("title") or f"Task {index}"),
                    "detail": str(item.get("detail") or ""),
                    "status": status if status in allowed else "pending",
                }
            )
        return todos

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
                image_suffix = path.suffix or self._detect_image_suffix(path) or ".png"
                source_name = path.name if path.suffix else f"{path.name}{image_suffix}"
                try:
                    if target_dir.resolve() in path.resolve().parents:
                        if path.suffix:
                            materialized.append(str(path))
                        else:
                            target = self._unique_path(target_dir / source_name)
                            shutil.copy2(str(path), str(target))
                            materialized.append(str(target))
                        continue
                except Exception:
                    if target_dir in path.parents:
                        if path.suffix:
                            materialized.append(str(path))
                        else:
                            target = self._unique_path(target_dir / source_name)
                            shutil.copy2(str(path), str(target))
                            materialized.append(str(target))
                        continue
                target = self._unique_path(target_dir / source_name)
                shutil.copy2(str(path), str(target))
                materialized.append(str(target))
            except Exception:
                materialized.append(image_path)
        if materialized != list(image_paths):
            self.storage_status = f"图片已更新到：{target_dir}"
            self.storage_status_changed.emit(self.storage_status)
        return materialized

    def _detect_image_suffix(self, path: Path) -> str:
        try:
            header = path.read_bytes()[:16]
        except OSError:
            return ""
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if header.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
            return ".gif"
        if header.startswith(b"BM"):
            return ".bmp"
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return ".webp"
        if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
            return ".tiff"
        return ""

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
