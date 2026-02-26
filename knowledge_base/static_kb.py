"""
Static Knowledge Base
=====================
Backed by a FAISS vector index built from pre-processed exam content.

The static KB is **read-heavy** – documents are ingested once (offline) and
then queried at inference time.  At runtime the index is loaded from disk;
if the persisted index is absent, an empty in-memory index is created so the
system still starts without errors.
"""

from __future__ import annotations

import os
import uuid
from typing import List

from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document as LCDocument
from langchain_core.embeddings import Embeddings

from config import settings
from models.schemas import Document, SearchResult


class StaticKnowledgeBase:
    """FAISS-backed vector store for static exam knowledge."""

    def __init__(
        self,
        kb_path: str | None = None,
        embedding_model: str | None = None,
        embeddings: Embeddings | None = None,
    ) -> None:
        self._kb_path = kb_path or settings.static_kb_path
        if embeddings is not None:
            self._embeddings = embeddings
        else:
            model_name = embedding_model or settings.embedding_model
            self._embeddings = HuggingFaceEmbeddings(model_name=model_name)
        self._store: FAISS | None = None
        self._load_or_init()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_or_init(self) -> None:
        index_file = os.path.join(self._kb_path, "index.faiss")
        if os.path.exists(index_file):
            self._store = FAISS.load_local(
                self._kb_path,
                self._embeddings,
                allow_dangerous_deserialization=True,
            )
        else:
            # Create an empty placeholder store so callers always get a store.
            placeholder = LCDocument(
                page_content="考研 AI 辅助系统 – 静态知识库占位符",
                metadata={"source": "system"},
            )
            self._store = FAISS.from_documents([placeholder], self._embeddings)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_documents(self, documents: List[Document]) -> None:
        """Add documents to the static index (for offline ingestion)."""
        lc_docs = [
            LCDocument(
                page_content=doc.content,
                metadata={**doc.metadata, "id": doc.id or str(uuid.uuid4())},
            )
            for doc in documents
        ]
        if self._store is None:
            self._store = FAISS.from_documents(lc_docs, self._embeddings)
        else:
            self._store.add_documents(lc_docs)

    def save(self) -> None:
        """Persist the FAISS index to disk."""
        if self._store is not None:
            os.makedirs(self._kb_path, exist_ok=True)
            self._store.save_local(self._kb_path)

    def search(self, query: str, top_k: int | None = None) -> List[SearchResult]:
        """Return the *top_k* most relevant documents for *query*."""
        k = top_k or settings.top_k
        if self._store is None:
            return []
        raw = self._store.similarity_search_with_score(query, k=k)
        results: List[SearchResult] = []
        for lc_doc, score in raw:
            doc = Document(
                id=lc_doc.metadata.get("id"),
                content=lc_doc.page_content,
                metadata=lc_doc.metadata,
            )
            results.append(SearchResult(document=doc, score=float(score)))
        return results

