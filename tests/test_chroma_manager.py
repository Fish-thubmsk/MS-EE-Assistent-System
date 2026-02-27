"""
ChromaDB 管理模块单元测试

使用 mock embedding 函数（返回固定向量），不依赖 SiliconFlow API Key，
ChromaDB 使用临时目录，测试完成后自动清理。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from knowledge_base.chroma_manager import (
    ChromaManager,
    _doc_id_from_path,
    _parse_frontmatter,
)

# ---------------------------------------------------------------------------
# 固定 mock embedding（所有测试共用，维度 8）
# ---------------------------------------------------------------------------

_DIM = 8


def _mock_embed(text: str) -> list[float]:
    """返回基于文本哈希的确定性伪向量（长度 _DIM）。"""
    import hashlib

    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return [(h >> (i * 4) & 0xF) / 15.0 for i in range(_DIM)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_chroma(tmp_path: Path) -> str:
    """返回临时 ChromaDB 持久化目录路径。"""
    return str(tmp_path / "chroma_test")


@pytest.fixture()
def manager(tmp_chroma: str) -> ChromaManager:
    """返回使用 mock embedding 的 ChromaManager 实例。"""
    return ChromaManager(
        collection_name="test_notes",
        persist_dir=tmp_chroma,
        embedding_fn=_mock_embed,
    )


@pytest.fixture()
def sample_md(tmp_path: Path) -> Path:
    """创建一个示例 Markdown 文件并返回其路径。"""
    md = tmp_path / "sample.md"
    md.write_text(
        "---\nsubject: 数学\nchapter: 极限\ntype: note\ndate: 2024-01-01\n---\n\n# 极限的定义\n\n极限是微积分的基础。",
        encoding="utf-8",
    )
    return md


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_with_frontmatter(self) -> None:
        content = "---\nsubject: 数学\ntype: note\n---\n\n正文内容"
        meta, body = _parse_frontmatter(content)
        assert meta == {"subject": "数学", "type": "note"}
        assert "正文内容" in body

    def test_without_frontmatter(self) -> None:
        content = "# 标题\n\n正文"
        meta, body = _parse_frontmatter(content)
        assert meta == {}
        assert body == content

    def test_empty_frontmatter(self) -> None:
        content = "---\n---\n\n正文"
        meta, body = _parse_frontmatter(content)
        assert meta == {}
        assert "正文" in body


# ---------------------------------------------------------------------------
# _doc_id_from_path
# ---------------------------------------------------------------------------


class TestDocIdFromPath:
    def test_deterministic(self) -> None:
        path = "/some/fixed/path/note.md"
        assert _doc_id_from_path(path) == _doc_id_from_path(path)

    def test_different_paths_different_ids(self) -> None:
        assert _doc_id_from_path("/a/b.md") != _doc_id_from_path("/a/c.md")


# ---------------------------------------------------------------------------
# ChromaManager: add / count / delete
# ---------------------------------------------------------------------------


class TestAddAndDelete:
    def test_add_note_returns_doc_id(self, manager: ChromaManager) -> None:
        doc_id = manager.add_note("这是一条测试笔记。")
        assert isinstance(doc_id, str)
        assert len(doc_id) == 32  # MD5 hex

    def test_add_note_increments_count(self, manager: ChromaManager) -> None:
        assert manager.count() == 0
        manager.add_note("笔记一")
        assert manager.count() == 1
        manager.add_note("笔记二")
        assert manager.count() == 2

    def test_upsert_same_doc_id_does_not_duplicate(self, manager: ChromaManager) -> None:
        manager.add_note("原始内容", doc_id="fixed-id")
        manager.add_note("更新内容", doc_id="fixed-id")
        assert manager.count() == 1

    def test_add_note_with_metadata(self, manager: ChromaManager) -> None:
        doc_id = manager.add_note(
            "数学极限笔记",
            metadata={"subject": "数学", "type": "note"},
        )
        assert doc_id is not None

    def test_add_note_parses_frontmatter(self, manager: ChromaManager) -> None:
        content = "---\nsubject: 政治\ntype: wrong\n---\n\n错题内容"
        doc_id = manager.add_note(content)
        # 能无异常存入即可
        assert doc_id is not None

    def test_delete_note(self, manager: ChromaManager) -> None:
        doc_id = manager.add_note("待删除笔记", doc_id="del-id")
        assert manager.count() == 1
        manager.delete_note(doc_id)
        assert manager.count() == 0

    def test_add_note_from_file(self, manager: ChromaManager, sample_md: Path) -> None:
        doc_id = manager.add_note_from_file(str(sample_md))
        assert doc_id == _doc_id_from_path(str(sample_md))
        assert manager.count() == 1

    def test_delete_note_by_file(self, manager: ChromaManager, sample_md: Path) -> None:
        manager.add_note_from_file(str(sample_md))
        assert manager.count() == 1
        manager.delete_note_by_file(str(sample_md))
        assert manager.count() == 0


# ---------------------------------------------------------------------------
# ChromaManager: query
# ---------------------------------------------------------------------------


class TestQuery:
    def test_query_returns_results(self, manager: ChromaManager) -> None:
        manager.add_note("极限是微积分的核心概念", doc_id="n1")
        manager.add_note("导数描述函数变化率", doc_id="n2")
        results = manager.query("什么是极限", n_results=2)
        assert len(results) == 2
        for item in results:
            assert "id" in item
            assert "document" in item
            assert "metadata" in item
            assert "distance" in item

    def test_query_n_results_capped_by_collection_size(self, manager: ChromaManager) -> None:
        manager.add_note("唯一的笔记", doc_id="only")
        results = manager.query("查询", n_results=10)
        assert len(results) == 1

    def test_query_with_metadata_filter(self, manager: ChromaManager) -> None:
        manager.add_note("数学笔记内容", doc_id="math1", metadata={"subject": "数学"})
        manager.add_note("政治笔记内容", doc_id="pol1", metadata={"subject": "政治"})
        results = manager.query("笔记", n_results=5, where={"subject": "数学"})
        assert all(r["metadata"].get("subject") == "数学" for r in results)
