"""
Chat API 路由模块

提供以下接口：
    POST /chat/route   意图识别与路由，返回识别到的模式及参数
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agents.router_agent import Mode, RouterParams, run_router

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class MultimodalAttachment(BaseModel):
    type: str = Field(..., description="附件类型，如 image / file")
    url: Optional[str] = Field(None, description="附件 URL")
    content: Optional[str] = Field(None, description="附件文本内容（base64 等）")


class ChatMessage(BaseModel):
    role: str = Field(..., description="角色：user 或 assistant")
    content: str = Field(..., description="消息内容")


class RouteRequest(BaseModel):
    user_input: str = Field(..., description="当前用户输入文本")
    messages: list[ChatMessage] = Field(
        default_factory=list, description="历史对话消息列表"
    )
    session_history: list[dict[str, Any]] = Field(
        default_factory=list, description="历史会话模式记录（用于跨轮次模式切换）"
    )
    multimodal_attachments: list[MultimodalAttachment] = Field(
        default_factory=list, description="多模态附件（图片等），预留接口"
    )


class RouteResponse(BaseModel):
    mode: str = Field(..., description="识别到的主模式：quiz / qa / diagnosis / unknown")
    sub_mode: Optional[str] = Field(None, description="子模式")
    params: dict[str, Any] = Field(default_factory=dict, description="提取的参数")
    intent_confidence: float = Field(..., description="意图置信度 0.0–1.0")
    messages: list[ChatMessage] = Field(..., description="更新后的消息列表")
    session_history: list[dict[str, Any]] = Field(
        ..., description="更新后的历史会话记录"
    )
    mode_description: str = Field(..., description="模式说明文字")


# ---------------------------------------------------------------------------
# 模式说明映射
# ---------------------------------------------------------------------------

_MODE_DESCRIPTIONS: dict[str, str] = {
    Mode.QUIZ.value: "刷题模式：追问、批改、讲解",
    Mode.QA.value: "问答模式：知识点查询、概念解释、融合个人笔记",
    Mode.DIAGNOSIS.value: "诊断模式：学习轨迹分析、弱项推荐",
    Mode.UNKNOWN.value: "未识别到明确意图，请补充更多信息",
}


# ---------------------------------------------------------------------------
# 接口实现
# ---------------------------------------------------------------------------


@router.post("/route", response_model=RouteResponse, summary="意图识别与路由")
def route_intent(req: RouteRequest) -> RouteResponse:
    """
    接收用户输入，识别意图并路由到对应模式。

    - **quiz**      : 刷题模式（追问 / 批改 / 讲解）
    - **qa**        : 问答模式（知识点 / 概念 / 融合笔记）
    - **diagnosis** : 诊断模式（学习轨迹 / 弱项分析）
    """
    result = run_router(
        req.user_input,
        messages=[m.model_dump() for m in req.messages],
        session_history=req.session_history,
        multimodal_attachments=[a.model_dump() for a in req.multimodal_attachments],
    )

    return RouteResponse(
        mode=result["mode"],
        sub_mode=result.get("sub_mode"),
        params=dict(result.get("params", {})),
        intent_confidence=result["intent_confidence"],
        messages=[ChatMessage(**m) for m in result["messages"]],
        session_history=result["session_history"],
        mode_description=_MODE_DESCRIPTIONS.get(result["mode"], ""),
    )
