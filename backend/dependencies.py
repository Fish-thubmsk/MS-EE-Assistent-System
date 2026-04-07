"""
JWT 认证依赖模块

提供 FastAPI Depends 可用的 get_current_user() 函数，从 Authorization header
中解析并验证 JWT Token，返回当前已认证用户的 user_id (int)。

用法：
    from backend.dependencies import get_current_user
    from fastapi import Depends

    @router.post("/protected")
    def protected_route(user_id: int = Depends(get_current_user)):
        ...
"""

from __future__ import annotations

import logging
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ] = None,
    settings: Settings = Depends(get_settings),
) -> int:
    """
    从 Bearer Token 中提取并验证 JWT，返回 user_id (int)。

    - 若 token 缺失、签名无效或已过期，返回 401。
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证 Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.debug("JWT decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证 Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 载荷缺少 sub 字段",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 载荷 sub 字段格式错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
