from __future__ import annotations

import unittest

from houdini_ai_agent.core.context_manager import (
    _NEVER_COMPRESS_TOOLS,
    _QUERY_TOOLS,
    _Round,
    _build_tc_id_map_simple,
    _split_into_rounds,
    _split_with_system,
    compress_result_for_context,
    compress_tool_result,
    estimate_tokens_for_messages,
    estimate_tokens_for_text,
    is_context_exceeded_error,
    is_server_transient_error,
    smart_compress,
    strip_images,
    trim_context,
)


class TokenEstimationTests(unittest.TestCase):
    def test_empty_text(self):
        self.assertEqual(estimate_tokens_for_text(""), 0)

    def test_ascii_text(self):
        # ~3.8 chars/token for plain ASCII
        tokens = estimate_tokens_for_text("Hello world, this is a test.")
        self.assertGreater(tokens, 0)
        self.assertLess(tokens, len("Hello world, this is a test."))

    def test_cjk_text(self):
        # CJK ~1.5 chars/token → should produce more tokens per char
        cjk = "你好世界测试"
        ascii_text = "hello world test"
        cjk_tokens = estimate_tokens_for_text(cjk)
        ascii_tokens = estimate_tokens_for_text(ascii_text)
        # CJK should produce proportionally more tokens
        self.assertGreater(cjk_tokens / len(cjk), ascii_tokens / len(ascii_text))

    def test_code_punctuation(self):
        # Code punctuation: 1 char/token
        code = "{[]:,;()=<>}"
        tokens = estimate_tokens_for_text(code)
        self.assertEqual(tokens, len(code) + 1)  # +1 for the int() rounding

    def test_messages_with_text_content(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        tokens = estimate_tokens_for_messages(messages)
        self.assertGreater(tokens, 0)

    def test_messages_with_multimodal_content(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            },
        ]
        tokens = estimate_tokens_for_messages(messages)
        self.assertGreater(tokens, 765)  # Should include image token estimate

    def test_messages_with_tool_calls(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_network_structure", "arguments": '{"path": "/obj"}'},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "Network: /obj with 3 nodes"},
        ]
        tokens = estimate_tokens_for_messages(messages)
        self.assertGreater(tokens, 0)

    def test_messages_with_tools_definitions(self):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "create_node",
                    "description": "Create a new node in Houdini",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]
        tokens = estimate_tokens_for_messages([], tools=tools)
        self.assertGreater(tokens, 0)


class StripImagesTests(unittest.TestCase):
    def test_no_images(self):
        messages = [{"role": "user", "content": "Hello"}]
        stripped = strip_images(messages, keep_recent_user=0)
        self.assertEqual(stripped, 0)

    def test_strip_all_images(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Look at this"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            },
        ]
        stripped = strip_images(messages, keep_recent_user=0)
        self.assertEqual(stripped, 1)
        self.assertIsInstance(messages[0]["content"], str)

    def test_keep_recent_user_images(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Old image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,old"}},
                ],
            },
            {"role": "assistant", "content": "Got it"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "New image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,new"}},
                ],
            },
        ]
        stripped = strip_images(messages, keep_recent_user=1)
        self.assertEqual(stripped, 1)  # Only old image stripped
        # Old message should be text-only
        self.assertIsInstance(messages[0]["content"], str)
        # New message should still be multimodal
        self.assertIsInstance(messages[2]["content"], list)

    def test_empty_messages(self):
        stripped = strip_images([], keep_recent_user=0)
        self.assertEqual(stripped, 0)


class ToolResultCompressionTests(unittest.TestCase):
    def test_empty_content(self):
        self.assertEqual(compress_tool_result("test_tool", ""), "")

    def test_short_content_unchanged(self):
        content = "Short result"
        self.assertEqual(compress_tool_result("any_tool", content), content)

    def test_check_errors_never_compressed(self):
        content = "Error: something failed\n" * 100
        result = compress_tool_result("check_errors", content)
        self.assertEqual(result, content)

    def test_network_structure_strips_positions(self):
        # Content must be long enough to trigger compression (max_length=300 default)
        lines = [f"Node node{i} at ({i}.234, {i}.567) [D][R] connected to node{i+1}" for i in range(20)]
        content = "\n".join(lines)
        result = compress_tool_result("get_network_structure", content)
        # Positions should be stripped
        self.assertNotIn(".234", result)
        self.assertNotIn("[D]", result)
        self.assertIn("node0", result)

    def test_query_tools_paginated(self):
        # list_children goes through _QUERY_TOOLS → _paginate_lines
        content = "\n".join(f"Line {i} with some extra data to make it longer" for i in range(100))
        result = compress_tool_result("list_children", content)
        self.assertIn("more lines", result)

    def test_op_tools_extract_paths(self):
        content = "Created node /obj/geo1/box1 successfully. Also /obj/geo1/sphere1 done."
        result = compress_tool_result("create_node", content)
        self.assertIn("/obj/geo1/box1", result)

    def test_smart_summary_fallback(self):
        content = "A" * 500
        result = compress_tool_result("unknown_tool", content, max_length=100)
        self.assertLessEqual(len(result), 150)  # Allow some overhead

    def test_error_content_kept_longer(self):
        content = "Error: " + "something " * 100 + "failed"
        result = compress_tool_result("unknown_tool", content, max_length=100)
        # Error messages should get more space
        self.assertGreater(len(result), 100)


class RoundSplitTests(unittest.TestCase):
    def test_empty_messages(self):
        rounds = _split_into_rounds([])
        self.assertEqual(rounds, [])

    def test_single_round(self):
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        rounds = _split_into_rounds(messages)
        self.assertEqual(len(rounds), 1)
        self.assertEqual(len(rounds[0].messages), 2)

    def test_multiple_rounds(self):
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "Fine"},
        ]
        rounds = _split_into_rounds(messages)
        self.assertEqual(len(rounds), 2)

    def test_system_prefix_separated(self):
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        prefix, rounds = _split_with_system(messages)
        self.assertEqual(len(prefix), 1)
        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0].messages[0]["role"], "user")


class TrimContextTests(unittest.TestCase):
    def test_no_trimming_needed(self):
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        result = trim_context(messages, context_limit=100000)
        # Should still return messages (possibly with image stripping)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_trim_level_3_keeps_few_rounds(self):
        flat = []
        for i in range(10):
            flat.append({"role": "user", "content": f"Round {i}"})
            flat.append({"role": "assistant", "content": f"Response {i}"})
            flat.append({"role": "tool", "tool_call_id": f"tc_{i}", "content": f"Tool result {i}" * 50})

        result = trim_context(flat, context_limit=100, trim_level=3)
        # Should be much shorter
        self.assertLess(len(result), len(flat))

    def test_empty_messages(self):
        result = trim_context([], context_limit=1000)
        self.assertEqual(result, [])


class SmartCompressTests(unittest.TestCase):
    def test_no_compression_needed(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        result = smart_compress(messages, context_limit=100000)
        # Should not add compression notice since no compression needed
        has_notice = any(
            isinstance(m, dict) and "上下文管理" in str(m.get("content", ""))
            for m in result
        )
        self.assertFalse(has_notice)

    def test_compression_triggered(self):
        # Create messages large enough to trigger compression
        big_content = "x" * 5000
        messages = [
            {"role": "system", "content": "You are helpful."},
        ]
        for i in range(20):
            messages.append({"role": "user", "content": f"Question {i}"})
            messages.append({"role": "assistant", "content": f"Answer {i}"})
            messages.append({"role": "tool", "tool_call_id": f"tc_{i}", "content": big_content})

        result = smart_compress(messages, context_limit=5000)
        # Should be shorter than input
        self.assertLess(len(result), len(messages))
        # Should have compression notice
        has_notice = any(
            isinstance(m, dict) and "上下文管理" in str(m.get("content", ""))
            for m in result
        )
        self.assertTrue(has_notice)


class ErrorDetectionTests(unittest.TestCase):
    def test_context_exceeded(self):
        self.assertTrue(is_context_exceeded_error("Error: context_length_exceeded"))
        self.assertTrue(is_context_exceeded_error("Maximum context length reached"))
        self.assertTrue(is_context_exceeded_error("HTTP 413: request too large"))

    def test_not_context_error(self):
        self.assertFalse(is_context_exceeded_error("Network error"))
        self.assertFalse(is_context_exceeded_error("Invalid API key"))

    def test_server_transient(self):
        self.assertTrue(is_server_transient_error("502 Bad Gateway"))
        self.assertTrue(is_server_transient_error("Server error: 500"))
        self.assertTrue(is_server_transient_error("Rate limit exceeded"))

    def test_not_transient(self):
        self.assertFalse(is_server_transient_error("Invalid JSON"))
        self.assertFalse(is_server_transient_error("API key not found"))


class ResultCompressionTests(unittest.TestCase):
    def test_short_result_unchanged(self):
        result = {"success": True, "message": "Done"}
        text = compress_result_for_context(result)
        self.assertIn("Done", text)

    def test_long_result_truncated(self):
        result = {"success": True, "message": "x" * 5000}
        text = compress_result_for_context(result, max_length=1000)
        self.assertIn("truncated", text)
        self.assertLess(len(text), 3000)


class TcIdMapTests(unittest.TestCase):
    def test_build_mapping(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {"name": "create_node", "arguments": "{}"}},
                    {"id": "call_2", "type": "function", "function": {"name": "delete_node", "arguments": "{}"}},
                ],
            },
        ]
        mapping = _build_tc_id_map_simple(messages)
        self.assertEqual(mapping["call_1"], "create_node")
        self.assertEqual(mapping["call_2"], "delete_node")


if __name__ == "__main__":
    unittest.main()
