"""
ChromaDB 动态知识库管理模块

功能：
- 调用 SiliconFlow Embedding API 向量化文本（模型由 EMBEDDING_MODEL 环境变量配置，默认 BAAI/bge-m3）
- 将向量化结果存入 ChromaDB（持久化至 chroma_userdata/）
- 支持增量新增、删除笔记
- 支持向量相似度检索
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx
import chromadb
from chromadb.config import Settings

from utils.sf_retry import call_with_retry, get_sf_timeout


# ---------------------------------------------------------------------------
# 常量 / 默认配置
# ---------------------------------------------------------------------------

SILICONFLOW_API_URL = os.environ.get(
    "SILICONFLOW_API_URL", "https://api.siliconflow.cn/v1/embeddings"
)
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")
# CWD-relative default; overrideable via CHROMA_PERSIST_DIRECTORY env var
DEFAULT_CHROMA_DIR = os.path.abspath(
    os.environ.get("CHROMA_PERSIST_DIRECTORY", os.path.join(os.getcwd(), "chroma_userdata"))
)
# Preserve the original default "user_notes" for backward compatibility;
# overrideable via CHROMA_COLLECTION_NAME env var.
DEFAULT_COLLECTION = os.environ.get("CHROMA_COLLECTION_NAME", "user_notes")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """解析 Markdown YAML frontmatter，返回 (metadata_dict, body_text)。"""
    metadata: dict[str, str] = {}
    body = content
    pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    match = pattern.match(content)
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                metadata[key.strip()] = value.strip()
        body = content[match.end():]
    return metadata, body


def _doc_id_from_path(file_path: str) -> str:
    """根据文件路径生成确定性文档 ID（使用 MD5 摘要）。"""
    return hashlib.md5(os.path.abspath(file_path).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def get_embedding(
    text: str,
    api_key: Optional[str] = None,
    model: str = EMBEDDING_MODEL,
    api_url: str = SILICONFLOW_API_URL,
) -> list[float]:
    """
    调用 SiliconFlow Embedding API 获取文本向量。

    Args:
        text: 要向量化的文本。
        api_key: SiliconFlow API Key；若未传入则从环境变量 SILICONFLOW_API_KEY 读取。
        model: Embedding 模型名称（默认从环境变量 EMBEDDING_MODEL 读取，回退为 BAAI/bge-m3）。
        api_url: Embedding API 完整 URL（默认从环境变量 SILICONFLOW_API_URL 读取）。

    Returns:
        浮点数列表（embedding 向量）。

    Raises:
        ValueError: API Key 未配置。
        httpx.HTTPStatusError: API 请求失败。
    """
    key = api_key or os.environ.get("SILICONFLOW_API_KEY", "")
    if not key:
        raise ValueError(
            "SiliconFlow API Key 未配置，请设置环境变量 SILICONFLOW_API_KEY "
            "或通过参数传入。"
        )
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": text, "encoding_format": "float"}
    timeout = get_sf_timeout()
    response = call_with_retry(
        lambda: httpx.post(api_url, json=payload, headers=headers, timeout=timeout)
    )
    return response.json()["data"][0]["embedding"]


# ---------------------------------------------------------------------------
# ChromaDB 管理器
# ---------------------------------------------------------------------------

class ChromaManager:
    """
    封装 ChromaDB 的增删查操作，提供面向笔记/错题的高层接口。

    Args:
        collection_name: ChromaDB 集合名称（默认 "user_notes"）。
        persist_dir: ChromaDB 持久化目录（默认 chroma_userdata/）。
        api_key: SiliconFlow API Key；不传则读取环境变量。
        embedding_fn: 自定义 embedding 函数（主要用于测试，签名同 get_embedding）。
        embedding_model: Embedding 模型名称；不传则使用模块级常量（来自环境变量）。
        api_url: Embedding API 完整 URL；不传则使用模块级常量（来自环境变量）。
    """

    def __init__(
        self,
        collection_name: str = DEFAULT_COLLECTION,
        persist_dir: str = DEFAULT_CHROMA_DIR,
        api_key: Optional[str] = None,
        embedding_fn: Optional[Any] = None,
        embedding_model: str = EMBEDDING_MODEL,
        api_url: str = SILICONFLOW_API_URL,
    ) -> None:
        self.api_key = api_key
        self._embed = embedding_fn or (
            lambda text: get_embedding(text, self.api_key, model=embedding_model, api_url=api_url)
        )
        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # embeddings are always provided explicitly via SiliconFlow API
        )

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def add_note(
        self,
        content: str,
        doc_id: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> str:
        """
        向量化并存储一条笔记/错题。

        Args:
            content: 笔记正文（纯文本或含 frontmatter 的 Markdown）。
            doc_id: 文档唯一 ID；若为 None 则自动生成。
            metadata: 附加元数据（subject/chapter/type/date 等）；
                      若 content 包含 frontmatter，会自动合并。

        Returns:
            实际使用的 doc_id。
        """
        fm, body = _parse_frontmatter(content)
        merged_meta: dict[str, str] = {}
        merged_meta.update(fm)
        if metadata:
            merged_meta.update(metadata)

        # ChromaDB 元数据值必须为 str/int/float/bool
        safe_meta = {k: str(v) for k, v in merged_meta.items()}

        if doc_id is None:
            doc_id = hashlib.md5(content.encode()).hexdigest()

        embedding = self._embed(body or content)
        self._collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[body or content],
            metadatas=[safe_meta] if safe_meta else None,
        )
        return doc_id

    def add_note_from_file(self, file_path: str) -> str:
        """
        从 Markdown 文件读取内容并存储。

        Args:
            file_path: .md 文件路径。

        Returns:
            使用的 doc_id（基于文件路径的 MD5）。
        """
        path = Path(file_path)
        content = path.read_text(encoding="utf-8")
        doc_id = _doc_id_from_path(file_path)
        return self.add_note(content=content, doc_id=doc_id)

    def delete_note(self, doc_id: str) -> None:
        """
        删除指定 ID 的笔记。

        Args:
            doc_id: 文档唯一 ID。
        """
        self._collection.delete(ids=[doc_id])

    def delete_note_by_file(self, file_path: str) -> None:
        """
        根据文件路径删除对应笔记。

        Args:
            file_path: .md 文件路径。
        """
        self.delete_note(_doc_id_from_path(file_path))

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[dict[str, str]] = None,
    ) -> list[dict[str, Any]]:
        """
        根据查询文本进行向量相似度检索。

        Args:
            query_text: 查询文本。
            n_results: 返回结果数量（默认 5）。
            where: 元数据过滤条件，如 {"subject": "数学"}。

        Returns:
            检索结果列表，每项包含 id、document、metadata、distance。
        """
        query_embedding = self._embed(query_text)
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(n_results, self._collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)
        output: list[dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for i, doc_id in enumerate(ids):
            output.append(
                {
                    "id": doc_id,
                    "document": docs[i] if docs else "",
                    "metadata": metas[i] if metas else {},
                    "distance": distances[i] if distances else None,
                }
            )
        return output

    def count(self) -> int:
        """返回集合中的文档总数。"""
        return self._collection.count()

    def doc_id_from_path(self, file_path: str) -> str:
        """公开的辅助方法：根据文件路径获取 doc_id。"""
        return _doc_id_from_path(file_path)
