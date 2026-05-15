"""Tests for houdini_ai_agent.core.doc_rag module."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from houdini_ai_agent.core.doc_rag import (
    HoudiniDocIndex, KnowledgeChunk, NodeDoc, VexDoc, HomDoc,
    get_doc_index, get_doc_rag, _index_instance,
)


class DataClassTests(unittest.TestCase):
    """Test data class instantiation."""

    def test_node_doc(self):
        nd = NodeDoc("box", "sop", "Box", "Creates a box.", [["size", "Box size"]])
        self.assertEqual(nd.node_type, "box")
        self.assertEqual(nd.context, "sop")
        self.assertEqual(nd.parameters, [["size", "Box size"]])

    def test_vex_doc(self):
        vd = VexDoc("addpoint", "int addpoint(int geo, vector pos)", "Adds a point.", "geo")
        self.assertEqual(vd.name, "addpoint")
        self.assertEqual(vd.category, "geo")

    def test_hom_doc(self):
        hd = HomDoc("hou.Node", "class", "", "Represents a Houdini node.")
        self.assertEqual(hd.doc_type, "class")

    def test_knowledge_chunk(self):
        kc = KnowledgeChunk("VEX Snippet", "Content here", "vex_basics", ["vex", "snippet"])
        self.assertEqual(kc.keywords, ["vex", "snippet"])


class WikiParserTests(unittest.TestCase):
    """Test _parse_wiki static method."""

    def test_basic_node_doc(self):
        text = """= Box =\n#type: node\n#context: sop\n#internal: box\n\n\"\"\"Creates a box geometry.\"\"\"\n\nBody text.\n\n@parameters\nSize:\n    The size of the box."""
        doc = HoudiniDocIndex._parse_wiki(text)
        self.assertEqual(doc["title"], "Box")
        self.assertEqual(doc["context"], "sop")
        self.assertEqual(doc["internal"], "box")
        self.assertEqual(doc["description"], "Creates a box geometry.")
        self.assertIn("parameters", doc["sections"])

    def test_multiline_description(self):
        text = '= Node =\n#context: sop\n\n\"\"\"Line one\nLine two\nLine three\"\"\"'
        doc = HoudiniDocIndex._parse_wiki(text)
        self.assertIn("Line one", doc["description"])
        self.assertIn("Line three", doc["description"])

    def test_empty_input(self):
        doc = HoudiniDocIndex._parse_wiki("")
        self.assertEqual(doc["title"], "")
        self.assertEqual(doc["sections"], {})


class TxtSectionParserTests(unittest.TestCase):
    """Test _parse_txt_sections static method."""

    def test_basic_sections(self):
        text = "## VEX Basics\nVEX is a high-performance language.\n\n## Attributes\nAttributes store data on points."
        chunks = HoudiniDocIndex._parse_txt_sections(text, "test")
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].title, "VEX Basics")
        self.assertIn("high-performance", chunks[0].content)
        self.assertEqual(chunks[1].title, "Attributes")

    def test_short_sections_skipped(self):
        text = "## Short\nhi\n\n## Long Enough\nThis has enough content to pass the 30 char minimum threshold."
        chunks = HoudiniDocIndex._parse_txt_sections(text, "test")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].title, "Long Enough")

    def test_decorator_lines_skipped(self):
        text = "## ========\nIgnored\n\n## Real Title\nReal content with enough length to be included."
        chunks = HoudiniDocIndex._parse_txt_sections(text, "test")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].title, "Real Title")

    def test_keywords_extracted(self):
        text = "## Point Cloud Functions\nUse pcfind() and pcnumfound() for searching."
        chunks = HoudiniDocIndex._parse_txt_sections(text, "test")
        self.assertTrue(len(chunks) == 1)
        kw_set = set(chunks[0].keywords)
        self.assertIn("pcfind", kw_set)
        self.assertIn("pcnumfound", kw_set)


class ParameterParserTests(unittest.TestCase):
    """Test _parse_parameters static method."""

    def test_basic_params(self):
        text = "Size:\n    The size\nUniform Scale:\n    Uniform scaling"
        params = HoudiniDocIndex._parse_parameters(text)
        self.assertEqual(len(params), 2)
        self.assertEqual(params[0][0], "Size")
        self.assertEqual(params[1][0], "Uniform Scale")

    def test_empty_input(self):
        self.assertEqual(HoudiniDocIndex._parse_parameters(""), [])
        self.assertEqual(HoudiniDocIndex._parse_parameters(None), [])

    def test_skip_includes(self):
        text = ":include some/file\nReal Param:\n    A real parameter"
        params = HoudiniDocIndex._parse_parameters(text)
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0][0], "Real Param")


class EmptyIndexTests(unittest.TestCase):
    """Test HoudiniDocIndex with no help directory."""

    def setUp(self):
        self.index = HoudiniDocIndex.__new__(HoudiniDocIndex)
        self.index._help_dir = None
        self.index.node_index = {}
        self.index.vex_index = {}
        self.index.hom_index = {}
        self.index.knowledge_chunks = []
        self.index._node_aliases = {}
        self.index._vex_categories = {}
        self.index._all_node_types = set()

    def test_lookup_empty(self):
        self.assertIsNone(self.index.lookup_node("box"))
        self.assertIsNone(self.index.lookup_vex("addpoint"))
        self.assertIsNone(self.index.lookup_hom("hou.Node"))

    def test_search_empty(self):
        self.assertEqual(self.index.search("box"), [])

    def test_auto_retrieve_empty(self):
        self.assertEqual(self.index.auto_retrieve("How do I use box?"), "")

    def test_stats_empty(self):
        stats = self.index.stats()
        self.assertEqual(stats["nodes"], 0)
        self.assertIsNone(stats["help_dir"])


class PopulatedIndexTests(unittest.TestCase):
    """Test HoudiniDocIndex with manually populated data."""

    def setUp(self):
        self.index = HoudiniDocIndex.__new__(HoudiniDocIndex)
        self.index._help_dir = None
        self.index.node_index = {}
        self.index.vex_index = {}
        self.index.hom_index = {}
        self.index.knowledge_chunks = []
        self.index._node_aliases = {}
        self.index._vex_categories = {}
        self.index._all_node_types = None
        # Populate
        nd = NodeDoc("box", "sop", "Box", "Creates a box.", [["size", "Box size"]])
        self.index.node_index["box"] = nd
        self.index.node_index["sop/box"] = nd
        vd = VexDoc("addpoint", "int addpoint(int geo, vector pos)", "Add a point.", "geo")
        self.index.vex_index["addpoint"] = vd
        hd = HomDoc("hou.Node", "class", "", "Represents a node.")
        self.index.hom_index["hou.Node"] = hd
        self.index._build_aliases()

    def test_lookup_node(self):
        doc = self.index.lookup_node("box")
        self.assertIsNotNone(doc)
        self.assertEqual(doc.node_type, "box")

    def test_lookup_node_case_insensitive(self):
        doc = self.index.lookup_node("Box")
        self.assertIsNotNone(doc)

    def test_lookup_vex(self):
        doc = self.index.lookup_vex("addpoint")
        self.assertIsNotNone(doc)
        self.assertEqual(doc.category, "geo")

    def test_lookup_hom(self):
        doc = self.index.lookup_hom("hou.Node")
        self.assertIsNotNone(doc)
        self.assertEqual(doc.doc_type, "class")

    def test_search_exact(self):
        results = self.index.search("box")
        self.assertTrue(any(r["name"] == "box" for r in results))

    def test_search_vex(self):
        results = self.index.search("addpoint")
        self.assertTrue(any(r["type"] == "vex" for r in results))

    def test_search_hom(self):
        results = self.index.search("hou.Node")
        self.assertTrue(any(r["type"] == "hom" for r in results))

    def test_auto_retrieve_hou_ref(self):
        result = self.index.auto_retrieve("How to use hou.Node?")
        self.assertIn("hou.Node", result)

    def test_auto_retrieve_vex(self):
        result = self.index.auto_retrieve("How does addpoint work?")
        self.assertIn("addpoint", result)

    def test_auto_retrieve_no_stopwords(self):
        result = self.index.auto_retrieve("the node is very good")
        self.assertEqual(result, "")

    def test_stats(self):
        stats = self.index.stats()
        self.assertGreater(stats["nodes"], 0)
        self.assertGreater(stats["vex_functions"], 0)
        self.assertGreater(stats["hom_entries"], 0)


class KnowledgeSearchTests(unittest.TestCase):
    """Test knowledge base search."""

    def setUp(self):
        self.index = HoudiniDocIndex.__new__(HoudiniDocIndex)
        self.index._help_dir = None
        self.index.node_index = {}
        self.index.vex_index = {}
        self.index.hom_index = {}
        self.index.knowledge_chunks = [
            KnowledgeChunk("VEX Wrangle Tips", "Use @P for position, @N for normal in wrangles.",
                           "vex_tips", ["vex", "wrangle", "@P", "@N", "position", "normal"]),
            KnowledgeChunk("Heightfield Workflow", "Create terrain with heightfield node.",
                           "terrain", ["heightfield", "terrain", "node"]),
        ]
        self.index._node_aliases = {}
        self.index._vex_categories = {}
        self.index._all_node_types = set()

    def test_search_knowledge_english(self):
        results = self.index.search_knowledge("wrangle @P")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["type"], "knowledge")

    def test_search_knowledge_no_match(self):
        results = self.index.search_knowledge("xyznonexistent")
        self.assertEqual(len(results), 0)

    def test_search_includes_knowledge(self):
        results = self.index.search("heightfield workflow stuff", top_k=5)
        kb_results = [r for r in results if r["type"] == "knowledge"]
        self.assertTrue(len(kb_results) > 0)


class FormattingTests(unittest.TestCase):
    """Test formatting helpers."""

    def test_fmt_node(self):
        nd = NodeDoc("box", "sop", "Box", "A box.", [["size", "Size"]])
        s = HoudiniDocIndex._fmt_node(nd)
        self.assertIn("[doc] Box", s)
        self.assertIn("sop/box", s)
        self.assertIn("size", s)

    def test_fmt_vex(self):
        vd = VexDoc("addpoint", "int addpoint(int, vector)", "Add point.", "geo")
        s = HoudiniDocIndex._fmt_vex(vd)
        self.assertIn("[VEX] addpoint", s)
        self.assertIn("addpoint", s)

    def test_fmt_hom(self):
        hd = HomDoc("hou.Node", "class", "name()", "A node.")
        s = HoudiniDocIndex._fmt_hom(hd)
        self.assertIn("[HOM] hou.Node", s)
        self.assertIn("name()", s)


class CacheTests(unittest.TestCase):
    """Test cache serialization round-trip."""

    def test_save_load_roundtrip(self):
        index = HoudiniDocIndex.__new__(HoudiniDocIndex)
        index._help_dir = Path("/test/help")
        index.node_index = {"box": NodeDoc("box", "sop", "Box", "A box.", [])}
        index.vex_index = {"addpoint": VexDoc("addpoint", "sig", "desc", "geo")}
        index.hom_index = {"hou.Node": HomDoc("hou.Node", "class", "", "A node.")}
        index._node_aliases = {}
        index._vex_categories = {"geo": ["addpoint"]}
        index._all_node_types = None

        with tempfile.TemporaryDirectory() as td:
            cache_path = Path(td) / "test_cache.json"
            index._save_to_cache(cache_path)
            data = json.loads(cache_path.read_text("utf-8"))
            self.assertEqual(data["version"], 2)
            self.assertIn("box", data["nodes"])
            self.assertIn("addpoint", data["vex"])

            # Load round-trip
            index2 = HoudiniDocIndex.__new__(HoudiniDocIndex)
            index2._help_dir = None
            index2.node_index = {}
            index2.vex_index = {}
            index2.hom_index = {}
            index2.knowledge_chunks = []
            index2._node_aliases = {}
            index2._vex_categories = {}
            index2._all_node_types = None
            index2._load_from_cache(data)
            self.assertIn("box", index2.node_index)
            self.assertIn("addpoint", index2.vex_index)


class SingletonTests(unittest.TestCase):
    """Test singleton behavior."""

    def test_get_doc_rag_is_alias(self):
        self.assertIs(get_doc_rag, get_doc_index)

    def test_stats_method(self):
        index = HoudiniDocIndex.__new__(HoudiniDocIndex)
        index._help_dir = None
        index.node_index = {}
        index.vex_index = {}
        index.hom_index = {}
        index.knowledge_chunks = []
        stats = index.stats()
        self.assertIn("nodes", stats)
        self.assertIn("help_dir", stats)


class ResolveHelpDirTests(unittest.TestCase):
    """Test help directory resolution."""

    def test_nonexistent_explicit_path(self):
        result = HoudiniDocIndex._resolve_help_dir("/nonexistent/path")
        # May find help dir via fallback discovery on systems with Houdini installed
        self.assertIsInstance(result, (Path, type(None)))

    def test_empty_string(self):
        result = HoudiniDocIndex._resolve_help_dir("")
        # May return None or a found path depending on environment
        # Just verify it doesn't crash
        self.assertIsInstance(result, (Path, type(None)))


if __name__ == "__main__":
    unittest.main()
