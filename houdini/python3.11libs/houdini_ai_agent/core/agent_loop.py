"""Multi-turn Agent Loop engine for the Houdini AI Agent.

Implements a bounded loop that:
1. Sends user message + conversation history + tools schema to the AI
2. Receives model response
3. If the model requests tool_calls -> executes tools -> feeds results back -> goto 2
4. If the model finishes (stop) -> returns final text to the user

Supports both Function Calling (native) and fenced-JSON (fallback) modes.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from houdini_ai_agent.core.openai_compat import (
    AIResponse,
    ProviderCallError,
    StreamChunk,
    ToolCall,
    build_assistant_tool_call_message,
    build_tool_result_message,
    collect_streaming_response,
    send_chat_streaming,
    send_messages,
)
from houdini_ai_agent.core.context_manager import (
    DEFAULT_CONTEXT_LIMIT,
    compress_result_for_context,
    is_context_exceeded_error,
    smart_compress,
    trim_context,
)
from houdini_ai_agent.core.tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# Loop result
# ---------------------------------------------------------------------------

@dataclass
class AgentLoopResult:
    """Result of a complete agent loop run."""
    final_text: str = ""
    reasoning: str = ""
    tool_traces: List[ToolTrace] = field(default_factory=list)
    iterations: int = 0
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    cancelled: bool = False

    @property
    def total_tool_calls(self) -> int:
        return sum(len(t.call_results) for t in self.tool_traces)


@dataclass
class ToolTrace:
    """Trace of tools called in a single loop iteration."""
    iteration: int
    tool_calls: List[ToolCall] = field(default_factory=list)
    call_results: List[Dict[str, object]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool executor protocol
# ---------------------------------------------------------------------------

ToolExecutor = Callable[[str, Dict[str, object]], Dict[str, object]]
"""Given (tool_name, tool_args) -> result dict with at least 'success' and 'message'."""


# ---------------------------------------------------------------------------
# Agent Loop
# ---------------------------------------------------------------------------

class AgentLoop:
    """Bounded multi-turn agent loop with Function Calling support."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        max_iterations: int = 10,
        max_tool_calls_per_iteration: int = 5,
        max_total_tool_calls: int = 25,
        enable_fc: bool = True,
        enable_streaming: bool = False,
        cancel_event: Optional[threading.Event] = None,
        on_iteration_start: Optional[Callable[[int, int], None]] = None,
        on_tool_call_start: Optional[Callable[[str, Dict[str, object]], None]] = None,
        on_tool_call_end: Optional[Callable[[str, Dict[str, object]], None]] = None,
        on_content_delta: Optional[Callable[[str], None]] = None,
        on_thinking_delta: Optional[Callable[[str], None]] = None,
    ):
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.max_iterations = max_iterations
        self.max_tool_calls_per_iteration = max_tool_calls_per_iteration
        self.max_total_tool_calls = max_total_tool_calls
        self.enable_fc = enable_fc
        self.enable_streaming = enable_streaming
        self.cancel_event = cancel_event or threading.Event()
        self.on_iteration_start = on_iteration_start
        self.on_tool_call_start = on_tool_call_start
        self.on_tool_call_end = on_tool_call_end
        self.on_content_delta = on_content_delta
        self.on_thinking_delta = on_thinking_delta

        # Duplicate call detection
        self._recent_readonly_calls: List[str] = []
        self._readonly_dedup_window = 3

    def run(
        self,
        provider,
        messages: List[Dict[str, object]],
        work_mode: str,
        max_tokens: int = 1400,
        thinking_level: str = "\u4e2d",
        timeout_seconds: int = 120,
    ) -> AgentLoopResult:
        """Run the agent loop to completion.

        Args:
            provider: ProviderConfig for the AI model
            messages: Full conversation history
            work_mode: Current work mode for tool filtering
            max_tokens: Max response tokens per iteration
            thinking_level: Reasoning effort level
            timeout_seconds: Timeout per API call

        Returns:
            AgentLoopResult with final text and trace data
        """
        result = AgentLoopResult()
        total_tool_calls = 0
        working_messages = list(messages)

        # Build tools schema for FC mode
        tools_schema = None
        if self.enable_fc:
            tools_schema = self.tool_registry.schemas_for_provider(work_mode)
            if not tools_schema:
                tools_schema = None

        for iteration in range(1, self.max_iterations + 1):
            if self.cancel_event.is_set():
                result.cancelled = True
                result.finish_reason = "cancelled"
                return result

            result.iterations = iteration
            if self.on_iteration_start:
                self.on_iteration_start(iteration, self.max_iterations)

            # Proactive context compression before API call
            working_messages = smart_compress(
                working_messages,
                context_limit=DEFAULT_CONTEXT_LIMIT,
                supports_vision=True,
                tools=tools_schema,
            )

            # Call the AI model
            try:
                ai_response = self._call_model(
                    provider=provider,
                    messages=working_messages,
                    tools_schema=tools_schema,
                    max_tokens=max_tokens,
                    thinking_level=thinking_level,
                    timeout_seconds=timeout_seconds,
                )
            except ProviderCallError as exc:
                error_text = str(exc)
                # Reactive context trimming on context_length_exceeded
                if is_context_exceeded_error(error_text):
                    working_messages = trim_context(
                        working_messages,
                        context_limit=DEFAULT_CONTEXT_LIMIT,
                        trim_level=2,
                    )
                    # Retry once after trimming
                    try:
                        ai_response = self._call_model(
                            provider=provider,
                            messages=working_messages,
                            tools_schema=tools_schema,
                            max_tokens=max_tokens,
                            thinking_level=thinking_level,
                            timeout_seconds=timeout_seconds,
                        )
                    except ProviderCallError as retry_exc:
                        result.final_text = str(retry_exc)
                        result.finish_reason = "error"
                        return result
                else:
                    result.final_text = error_text
                    result.finish_reason = "error"
                    return result

            # Collect usage
            if ai_response.usage:
                for key, val in ai_response.usage.items():
                    result.usage[key] = result.usage.get(key, 0) + val

            # If no tool calls, we're done
            if not ai_response.has_tool_calls:
                result.final_text = ai_response.to_text()
                result.reasoning = ai_response.reasoning
                result.finish_reason = ai_response.finish_reason
                return result

            # Process tool calls
            tool_calls = ai_response.tool_calls[:self.max_tool_calls_per_iteration]
            remaining_budget = self.max_total_tool_calls - total_tool_calls
            if len(tool_calls) > remaining_budget:
                tool_calls = tool_calls[:max(0, remaining_budget)]

            if not tool_calls:
                # No budget left, return what we have
                result.final_text = ai_response.to_text() or "Tool call budget exhausted."
                result.finish_reason = "max_tool_calls"
                return result

            trace = ToolTrace(iteration=iteration, tool_calls=list(tool_calls))
            total_tool_calls += len(tool_calls)

            # Add assistant message with tool calls to history
            working_messages.append(
                build_assistant_tool_call_message(ai_response.text, tool_calls)
            )

            # Execute each tool call
            for tc in tool_calls:
                if self.cancel_event.is_set():
                    result.cancelled = True
                    result.finish_reason = "cancelled"
                    return result

                # Check mode policy
                if not self.tool_registry.is_tool_allowed(work_mode, tc.function_name):
                    error_result = {
                        "success": False,
                        "message": f"Tool '{tc.function_name}' is not allowed in {work_mode} mode.",
                    }
                    trace.call_results.append(error_result)
                    working_messages.append(
                        build_tool_result_message(tc.id, json.dumps(error_result), is_error=True)
                    )
                    if self.on_tool_call_end:
                        self.on_tool_call_end(tc.function_name, error_result)
                    continue

                # Duplicate readonly call detection
                dedup_key = self._dedup_key(tc)
                tool_meta = self.tool_registry.get(tc.function_name)
                if tool_meta and tool_meta.is_readonly and dedup_key in self._recent_readonly_calls:
                    skip_result = {
                        "success": True,
                        "message": f"Skipping duplicate readonly call: {tc.function_name}",
                    }
                    trace.call_results.append(skip_result)
                    working_messages.append(
                        build_tool_result_message(tc.id, json.dumps(skip_result))
                    )
                    continue

                # Parse arguments
                try:
                    args = json.loads(tc.function_arguments) if tc.function_arguments else {}
                except json.JSONDecodeError:
                    args = {}

                # Schema validation
                is_valid, validation_msg = self.tool_registry.validate_args(tc.function_name, args)
                if not is_valid:
                    error_result = {"success": False, "message": validation_msg}
                    trace.call_results.append(error_result)
                    working_messages.append(
                        build_tool_result_message(tc.id, json.dumps(error_result), is_error=True)
                    )
                    if self.on_tool_call_end:
                        self.on_tool_call_end(tc.function_name, error_result)
                    continue

                # Execute
                if self.on_tool_call_start:
                    self.on_tool_call_start(tc.function_name, args)

                try:
                    exec_result = self.tool_executor(tc.function_name, args)
                except Exception as exc:
                    exec_result = {"success": False, "message": f"Tool execution error: {exc}"}

                # Track readonly calls for dedup
                if tool_meta and tool_meta.is_readonly:
                    self._recent_readonly_calls.append(dedup_key)
                    if len(self._recent_readonly_calls) > self._readonly_dedup_window:
                        self._recent_readonly_calls = self._recent_readonly_calls[-self._readonly_dedup_window:]

                # Compress result for context
                compressed = compress_result_for_context(exec_result)
                trace.call_results.append(exec_result)
                working_messages.append(
                    build_tool_result_message(tc.id, compressed)
                )

                if self.on_tool_call_end:
                    self.on_tool_call_end(tc.function_name, exec_result)

            result.tool_traces.append(trace)

        # If we exhausted all iterations
        result.final_text = "Agent loop reached maximum iterations."
        result.finish_reason = "max_iterations"
        return result

    def _call_model(
        self,
        provider,
        messages: List[Dict[str, object]],
        tools_schema: Optional[List[Dict[str, object]]],
        max_tokens: int,
        thinking_level: str,
        timeout_seconds: int,
    ) -> AIResponse:
        """Call the AI model, either streaming or non-streaming."""
        if self.enable_streaming:
            stream = send_chat_streaming(
                provider=provider,
                messages=messages,
                tools=tools_schema,
                thinking_level=thinking_level,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            )
            return collect_streaming_response(stream)
        else:
            return send_messages(
                provider=provider,
                messages=messages,
                tools=tools_schema,
                thinking_level=thinking_level,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            )

    @staticmethod
    def _dedup_key(tc: ToolCall) -> str:
        return f"{tc.function_name}:{tc.function_arguments}"
