from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".json",
    ".md",
    ".py",
    ".pypanel",
    ".qss",
    ".shelf",
}

MOJIBAKE_MARKERS = tuple(
    chr(codepoint)
    for codepoint in (
        0xFFFD,
        0x9225,
        0x923D,
        0x93C2,
        0x93CC,
        0x947A,
        0x7481,
        0x95AB,
        0x9342,
        0x6B3F,
        0x5BCB,
        0x4FD3,
    )
)


class TextEncodingTests(unittest.TestCase):
    def test_repository_text_files_are_utf8_without_common_mojibake(self):
        failures: list[str] = []
        for path in self._iter_text_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                failures.append(f"{path.relative_to(ROOT)} is not UTF-8: {exc}")
                continue

            for marker in MOJIBAKE_MARKERS:
                if marker in text:
                    failures.append(
                        f"{path.relative_to(ROOT)} contains mojibake marker {marker!r}"
                    )
                    break

        self.assertEqual([], failures)

    def _iter_text_files(self):
        roots = [
            ROOT / "houdini",
            ROOT / "docs",
            ROOT / "tests",
            ROOT,
        ]
        seen: set[Path] = set()
        for root in roots:
            for path in root.rglob("*") if root.is_dir() else []:
                if path in seen or not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                seen.add(path)
                yield path
            if root.is_file() and root not in seen and root.suffix.lower() in TEXT_SUFFIXES:
                seen.add(root)
                yield root
