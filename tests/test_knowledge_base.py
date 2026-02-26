"""
Tests for the static and dynamic knowledge bases.
"""

import pytest
from langchain_community.embeddings import FakeEmbeddings

from models.schemas import Document, NoteCreate, QARecordCreate, AgentMode
from knowledge_base.static_kb import StaticKnowledgeBase
from knowledge_base.dynamic_kb import DynamicKnowledgeBase


# ---------------------------------------------------------------------------
# Static KB
# ---------------------------------------------------------------------------

@pytest.fixture
def static_kb(tmp_path):
    """Return a StaticKnowledgeBase backed by deterministic fake embeddings."""
    return StaticKnowledgeBase(
        kb_path=str(tmp_path / "static"),
        embeddings=FakeEmbeddings(size=384),
    )


def test_static_kb_search_returns_results(static_kb):
    docs = [
        Document(content="微积分是数学的重要分支，包括导数和积分。", metadata={"subject": "数学"}),
        Document(content="英语六级词汇是考研英语的基础。", metadata={"subject": "英语"}),
        Document(content="马克思主义哲学是政治理论课的核心内容。", metadata={"subject": "政治"}),
    ]
    static_kb.add_documents(docs)
    results = static_kb.search("微积分导数", top_k=2)
    assert len(results) >= 1
    # With fake embeddings every result is equally ranked, just verify structure
    assert all(hasattr(r, "document") and hasattr(r, "score") for r in results)


def test_static_kb_search_empty_returns_list(static_kb):
    # Should not raise even before any custom documents are added
    results = static_kb.search("随机查询词")
    assert isinstance(results, list)


def test_static_kb_save_and_reload(tmp_path):
    path = str(tmp_path / "kb")
    embeddings = FakeEmbeddings(size=384)
    kb = StaticKnowledgeBase(kb_path=path, embeddings=embeddings)
    kb.add_documents([Document(content="线性代数矩阵运算")])
    kb.save()

    kb2 = StaticKnowledgeBase(kb_path=path, embeddings=FakeEmbeddings(size=384))
    results = kb2.search("矩阵", top_k=1)
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# Dynamic KB
# ---------------------------------------------------------------------------

@pytest.fixture
def dynamic_kb(tmp_path):
    db_url = f"sqlite:///{tmp_path}/dynamic.db"
    return DynamicKnowledgeBase(db_url=db_url)


def test_dynamic_kb_add_and_get_note(dynamic_kb):
    note = NoteCreate(subject="数学", content="积分换元法总结", tags=["积分", "换元"])
    resp = dynamic_kb.add_note(note)
    assert resp.id is not None
    assert resp.subject == "数学"
    assert "积分" in resp.tags

    notes = dynamic_kb.get_notes(subject="数学")
    assert any(n.id == resp.id for n in notes)


def test_dynamic_kb_delete_note(dynamic_kb):
    note = NoteCreate(subject="英语", content="长难句分析方法")
    resp = dynamic_kb.add_note(note)
    assert dynamic_kb.delete_note(resp.id) is True
    notes = dynamic_kb.get_notes(subject="英语")
    assert all(n.id != resp.id for n in notes)


def test_dynamic_kb_delete_nonexistent_note(dynamic_kb):
    assert dynamic_kb.delete_note(99999) is False


def test_dynamic_kb_add_and_get_qa_record(dynamic_kb):
    record = QARecordCreate(
        question="什么是极限？",
        answer="极限是微积分的基础概念...",
        mode=AgentMode.QA,
        subject="数学",
    )
    resp = dynamic_kb.add_qa_record(record)
    assert resp.id is not None
    assert resp.mode == AgentMode.QA

    records = dynamic_kb.get_qa_records(subject="数学")
    assert any(r.id == resp.id for r in records)


def test_dynamic_kb_qa_records_limit(dynamic_kb):
    for i in range(5):
        dynamic_kb.add_qa_record(
            QARecordCreate(
                question=f"问题{i}",
                answer=f"答案{i}",
                mode=AgentMode.STUDY,
            )
        )
    records = dynamic_kb.get_qa_records(limit=3)
    assert len(records) <= 3

