"""FastAPI 后端入口"""

from fastapi import FastAPI
from backend.routers.notes import router as notes_router

app = FastAPI(
    title="考研智能辅导系统 API",
    description="基于 FastAPI + ChromaDB + SiliconFlow 的考研笔记动态知识库",
    version="0.1.0",
)

app.include_router(notes_router)


@app.get("/", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
