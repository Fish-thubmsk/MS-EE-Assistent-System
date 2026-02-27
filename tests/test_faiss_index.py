"""
Tests for knowledge_base/build_faiss_index.py and knowledge_base/search_demo.py.

These tests mock the SiliconFlow API so no real network calls are made.
They use a temporary SQLite database and a temporary index directory.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import faiss
import numpy as np
import requests

# ---------------------------------------------------------------------------
# Make the knowledge_base package importable from the repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _REPO_ROOT)

import knowledge_base.build_faiss_index as builder
import knowledge_base.search_demo as searcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(path: str, num_questions: int = 5) -> None:
    """Create a minimal questions table populated with dummy rows."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE questions (
            id         INTEGER PRIMARY KEY,
            subject    TEXT,
            year       INTEGER,
            question_type TEXT,
            content    TEXT,
            correct_answer TEXT,
            vector_id  TEXT,
            is_active  INTEGER DEFAULT 1
        )
        """
    )
    for i in range(1, num_questions + 1):
        conn.execute(
            "INSERT INTO questions(id, subject, year, content, is_active) "
            "VALUES (?, '政治', 2024, ?, 1)",
            (i, f"Test question content number {i}"),
        )
    conn.commit()
    conn.close()


def _fake_embeddings(texts: list, **_kwargs) -> list:
    """Return deterministic unit vectors for each text (no API call)."""
    rng = np.random.RandomState(42)
    vecs = []
    for _ in texts:
        v = rng.randn(builder.EMBEDDING_DIM).astype(np.float32)
        v /= np.linalg.norm(v)
        vecs.append(v.tolist())
    return vecs


# ---------------------------------------------------------------------------
# Tests for build_faiss_index
# ---------------------------------------------------------------------------


class TestLoadOrCreateIndex(unittest.TestCase):
    def test_creates_new_index_when_files_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = builder.INDEX_DIR
            builder.INDEX_DIR = tmpdir
            builder.INDEX_FILE = os.path.join(tmpdir, "questions.index")
            builder.ID_MAP_FILE = os.path.join(tmpdir, "id_map.json")
            try:
                index, id_map = builder.load_or_create_index(dim=4)
                self.assertIsInstance(index, faiss.IndexFlatIP)
                self.assertEqual(index.ntotal, 0)
                self.assertEqual(id_map, [])
            finally:
                builder.INDEX_DIR = orig_dir
                builder.INDEX_FILE = os.path.join(orig_dir, "questions.index")
                builder.ID_MAP_FILE = os.path.join(orig_dir, "id_map.json")

    def test_loads_existing_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            index_file = os.path.join(tmpdir, "questions.index")
            id_map_file = os.path.join(tmpdir, "id_map.json")

            # Pre-populate a tiny index
            idx = faiss.IndexFlatIP(4)
            vec = np.ones((1, 4), dtype=np.float32)
            faiss.normalize_L2(vec)
            idx.add(vec)
            faiss.write_index(idx, index_file)
            with open(id_map_file, "w") as fh:
                json.dump([99], fh)

            orig_dir = builder.INDEX_DIR
            builder.INDEX_DIR = tmpdir
            builder.INDEX_FILE = index_file
            builder.ID_MAP_FILE = id_map_file
            try:
                loaded_index, loaded_map = builder.load_or_create_index(dim=4)
                self.assertEqual(loaded_index.ntotal, 1)
                self.assertEqual(loaded_map, [99])
            finally:
                builder.INDEX_DIR = orig_dir
                builder.INDEX_FILE = os.path.join(orig_dir, "questions.index")
                builder.ID_MAP_FILE = os.path.join(orig_dir, "id_map.json")


class TestBuildIndex(unittest.TestCase):
    """Integration-style test: builds an index against a temp DB."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        _make_db(self._db_path, num_questions=6)

        # Redirect builder to use temp paths
        self._orig_db = builder.DB_PATH
        self._orig_index_dir = builder.INDEX_DIR
        self._orig_index_file = builder.INDEX_FILE
        self._orig_id_map = builder.ID_MAP_FILE

        builder.DB_PATH = self._db_path
        builder.INDEX_DIR = self._tmpdir
        builder.INDEX_FILE = os.path.join(self._tmpdir, "questions.index")
        builder.ID_MAP_FILE = os.path.join(self._tmpdir, "id_map.json")

    def tearDown(self):
        builder.DB_PATH = self._orig_db
        builder.INDEX_DIR = self._orig_index_dir
        builder.INDEX_FILE = self._orig_index_file
        builder.ID_MAP_FILE = self._orig_id_map

    @patch("knowledge_base.build_faiss_index.get_embeddings", side_effect=_fake_embeddings)
    def test_full_build(self, _mock_embed):
        builder.build_index(batch_size=3)

        # Index file must exist
        self.assertTrue(os.path.exists(builder.INDEX_FILE))
        self.assertTrue(os.path.exists(builder.ID_MAP_FILE))

        # All 6 questions should be indexed
        index = faiss.read_index(builder.INDEX_FILE)
        self.assertEqual(index.ntotal, 6)

        with open(builder.ID_MAP_FILE) as fh:
            id_map = json.load(fh)
        self.assertEqual(len(id_map), 6)
        self.assertEqual(sorted(id_map), [1, 2, 3, 4, 5, 6])

        # vector_id should be back-filled in DB
        conn = sqlite3.connect(self._db_path)
        rows = conn.execute("SELECT id, vector_id FROM questions ORDER BY id").fetchall()
        conn.close()
        for qid, vid in rows:
            self.assertIsNotNone(vid, f"vector_id not set for question id={qid}")
            self.assertEqual(int(vid), id_map.index(qid))

    @patch("knowledge_base.build_faiss_index.get_embeddings", side_effect=_fake_embeddings)
    def test_incremental_build_skips_existing(self, mock_embed):
        """Second call to build_index must skip already-indexed questions."""
        # First build: all 6 questions
        builder.build_index(batch_size=6)
        calls_first = mock_embed.call_count

        # Second build: nothing new → no API calls
        builder.build_index(batch_size=6)
        calls_second = mock_embed.call_count

        self.assertEqual(calls_second, calls_first, "No new API calls expected on re-run")

        index = faiss.read_index(builder.INDEX_FILE)
        self.assertEqual(index.ntotal, 6)

    @patch("knowledge_base.build_faiss_index.get_embeddings", side_effect=_fake_embeddings)
    def test_subject_filter(self, _mock_embed):
        """Filtering by subject must only index matching questions."""
        builder.build_index(subject="数学", batch_size=3)
        # All test questions have subject='政治', so the index file is never written
        # and nothing gets indexed.
        if os.path.exists(builder.INDEX_FILE):
            index = faiss.read_index(builder.INDEX_FILE)
            self.assertEqual(index.ntotal, 0)
        else:
            # No questions matched the filter → no index created; that's correct
            pass


class TestGetEmbeddings(unittest.TestCase):
    def test_raises_without_api_key(self):
        with self.assertRaises(ValueError):
            builder.get_embeddings(["hello"], api_key="", api_url="http://localhost")

    @patch("knowledge_base.build_faiss_index.requests.post")
    def test_returns_embeddings_in_order(self, mock_post):
        """Verify that embeddings are sorted by 'index' field."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = builder.get_embeddings(["a", "b"], api_key="test-key")
        self.assertEqual(result[0], [1.0, 0.0])  # index 0 first
        self.assertEqual(result[1], [0.0, 1.0])  # index 1 second

    @patch("knowledge_base.build_faiss_index.requests.post")
    @patch("knowledge_base.build_faiss_index.time.sleep")
    def test_retries_on_failure(self, mock_sleep, mock_post):
        mock_post.side_effect = requests.RequestException("timeout")
        with self.assertRaises(RuntimeError):
            builder.get_embeddings(["x"], api_key="test-key")

        self.assertEqual(mock_post.call_count, builder.MAX_RETRIES)


# ---------------------------------------------------------------------------
# Tests for search_demo
# ---------------------------------------------------------------------------


class TestSearch(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        _make_db(self._db_path, num_questions=4)

        # Build a tiny FAISS index manually
        dim = builder.EMBEDDING_DIM
        index = faiss.IndexFlatIP(dim)
        rng = np.random.RandomState(0)
        vecs = rng.randn(4, dim).astype(np.float32)
        faiss.normalize_L2(vecs)
        index.add(vecs)
        self._vecs = vecs

        index_file = os.path.join(self._tmpdir, "questions.index")
        id_map_file = os.path.join(self._tmpdir, "id_map.json")
        faiss.write_index(index, index_file)
        with open(id_map_file, "w") as fh:
            json.dump([1, 2, 3, 4], fh)

        # Back-fill vector_id in test DB
        conn = sqlite3.connect(self._db_path)
        for vid, qid in enumerate([1, 2, 3, 4]):
            conn.execute(
                "UPDATE questions SET vector_id = ? WHERE id = ?", (str(vid), qid)
            )
        conn.commit()
        conn.close()

        # Redirect searcher to temp paths
        self._orig_db = searcher.DB_PATH
        self._orig_index_file = searcher.INDEX_FILE
        self._orig_id_map = searcher.ID_MAP_FILE
        searcher.DB_PATH = self._db_path
        searcher.INDEX_FILE = index_file
        searcher.ID_MAP_FILE = id_map_file

    def tearDown(self):
        searcher.DB_PATH = self._orig_db
        searcher.INDEX_FILE = self._orig_index_file
        searcher.ID_MAP_FILE = self._orig_id_map

    def _patch_query_embedding(self, vec: np.ndarray):
        """Return a patch for _get_query_embedding that uses *vec*."""
        v = vec.reshape(1, -1).astype(np.float32).copy()
        faiss.normalize_L2(v)
        return patch(
            "knowledge_base.search_demo._get_query_embedding",
            return_value=v,
        )

    def test_returns_expected_result(self):
        # Use the first stored vector as query → top result should be question id=1
        with self._patch_query_embedding(self._vecs[0]):
            results = searcher.search("dummy", top_k=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], 1)
        self.assertAlmostEqual(results[0]["score"], 1.0, places=4)

    def test_returns_top_k_results(self):
        with self._patch_query_embedding(self._vecs[0]):
            results = searcher.search("dummy", top_k=3)

        self.assertEqual(len(results), 3)

    def test_result_fields(self):
        with self._patch_query_embedding(self._vecs[0]):
            results = searcher.search("dummy", top_k=1)

        r = results[0]
        for field in ("id", "subject", "year", "content", "score", "vector_id"):
            self.assertIn(field, r)

    def test_raises_when_index_missing(self):
        searcher.INDEX_FILE = "/nonexistent/path/questions.index"
        with self.assertRaises(FileNotFoundError):
            searcher.search("hello")


if __name__ == "__main__":
    unittest.main()
