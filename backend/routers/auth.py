"""
认证（Auth）API 路由模块

提供以下接口：
    POST /api/auth/register   用户注册
    POST /api/auth/login      用户登录，返回 JWT Token
    GET  /api/auth/me         返回当前登录用户信息（需要 Token）
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import bcrypt as _bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.config import Settings, get_settings
from backend.database.db_manager import get_db
from backend.database.models import User
from backend.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
CurrentUserDep = Annotated[int, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="用户名（3-50 字符）")
    password: str = Field(..., min_length=6, description="密码（至少 6 位）")
    display_name: Optional[str] = Field(None, max_length=100, description="昵称")
    email: Optional[str] = Field(None, description="邮箱（可选）")


class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    display_name: Optional[str] = None


class UserInfo(BaseModel):
    user_id: int
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def _create_access_token(user_id: int, settings: Settings) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED,
             summary="用户注册")
def register(req: RegisterRequest, settings: SettingsDep) -> TokenResponse:
    """
    注册新用户。

    - 检查用户名是否已存在。
    - 用 bcrypt 哈希密码后写入 users 表。
    - 注册成功后直接签发 JWT Token（免二次登录）。
    """
    db = get_db()
    try:
        existing = db.query(User).filter(User.username == req.username).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            )

        new_user = User(
            username=req.username,
            password_hash=_hash_password(req.password),
            display_name=req.display_name or req.username,
            email=req.email,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        logger.info("New user registered: id=%d username=%r", new_user.id, new_user.username)
    finally:
        db.close()

    token = _create_access_token(new_user.id, settings)
    return TokenResponse(
        access_token=token,
        user_id=new_user.id,
        username=new_user.username,
        display_name=new_user.display_name,
    )


@router.post("/login", response_model=TokenResponse, summary="用户登录")
def login(req: LoginRequest, settings: SettingsDep) -> TokenResponse:
    """
    使用用户名 + 密码登录，验证通过后返回 JWT Token。

    Token 有效期由 JWT_EXPIRE_MINUTES 配置（默认 24 小时）。
    """
    db = get_db()
    try:
        user = db.query(User).filter(User.username == req.username).first()
        if not user or not _verify_password(req.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 更新最后登录时间
        user.last_login = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        logger.info("User logged in: id=%d username=%r", user.id, user.username)
    finally:
        db.close()

    token = _create_access_token(user.id, settings)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
    )


@router.get("/me", response_model=UserInfo, summary="获取当前用户信息")
def me(current_user_id: CurrentUserDep) -> UserInfo:
    """
    返回当前已认证用户的基本信息（需要有效 JWT Token）。
    """
    db = get_db()
    try:
        user = db.query(User).filter(User.id == current_user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在",
            )
        return UserInfo(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            created_at=user.created_at,
        )
    finally:
        db.close()
