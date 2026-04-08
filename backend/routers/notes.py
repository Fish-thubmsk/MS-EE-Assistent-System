"""
笔记 API 路由模块

提供以下 RESTful 接口：
    POST   /notes/           新增/更新笔记（文本形式）
    POST   /notes/file       从 .md 文件路径新增/更新笔记
    DELETE /notes/{doc_id}   删除指定笔记
    GET    /notes/query      向量相似度检索
    GET    /notes/count      返回集合中笔记总数
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.config import Settings, get_settings
from knowledge_base.chroma_manager import ChromaManager

router = APIRouter(prefix="/notes", tags=["notes"])


@lru_cache(maxsize=1)
def _get_manager() -> ChromaManager:
    """单例工厂，首次调用时初始化 ChromaManager（使用应用配置）。"""
    settings = get_settings()
    return ChromaManager(
        collection_name=settings.chroma_collection_name,
        persist_dir=settings.chroma_persist_directory,
        api_key=settings.siliconflow_api_key,
        embedding_model=settings.embedding_model,
        api_url=settings.siliconflow_api_url,
    )


def get_manager() -> ChromaManager:
    """FastAPI Depends 兼容的依赖函数。"""
    return _get_manager()


ManagerDep = Annotated[ChromaManager, Depends(get_manager)]


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class NoteRequest(BaseModel):
    content: str
    doc_id: Optional[str] = None
    metadata: Optional[dict[str, str]] = None


class NoteFileRequest(BaseModel):
    file_path: str


class NoteResponse(BaseModel):
    doc_id: str
    message: str


class QueryResult(BaseModel):
    id: str
    document: str
    metadata: dict
    distance: Optional[float]


class QueryResponse(BaseModel):
    results: list[QueryResult]


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@router.post("/", response_model=NoteResponse, summary="新增或更新笔记")
def add_note(req: NoteRequest, manager: ManagerDep) -> NoteResponse:
    """
    接受笔记文本（可包含 YAML frontmatter），向量化后存入 ChromaDB。

    - **content**: Markdown 格式笔记内容（必填）
    - **doc_id**: 文档 ID，若不填则自动生成
    - **metadata**: 附加元数据，如 `{"subject": "数学", "type": "note"}`
    """
    try:
        doc_id = manager.add_note(
            content=req.content,
            doc_id=req.doc_id,
            metadata=req.metadata,
        )
        return NoteResponse(doc_id=doc_id, message="笔记已成功存入 ChromaDB")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"向量化或存储失败：{exc}") from exc


@router.post("/file", response_model=NoteResponse, summary="从文件新增或更新笔记")
def add_note_from_file(req: NoteFileRequest, manager: ManagerDep) -> NoteResponse:
    """
    读取指定路径的 .md 文件，向量化后存入 ChromaDB。

    - **file_path**: Markdown 文件的绝对或相对路径
    """
    try:
        doc_id = manager.add_note_from_file(req.file_path)
        return NoteResponse(doc_id=doc_id, message=f"文件 {req.file_path} 已存入 ChromaDB")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"文件不存在：{req.file_path}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"处理失败：{exc}") from exc


@router.delete("/{doc_id}", summary="删除笔记")
def delete_note(doc_id: str, manager: ManagerDep) -> dict[str, str]:
    """
    删除指定 doc_id 的笔记。

    - **doc_id**: 文档唯一 ID
    """
    try:
        manager.delete_note(doc_id)
        return {"message": f"笔记 {doc_id} 已删除"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除失败：{exc}") from exc


@router.get("/query", response_model=QueryResponse, summary="向量相似度检索")
def query_notes(
    manager: ManagerDep,
    q: str = Query(..., description="查询文本"),
    n: int = Query(5, ge=1, le=50, description="返回结果数量"),
    subject: Optional[str] = Query(None, description="按学科过滤，如 数学"),
    note_type: Optional[str] = Query(None, alias="type", description="按类型过滤：note 或 wrong"),
) -> QueryResponse:
    """
    根据查询文本进行向量相似度检索，可选按元数据过滤。

    - **q**: 查询文本（必填）
    - **n**: 返回数量（1-50，默认 5）
    - **subject**: 可选，按学科过滤
    - **type**: 可选，按笔记类型过滤（note/wrong）
    """
    where: dict[str, str] = {}
    if subject:
        where["subject"] = subject
    if note_type:
        where["type"] = note_type

    try:
        raw = manager.query(
            query_text=q,
            n_results=n,
            where=where or None,
        )
        return QueryResponse(
            results=[
                QueryResult(
                    id=item["id"],
                    document=item["document"],
                    metadata=item["metadata"],
                    distance=item["distance"],
                )
                for item in raw
            ]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"检索失败：{exc}") from exc


@router.get("/count", summary="获取笔记总数")
def count_notes(manager: ManagerDep) -> dict[str, int]:
    """返回 ChromaDB 集合中的笔记总数。"""
    return {"count": manager.count()}
