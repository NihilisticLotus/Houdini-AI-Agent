"""Tests for the i18n (internationalization) module."""

import unittest
from unittest.mock import patch, MagicMock

from houdini_ai_agent.core.i18n import (
    _EN,
    _ZH,
    all_keys,
    get_language,
    has_key,
    is_english,
    load_language,
    save_language,
    set_language,
    tr,
)


class TranslationCoreTests(unittest.TestCase):
    """Core tr() function behavior."""

    def test_zh_default(self):
        self.assertEqual(get_language(), "zh")

    def test_tr_zh_key(self):
        result = tr("button.send")
        self.assertEqual(result, "发送")

    def test_tr_en_key(self):
        set_language("en")
        try:
            result = tr("button.send")
            self.assertEqual(result, "Send")
        finally:
            set_language("zh")

    def test_tr_unknown_key_falls_back_to_key(self):
        result = tr("nonexistent.key.xyz")
        self.assertEqual(result, "nonexistent.key.xyz")

    def test_tr_format_args(self):
        result = tr("conv.msg_count", 5)
        self.assertEqual(result, "5 条消息")

    def test_tr_format_args_en(self):
        set_language("en")
        try:
            result = tr("conv.msg_count", 5)
            self.assertEqual(result, "5 messages")
        finally:
            set_language("zh")

    def test_tr_format_args_fallback_on_error(self):
        # If template has no placeholders but args are given, return template as-is
        result = tr("button.send", "unused")
        self.assertEqual(result, "发送")


class LanguageSwitchTests(unittest.TestCase):
    """set_language / get_language behavior."""

    def test_set_to_en(self):
        original = get_language()
        set_language("en")
        self.assertEqual(get_language(), "en")
        set_language(original)

    def test_set_to_zh(self):
        set_language("zh")
        self.assertEqual(get_language(), "zh")

    def test_set_invalid_defaults_to_zh(self):
        set_language("fr")
        self.assertEqual(get_language(), "zh")

    def test_set_empty_defaults_to_zh(self):
        set_language("")
        self.assertEqual(get_language(), "zh")

    def test_set_none_defaults_to_zh(self):
        set_language(None)
        self.assertEqual(get_language(), "zh")

    def test_set_same_language_no_op(self):
        set_language("zh")
        set_language("zh")
        self.assertEqual(get_language(), "zh")

    def test_is_english(self):
        set_language("zh")
        self.assertFalse(is_english())
        set_language("en")
        self.assertTrue(is_english())
        set_language("zh")


class LanguageSignalTests(unittest.TestCase):
    """Qt signal emission on language change."""

    def test_signal_emitted_on_change(self):
        from houdini_ai_agent.core.i18n import _LangSignals
        if _LangSignals.changed is None:
            self.skipTest("Qt not available for signal test")
        emitted = []
        _LangSignals.changed.connect(lambda lang: emitted.append(lang))
        try:
            set_language("en")
            self.assertTrue(len(emitted) > 0)
            self.assertEqual(emitted[-1], "en")
        finally:
            _LangSignals.changed.disconnect(lambda lang: emitted.append(lang))
            set_language("zh")

    def test_no_signal_on_same_language(self):
        from houdini_ai_agent.core.i18n import _LangSignals
        if _LangSignals.changed is None:
            self.skipTest("Qt not available for signal test")
        emitted = []
        _LangSignals.changed.connect(lambda lang: emitted.append(lang))
        try:
            set_language("zh")  # already zh
            self.assertEqual(len(emitted), 0)
        finally:
            _LangSignals.changed.disconnect(lambda lang: emitted.append(lang))


class DictConsistencyTests(unittest.TestCase):
    """Verify translation dictionaries are consistent."""

    def test_zh_and_en_have_common_keys(self):
        zh_keys = set(_ZH.keys())
        en_keys = set(_EN.keys())
        # All EN keys should exist in ZH
        missing_in_zh = en_keys - zh_keys
        self.assertEqual(len(missing_in_zh), 0, f"Keys in EN but not in ZH: {missing_in_zh}")

    def test_zh_keys_subset_of_en(self):
        zh_keys = set(_ZH.keys())
        en_keys = set(_EN.keys())
        missing_in_en = zh_keys - en_keys
        self.assertEqual(len(missing_in_en), 0, f"Keys in ZH but not in EN: {missing_in_en}")

    def test_no_empty_zh_values(self):
        empty = [k for k, v in _ZH.items() if not v.strip()]
        self.assertEqual(len(empty), 0, f"Empty ZH values for keys: {empty}")

    def test_no_empty_en_values(self):
        empty = [k for k, v in _EN.items() if not v.strip()]
        self.assertEqual(len(empty), 0, f"Empty EN values for keys: {empty}")

    def test_format_placeholders_match(self):
        """All keys with {0}-style placeholders should have the same placeholder set in both languages."""
        import re
        placeholder_re = re.compile(r"\{(\d+)\}")
        for key in set(_ZH.keys()) & set(_EN.keys()):
            zh_placeholders = set(placeholder_re.findall(_ZH[key]))
            en_placeholders = set(placeholder_re.findall(_EN[key]))
            self.assertEqual(
                zh_placeholders,
                en_placeholders,
                f"Placeholder mismatch for key '{key}': ZH has {zh_placeholders}, EN has {en_placeholders}",
            )


class KeyManagementTests(unittest.TestCase):
    """all_keys, has_key functions."""

    def test_all_keys_returns_sorted(self):
        keys = all_keys()
        self.assertEqual(keys, sorted(keys))

    def test_all_keys_non_empty(self):
        self.assertGreater(len(all_keys()), 0)

    def test_has_key_true(self):
        self.assertTrue(has_key("button.send"))

    def test_has_key_false(self):
        self.assertFalse(has_key("totally.fake.key"))

    def test_all_keys_are_has_key(self):
        for key in all_keys():
            self.assertTrue(has_key(key))


class PersistenceTests(unittest.TestCase):
    """load_language / save_language integration with config."""

    @patch("houdini_ai_agent.core.config.load_ui_language", return_value="en")
    def test_load_language_en(self, mock_load):
        load_language()
        self.assertEqual(get_language(), "en")
        set_language("zh")  # reset

    @patch("houdini_ai_agent.core.config.load_ui_language", return_value="zh")
    def test_load_language_zh(self, mock_load):
        set_language("en")
        load_language()
        self.assertEqual(get_language(), "zh")

    @patch("houdini_ai_agent.core.config.save_ui_language")
    def test_save_language_explicit(self, mock_save):
        save_language("en")
        mock_save.assert_called_once_with("en")

    @patch("houdini_ai_agent.core.config.save_ui_language")
    def test_save_language_uses_current(self, mock_save):
        set_language("en")
        save_language()
        mock_save.assert_called_once_with("en")
        set_language("zh")


if __name__ == "__main__":
    unittest.main()
