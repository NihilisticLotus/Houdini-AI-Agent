"""Comprehensive tests for the memory system modules.

Tests cover: embedding, memory_store, reward_engine, growth_tracker, reflection.
"""

import os
import sqlite3
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

# Ensure the package is importable
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "houdini", "python3.11libs"))

from houdini_ai_agent.core.embedding import (
    LocalEmbedder,
    _char_ngrams,
    _build_vocab,
    bytes_to_vector,
    cosine_similarity,
    embed_text,
    embed_texts,
    get_embedder,
    vector_to_bytes,
)
from houdini_ai_agent.core.memory_store import (
    ABSTRACTION_LEVELS,
    MEMORY_CATEGORIES,
    EpisodicRecord,
    MemoryStore,
    ProceduralRecord,
    SemanticRecord,
    get_memory_store,
)
from houdini_ai_agent.core.reward_engine import (
    RewardEngine,
    RewardResult,
    get_reward_engine,
)
from houdini_ai_agent.core.growth_tracker import (
    GrowthTracker,
    TaskMetric,
    get_growth_tracker,
)
from houdini_ai_agent.core.reflection import (
    DEEP_REFLECT_INTERVAL,
    ReflectionModule,
    categorize_task,
    extract_tags,
    get_reflection_module,
)


class TestCharNgrams(unittest.TestCase):
    """Tests for _char_ngrams utility."""

    def test_basic(self):
        result = _char_ngrams("abc", 3)
        # "^abc$" -> ["^ab", "abc", "bc$"]
        self.assertEqual(result, ["^ab", "abc", "bc$"])

    def test_short_text(self):
        # "^ab$" length 4 >= 3, so produces normal ngrams
        result = _char_ngrams("ab", 3)
        self.assertEqual(result, ["^ab", "ab$"])

    def test_empty(self):
        result = _char_ngrams("", 3)
        self.assertEqual(result, ["^$"])

    def test_lowercase(self):
        result = _char_ngrams("ABC", 3)
        self.assertTrue(all(c.islower() or c in "^$" for gram in result for c in gram))


class TestBuildVocab(unittest.TestCase):
    """Tests for _build_vocab."""

    def test_builds_from_texts(self):
        vocab = _build_vocab(["hello world", "hello python"])
        self.assertIsInstance(vocab, dict)
        self.assertGreater(len(vocab), 0)

    def test_shared_grams(self):
        vocab = _build_vocab(["aaa", "aaa"])
        # Same text produces same ngrams
        self.assertGreater(len(vocab), 0)


class TestEmbedText(unittest.TestCase):
    """Tests for embed_text."""

    def test_basic_embedding(self):
        vec = embed_text("create a box node")
        self.assertIsInstance(vec, list)
        self.assertGreater(len(vec), 0)

    def test_empty_returns_empty(self):
        vec = embed_text("")
        # Empty -> "^$" -> ngrams=["^$"] which is len < 3 -> ["^$"]
        # Still produces a vector since we handle short text
        # Actually "^$" length 2 < 3, so returns ["^$"], then sorted set -> 1 dim
        self.assertIsInstance(vec, list)

    def test_normalized(self):
        vec = embed_text("hello world test embedding")
        if vec:
            norm = sum(v * v for v in vec) ** 0.5
            self.assertAlmostEqual(norm, 1.0, places=5)

    def test_with_vocab(self):
        vocab = _build_vocab(["hello world", "test embedding"])
        vec = embed_text("hello test", vocab=vocab)
        self.assertEqual(len(vec), len(vocab))


class TestEmbedTexts(unittest.TestCase):
    """Tests for embed_texts."""

    def test_multiple(self):
        texts = ["hello world", "foo bar", "test case"]
        vectors, vocab = embed_texts(texts)
        self.assertEqual(len(vectors), 3)
        self.assertIsInstance(vocab, dict)
        for v in vectors:
            self.assertEqual(len(v), len(vocab))


class TestCosineSimilarity(unittest.TestCase):
    """Tests for cosine_similarity."""

    def test_identical(self):
        vec = embed_text("hello world")
        sim = cosine_similarity(vec, vec)
        self.assertAlmostEqual(sim, 1.0, places=5)

    def test_orthogonal(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        sim = cosine_similarity(a, b)
        self.assertAlmostEqual(sim, 0.0, places=5)

    def test_different_length(self):
        sim = cosine_similarity([1.0], [1.0, 0.0])
        self.assertEqual(sim, 0.0)

    def test_empty(self):
        sim = cosine_similarity([], [])
        self.assertEqual(sim, 0.0)

    def test_similar_texts(self):
        texts = ["create a box node in houdini", "create a sphere node in houdini"]
        vectors, _ = embed_texts(texts)
        sim = cosine_similarity(vectors[0], vectors[1])
        # Similar texts should have high similarity
        self.assertGreater(sim, 0.7)

    def test_dissimilar_texts(self):
        texts = ["create a box node in houdini", "the weather is nice today"]
        vectors, _ = embed_texts(texts)
        sim = cosine_similarity(vectors[0], vectors[1])
        # Dissimilar texts should have lower similarity
        self.assertLess(sim, 0.9)


class TestVectorSerialization(unittest.TestCase):
    """Tests for vector_to_bytes / bytes_to_vector."""

    def test_roundtrip(self):
        vec = [0.1, 0.2, 0.3, 0.4, 0.5]
        data = vector_to_bytes(vec)
        self.assertIsInstance(data, bytes)
        restored = bytes_to_vector(data)
        self.assertEqual(len(restored), len(vec))
        for a, b in zip(vec, restored):
            self.assertAlmostEqual(a, b, places=5)

    def test_empty(self):
        data = vector_to_bytes([])
        self.assertEqual(data, b"")
        restored = bytes_to_vector(data)
        self.assertEqual(restored, [])


class TestLocalEmbedder(unittest.TestCase):
    """Tests for LocalEmbedder class."""

    def test_embed_without_fit(self):
        embedder = LocalEmbedder()
        vec = embedder.embed("hello world")
        self.assertIsInstance(vec, list)
        self.assertGreater(len(vec), 0)

    def test_embed_with_fit(self):
        embedder = LocalEmbedder()
        corpus = ["create a box node", "delete a sphere node", "connect nodes"]
        embedder.fit(corpus)
        vec = embedder.embed("create a box")
        self.assertEqual(len(vec), len(embedder._vocab))

    def test_similarity(self):
        embedder = LocalEmbedder()
        corpus = ["create box", "create sphere", "delete box"]
        embedder.fit(corpus)
        sim = embedder.similarity("create box", "create sphere")
        self.assertGreater(sim, 0.0)
        self.assertLessEqual(sim, 1.0)

    def test_fit_empty(self):
        embedder = LocalEmbedder()
        embedder.fit([])
        # Should not crash, vocab/IDF remain None
        self.assertIsNone(embedder._vocab)


class TestGetEmbedder(unittest.TestCase):
    """Tests for get_embedder singleton."""

    def test_returns_instance(self):
        embedder = get_embedder()
        self.assertIsInstance(embedder, LocalEmbedder)

    def test_singleton(self):
        a = get_embedder()
        b = get_embedder()
        self.assertIs(a, b)


# ---------------------------------------------------------------------------
# Memory Store Tests
# ---------------------------------------------------------------------------

class _TempMemoryStoreMixin:
    """Mixin that creates a temp-dir backed MemoryStore for testing."""

    # Shared corpus for fitting the embedder so stored/search vectors align
    _FIT_CORPUS = [
        "create a box node in houdini",
        "delete a sphere node",
        "connect nodes together",
        "set parameter value",
        "fix error in vex code",
        "analyze the scene",
        "optimize performance",
        "run python script",
        "create geometry object",
        "node creation parameter setting",
        "box sphere cylinder geometry",
        "always use box node for geometry primitives",
        "level search test memory",
        "test task abc random text",
        "create connected nodes chain",
    ]

    def _make_store(self) -> MemoryStore:
        self._tmpdir = tempfile.mkdtemp()
        db_path = Path(self._tmpdir) / "test_memory.db"
        # Reset embedder singleton and fit with a shared corpus
        import houdini_ai_agent.core.embedding as emb_mod
        emb_mod._embedder_instance = None
        embedder = get_embedder()
        embedder.fit(self._FIT_CORPUS)
        return MemoryStore(db_path=db_path)


class TestEpisodicRecord(unittest.TestCase):
    """Tests for EpisodicRecord dataclass."""

    def test_auto_id(self):
        rec = EpisodicRecord()
        self.assertTrue(rec.id)
        self.assertEqual(len(rec.id), 12)

    def test_auto_timestamp(self):
        before = time.time()
        rec = EpisodicRecord()
        after = time.time()
        self.assertGreaterEqual(rec.timestamp, before)
        self.assertLessEqual(rec.timestamp, after)

    def test_defaults(self):
        rec = EpisodicRecord()
        self.assertTrue(rec.success)
        self.assertEqual(rec.error_count, 0)
        self.assertEqual(rec.actions, [])
        self.assertEqual(rec.tags, [])


class TestSemanticRecord(unittest.TestCase):
    """Tests for SemanticRecord dataclass."""

    def test_auto_fields(self):
        rec = SemanticRecord(rule="test rule")
        self.assertTrue(rec.id)
        self.assertGreater(rec.created_at, 0)
        self.assertEqual(rec.abstraction_level, 2)

    def test_preserve_id(self):
        rec = SemanticRecord(id="custom_id", rule="test")
        self.assertEqual(rec.id, "custom_id")


class TestProceduralRecord(unittest.TestCase):
    """Tests for ProceduralRecord dataclass."""

    def test_auto_id(self):
        rec = ProceduralRecord(strategy_name="test")
        self.assertTrue(rec.id)


class TestMemoryStore(unittest.TestCase, _TempMemoryStoreMixin):
    """Tests for MemoryStore."""

    def setUp(self):
        self.store = self._make_store()

    def tearDown(self):
        import shutil
        if hasattr(self, '_tmpdir'):
            shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_init_creates_tables(self):
        conn = self.store._get_conn()
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            self.assertIn("episodic_memory", tables)
            self.assertIn("semantic_memory", tables)
            self.assertIn("procedural_memory", tables)
        finally:
            conn.close()

    def test_add_and_search_episodic(self):
        rec = EpisodicRecord(
            session_id="s1",
            task_description="create a box node in /obj",
            result_summary="Box created successfully",
            success=True,
            tags=["node_creation"],
        )
        rec_id = self.store.add_episodic(rec)
        self.assertTrue(rec_id)

        # Search should find it
        results = self.store.search_episodic("create box node", top_k=5)
        self.assertGreater(len(results), 0)
        found_rec, score = results[0]
        self.assertEqual(found_rec.task_description, "create a box node in /obj")
        self.assertGreater(score, 0.0)

    def test_search_episodic_by_session(self):
        rec = EpisodicRecord(
            session_id="target_session",
            task_description="test task abc",
            result_summary="done",
            tags=["general"],
        )
        self.store.add_episodic(rec)

        # Search with correct session
        results = self.store.search_episodic("test task", session_id="target_session")
        self.assertGreater(len(results), 0)

        # Search with wrong session
        results = self.store.search_episodic("test task", session_id="other_session")
        self.assertEqual(len(results), 0)

    def test_add_and_search_semantic(self):
        rec = SemanticRecord(
            rule="Always use box node for geometry primitives",
            category="node_creation",
            confidence=0.8,
            abstraction_level=2,
        )
        self.store.add_semantic(rec)

        results = self.store.search_semantic("box node geometry", top_k=5)
        self.assertGreater(len(results), 0)

    def test_update_semantic(self):
        rec = SemanticRecord(rule="test rule", confidence=0.5)
        rec_id = self.store.add_semantic(rec)

        self.store.update_semantic(rec_id, confidence=0.9, category="updated")
        # Verify update
        results = self.store.search_semantic("test rule", top_k=1, min_confidence=0.8)
        self.assertGreater(len(results), 0)

    def test_get_core_memories(self):
        # Add a core identity memory (level 0)
        core = SemanticRecord(
            rule="I am a Houdini AI assistant",
            confidence=0.99,
            abstraction_level=0,
        )
        self.store.add_semantic(core)

        # Add a regular memory (level 2)
        regular = SemanticRecord(
            rule="Regular experience",
            confidence=0.7,
            abstraction_level=2,
        )
        self.store.add_semantic(regular)

        cores = self.store.get_core_memories(max_count=5)
        self.assertEqual(len(cores), 1)
        self.assertEqual(cores[0].rule, "I am a Houdini AI assistant")

    def test_count_semantic(self):
        self.assertEqual(self.store.count_semantic(), 0)
        self.store.add_semantic(SemanticRecord(rule="rule 1"))
        self.store.add_semantic(SemanticRecord(rule="rule 2"))
        self.assertEqual(self.store.count_semantic(), 2)

    def test_add_and_search_procedural(self):
        rec = ProceduralRecord(
            strategy_name="node_chain_creation",
            description="Create multiple connected nodes",
            priority=0.8,
            conditions=["create_node", "connect_nodes"],
        )
        self.store.add_procedural(rec)

        results = self.store.search_procedural("create connected nodes", top_k=3)
        self.assertGreater(len(results), 0)

    def test_update_procedural_usage(self):
        rec = ProceduralRecord(
            strategy_name="test_strategy",
            description="Test",
            priority=0.5,
        )
        self.store.add_procedural(rec)

        self.store.update_procedural_usage("test_strategy", success=True)
        self.store.update_procedural_usage("test_strategy", success=False)

        # Verify usage count updated
        conn = self.store._get_conn()
        try:
            row = conn.execute(
                "SELECT usage_count, success_rate FROM procedural_memory WHERE strategy_name = ?",
                ("test_strategy",),
            ).fetchone()
            self.assertEqual(row["usage_count"], 2)
            # success_rate should be between 0 and 1
            self.assertGreater(row["success_rate"], 0.0)
            self.assertLess(row["success_rate"], 1.0)
        finally:
            conn.close()

    def test_get_stats(self):
        self.store.add_episodic(EpisodicRecord(task_description="t1"))
        self.store.add_semantic(SemanticRecord(rule="r1"))
        self.store.add_procedural(ProceduralRecord(strategy_name="p1"))

        stats = self.store.get_stats()
        self.assertEqual(stats["episodic_count"], 1)
        self.assertEqual(stats["semantic_count"], 1)
        self.assertEqual(stats["procedural_count"], 1)
        self.assertEqual(stats["total"], 3)

    def test_search_all_levels(self):
        rec = SemanticRecord(
            rule="All level search test",
            confidence=0.7,
            abstraction_level=2,
        )
        self.store.add_semantic(rec)

        results = self.store.search_all_levels("level search", top_k=5)
        self.assertGreater(len(results), 0)


class TestGetMemoryStore(unittest.TestCase):
    """Tests for get_memory_store singleton."""

    def test_returns_instance(self):
        store = get_memory_store()
        self.assertIsInstance(store, MemoryStore)


# ---------------------------------------------------------------------------
# Reward Engine Tests
# ---------------------------------------------------------------------------

class TestRewardResult(unittest.TestCase):
    """Tests for RewardResult dataclass."""

    def test_defaults(self):
        r = RewardResult()
        self.assertEqual(r.reward_score, 0.0)
        self.assertEqual(r.importance, 1.0)
        self.assertEqual(r.tags, [])
        self.assertFalse(r.reinforcement_applied)


class TestRewardEngine(unittest.TestCase, _TempMemoryStoreMixin):
    """Tests for RewardEngine."""

    def setUp(self):
        self.store = self._make_store()
        self.engine = RewardEngine()
        # Patch get_memory_store to use our temp store
        self._patcher = patch(
            "houdini_ai_agent.core.reward_engine.get_memory_store",
            return_value=self.store,
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        import shutil
        if hasattr(self, '_tmpdir'):
            shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_successful_task_high_reward(self):
        result = self.engine.calculate_reward(
            success=True, error_count=0, retry_count=0, action_count=1,
        )
        self.assertGreater(result.reward_score, 0.5)
        self.assertGreater(result.importance, 1.0)

    def test_failed_task_lower_reward(self):
        result = self.engine.calculate_reward(
            success=False, error_count=3, retry_count=2, action_count=5,
        )
        self.assertLess(result.reward_score, 0.8)
        # Failures get importance boost
        self.assertGreater(result.importance, 1.0)

    def test_importance_bounds(self):
        result = self.engine.calculate_reward(success=True, error_count=0, action_count=1)
        self.assertGreaterEqual(result.importance, 0.01)
        self.assertLessEqual(result.importance, 5.0)

    def test_reward_bounds(self):
        result = self.engine.calculate_reward(success=False, error_count=100, action_count=1)
        self.assertGreaterEqual(result.reward_score, 0.0)
        self.assertLessEqual(result.reward_score, 1.0)

    def test_process_task_completion(self):
        record = EpisodicRecord(
            task_description="test task",
            actions=[{"action": "create_node"}],
            success=True,
            tags=["node_creation"],
        )
        result = self.engine.process_task_completion(record)
        self.assertIsInstance(result, RewardResult)
        self.assertGreater(result.reward_score, 0.0)
        self.assertEqual(record.reward_score, result.reward_score)

    def test_novelty_with_new_tags(self):
        # First use of tags -> high novelty
        result = self.engine.calculate_reward(
            success=True, tags=["brand_new_tag_xyz"],
        )
        self.assertGreater(result.reward_score, 0.5)

    def test_update_importance(self):
        # Add an episodic record first
        rec = EpisodicRecord(task_description="test")
        rec_id = self.store.add_episodic(rec)

        self.engine.update_importance(rec_id, delta=0.5)
        # Verify importance was updated
        conn = self.store._get_conn()
        try:
            row = conn.execute(
                "SELECT importance FROM episodic_memory WHERE id = ?",
                (rec_id,),
            ).fetchone()
            self.assertGreater(row["importance"], 1.0)
        finally:
            conn.close()


class TestGetRewardEngine(unittest.TestCase):
    """Tests for get_reward_engine singleton."""

    def test_returns_instance(self):
        engine = get_reward_engine()
        self.assertIsInstance(engine, RewardEngine)


# ---------------------------------------------------------------------------
# Growth Tracker Tests
# ---------------------------------------------------------------------------

class TestTaskMetric(unittest.TestCase):
    """Tests for TaskMetric dataclass."""

    def test_auto_timestamp(self):
        m = TaskMetric()
        self.assertGreater(m.timestamp, 0)


class TestGrowthTracker(unittest.TestCase):
    """Tests for GrowthTracker."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.db_path = Path(self._tmpdir) / "test_growth.db"
        self.tracker = GrowthTracker(db_path=self.db_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_init_creates_tables(self):
        conn = self.tracker._get_conn()
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            self.assertIn("task_metrics", tables)
            self.assertIn("skill_confidence", tables)
        finally:
            conn.close()

    def test_record_task(self):
        metric = TaskMetric(
            success=True, tool_count=3, error_count=0,
            reward_score=0.8, tags=["node_creation"],
        )
        self.tracker.record_task(metric)

        metrics = self.tracker.get_growth_metrics(days=1)
        self.assertEqual(metrics["total_tasks"], 1)
        self.assertEqual(metrics["success_rate"], 1.0)

    def test_skill_confidence_update(self):
        metric = TaskMetric(success=True, tags=["vex"])
        self.tracker.record_task(metric)
        metric2 = TaskMetric(success=True, tags=["vex"])
        self.tracker.record_task(metric2)

        skills = self.tracker.get_skill_ranking(top_k=10)
        vex_skills = [s for s in skills if s["skill"] == "vex"]
        self.assertEqual(len(vex_skills), 1)
        self.assertGreater(vex_skills[0]["confidence"], 0.0)
        self.assertEqual(vex_skills[0]["usage_count"], 2)

    def test_growth_metrics_empty(self):
        metrics = self.tracker.get_growth_metrics(days=30)
        self.assertEqual(metrics["total_tasks"], 0)
        self.assertEqual(metrics["success_rate"], 0.0)

    def test_trend_improving(self):
        # First half: failures
        for _ in range(3):
            m = TaskMetric(success=False, tags=["test"])
            self.tracker.record_task(m)
        # Second half: successes
        for _ in range(3):
            m = TaskMetric(success=True, tags=["test"])
            self.tracker.record_task(m)

        metrics = self.tracker.get_growth_metrics(days=1)
        self.assertEqual(metrics["trend"], "improving")

    def test_personality_description_empty(self):
        desc = self.tracker.get_personality_description()
        self.assertEqual(desc, "")

    def test_personality_description_with_data(self):
        for _ in range(5):
            m = TaskMetric(success=True, reward_score=0.9, tags=["vex", "node_creation"])
            self.tracker.record_task(m)

        desc = self.tracker.get_personality_description()
        self.assertIn("highly reliable", desc)
        self.assertIn("vex", desc)

    def test_personality_cache(self):
        m = TaskMetric(success=True, tags=["test"])
        self.tracker.record_task(m)

        desc1 = self.tracker.get_personality_description()
        # Second call should use cache
        desc2 = self.tracker.get_personality_description()
        self.assertEqual(desc1, desc2)

    def test_batch_update_skill_confidence(self):
        self.tracker.update_skill_confidence_batch({"vex": 0.9, "python": 0.7})
        skills = self.tracker.get_skill_ranking(top_k=10)
        skill_names = [s["skill"] for s in skills]
        self.assertIn("vex", skill_names)
        self.assertIn("python", skill_names)


class TestGetGrowthTracker(unittest.TestCase):
    """Tests for get_growth_tracker singleton."""

    def test_returns_instance(self):
        tracker = get_growth_tracker()
        self.assertIsInstance(tracker, GrowthTracker)


# ---------------------------------------------------------------------------
# Reflection Module Tests
# ---------------------------------------------------------------------------

class TestExtractTags(unittest.TestCase):
    """Tests for extract_tags function."""

    def test_node_creation(self):
        tags = extract_tags("create_node a box", [])
        self.assertIn("node_creation", tags)

    def test_error_fixing(self):
        tags = extract_tags("fix_error in the scene", [])
        self.assertIn("error_fixing", tags)

    def test_from_actions(self):
        tags = extract_tags("some task", [{"action": "create_node"}])
        self.assertIn("node_creation", tags)

    def test_default_general(self):
        tags = extract_tags("random text with no keywords", [])
        self.assertEqual(tags, ["general"])

    def test_multiple_tags(self):
        tags = extract_tags("create_node and connect", [])
        self.assertIn("node_creation", tags)
        self.assertIn("workflow", tags)


class TestCategorizeTask(unittest.TestCase):
    """Tests for categorize_task function."""

    def test_node_creation(self):
        cat = categorize_task("create_node box")
        self.assertEqual(cat, "node_creation")

    def test_general(self):
        cat = categorize_task("random text")
        self.assertEqual(cat, "general")


class TestReflectionModule(unittest.TestCase, _TempMemoryStoreMixin):
    """Tests for ReflectionModule."""

    def setUp(self):
        self.store = self._make_store()
        self._tmpdir_growth = tempfile.mkdtemp()
        self.growth_db = Path(self._tmpdir_growth) / "test_growth.db"
        self.tracker = GrowthTracker(db_path=self.growth_db)
        self.engine = RewardEngine()
        self.reflection = ReflectionModule()

        # Patch singletons to use temp instances
        self._patches = [
            patch("houdini_ai_agent.core.reflection.get_memory_store", return_value=self.store),
            patch("houdini_ai_agent.core.reflection.get_reward_engine", return_value=self.engine),
            patch("houdini_ai_agent.core.reflection.get_growth_tracker", return_value=self.tracker),
            patch("houdini_ai_agent.core.reward_engine.get_memory_store", return_value=self.store),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        shutil.rmtree(self._tmpdir_growth, ignore_errors=True)

    def test_reflect_on_task(self):
        result = self.reflection.reflect_on_task(
            session_id="test_session",
            task_description="create_node box in /obj",
            actions=[{"action": "create_node"}],
            result_summary="Box created",
            success=True,
        )
        self.assertIn("tags", result)
        self.assertIn("reward_score", result)
        self.assertIn("importance", result)
        self.assertIn("record_id", result)
        self.assertIn("deep_reflected", result)
        self.assertGreater(result["reward_score"], 0.0)
        self.assertIn("node_creation", result["tags"])

    def test_reflect_on_task_failure(self):
        result = self.reflection.reflect_on_task(
            session_id="test_session",
            task_description="fix_error in scene",
            actions=[],
            result_summary="Failed to fix",
            success=False,
            error_count=2,
        )
        self.assertIn("error_fixing", result["tags"])

    def test_deep_reflection_trigger(self):
        # Trigger DEEP_REFLECT_INTERVAL tasks
        reflected_count = 0
        for i in range(DEEP_REFLECT_INTERVAL + 1):
            result = self.reflection.reflect_on_task(
                session_id="s1",
                task_description=f"task {i}",
                actions=[{"action": "test"}],
                result_summary="done",
                success=True,
            )
            if result["deep_reflected"]:
                reflected_count += 1
        self.assertGreater(reflected_count, 0)

    def test_generate_semantic_from_episodic(self):
        sem_id = self.reflection.generate_semantic_from_episodic(
            task_description="create_node box",
            result_summary="Success",
            success=True,
            tags=["node_creation"],
            source_id="ep_123",
        )
        self.assertTrue(sem_id)
        # Verify stored
        self.assertGreater(self.store.count_semantic(), 0)

    def test_generate_semantic_failure(self):
        sem_id = self.reflection.generate_semantic_from_episodic(
            task_description="fix_error",
            result_summary="Failed: error in VEX code",
            success=False,
            tags=["error_fixing"],
        )
        self.assertTrue(sem_id)

    def test_light_sleep(self):
        messages = [
            {"role": "user", "content": "Create a box"},
            {"role": "assistant", "content": "Done"},
            {"role": "user", "content": "Delete it"},
        ]
        result = self.reflection.light_sleep("s1", messages)
        self.assertEqual(result["episodic_count"], 2)  # 2 user messages

    def test_light_sleep_empty(self):
        result = self.reflection.light_sleep("s1", [])
        self.assertEqual(result["episodic_count"], 0)

    def test_deep_sleep(self):
        messages = [
            {"role": "assistant", "content": '{"action": "create_node", "params": {}}'},
            {"role": "assistant", "content": '{"action": "create_node", "params": {}}'},
            {"role": "assistant", "content": '{"action": "connect", "params": {}}'},
        ]
        result = self.reflection.deep_sleep("s1", messages)
        self.assertIn("tool_patterns", result)
        self.assertGreater(result["semantic_count"], 0)
        # create_node appeared 2 times, should be captured
        self.assertIn("create_node", result["tool_patterns"])


class TestGetReflectionModule(unittest.TestCase):
    """Tests for get_reflection_module singleton."""

    def test_returns_instance(self):
        module = get_reflection_module()
        self.assertIsInstance(module, ReflectionModule)


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestMemoryIntegration(unittest.TestCase, _TempMemoryStoreMixin):
    """Integration test: full pipeline from task completion to memory retrieval."""

    def setUp(self):
        self.store = self._make_store()
        self._tmpdir_growth = tempfile.mkdtemp()
        self.growth_db = Path(self._tmpdir_growth) / "test_growth.db"
        self.tracker = GrowthTracker(db_path=self.growth_db)
        self.engine = RewardEngine()
        self.reflection = ReflectionModule()

        self._patches = [
            patch("houdini_ai_agent.core.reflection.get_memory_store", return_value=self.store),
            patch("houdini_ai_agent.core.reflection.get_reward_engine", return_value=self.engine),
            patch("houdini_ai_agent.core.reflection.get_growth_tracker", return_value=self.tracker),
            patch("houdini_ai_agent.core.reward_engine.get_memory_store", return_value=self.store),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        shutil.rmtree(self._tmpdir_growth, ignore_errors=True)

    def test_full_pipeline(self):
        """Test: reflect_on_task -> store -> search -> growth tracking."""
        # 1. Reflect on a task
        result = self.reflection.reflect_on_task(
            session_id="integration_session",
            task_description="create_node box and set parameter size",
            actions=[
                {"action": "create_node"},
                {"action": "set_parm"},
            ],
            result_summary="Created box with size parameter",
            success=True,
        )

        # 2. Verify episodic stored
        self.assertTrue(result["record_id"])
        episodic_results = self.store.search_episodic("create box parameter", top_k=5)
        self.assertGreater(len(episodic_results), 0)

        # 3. Generate semantic memory
        sem_id = self.reflection.generate_semantic_from_episodic(
            task_description="create_node box and set parameter size",
            result_summary="Created box with size parameter",
            success=True,
            tags=result["tags"],
            source_id=result["record_id"],
        )
        self.assertTrue(sem_id)

        # 4. Search semantic
        sem_results = self.store.search_semantic("box size parameter", top_k=5)
        self.assertGreater(len(sem_results), 0)

        # 5. Check growth metrics
        metrics = self.tracker.get_growth_metrics(days=1)
        self.assertEqual(metrics["total_tasks"], 1)
        self.assertEqual(metrics["success_rate"], 1.0)

        # 6. Check skill ranking
        skills = self.tracker.get_skill_ranking(top_k=5)
        self.assertGreater(len(skills), 0)

    def test_multiple_tasks(self):
        """Test multiple tasks creating a learning history."""
        tasks = [
            ("create_node box", True, ["node_creation"]),
            ("fix_error in vex code", False, ["error_fixing", "vex_hscript"]),
            ("connect_nodes for pipeline", True, ["workflow"]),
            ("create_node sphere", True, ["node_creation"]),
            ("optim performance cache", True, ["performance"]),
        ]

        for desc, success, _tags in tasks:
            self.reflection.reflect_on_task(
                session_id="s1",
                task_description=desc,
                actions=[{"action": "test"}],
                result_summary="done" if success else "failed",
                success=success,
            )

        # Verify all stored
        stats = self.store.get_stats()
        self.assertEqual(stats["episodic_count"], 5)

        # Growth should show trend
        metrics = self.tracker.get_growth_metrics(days=1)
        self.assertEqual(metrics["total_tasks"], 5)


if __name__ == "__main__":
    unittest.main()
