"""
配置管理模块

通过 pydantic-settings 从 .env 文件或环境变量加载配置。
支持多模型（LLM / Embedding）切换和 SiliconFlow token 配置。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -----------------------------------------------------------------------
    # SiliconFlow / LLM API
    # -----------------------------------------------------------------------
    siliconflow_api_key: str = Field(default="", description="SiliconFlow API Key")
    llm_model: str = Field(
        description="LLM 模型名称，必须通过环境变量 LLM_MODEL 配置（推荐：deepseek-ai/DeepSeek-V3）",
    )
    llm_base_url: str = Field(
        default="https://api.siliconflow.cn/v1",
        description="LLM API 基础 URL（兼容 OpenAI Chat Completions 格式）",
    )
    llm_temperature: float = Field(default=0.3, description="LLM 采样温度")
    llm_max_tokens: int = Field(default=2048, description="LLM 最大生成 token 数")
    llm_timeout: int = Field(default=60, description="LLM API 超时秒数")

    # -----------------------------------------------------------------------
    # SiliconFlow 速率限制 & 重试
    # -----------------------------------------------------------------------
    sf_request_delay_seconds: float = Field(
        default=1.0,
        description="每次 SiliconFlow API 请求前的基础延迟（秒），用于速率限制",
    )
    sf_max_retries: int = Field(
        default=3,
        description="SiliconFlow API 最大重试次数（遇到 429 或超时时触发）",
    )
    sf_api_timeout: int = Field(
        default=60,
        description="SiliconFlow API 请求超时时间（秒）",
    )

    # -----------------------------------------------------------------------
    # Embedding
    # -----------------------------------------------------------------------
    embedding_model: str = Field(
        default="Qwen/Qwen3-Embedding-8B",
        description="Embedding 模型名称（必须与 .env 中的 EMBEDDING_MODEL 匹配，影响 EMBEDDING_DIM）",
    )
    embedding_base_url: str = Field(
        default="https://api.siliconflow.cn/v1",
        description="Embedding API 基础 URL",
    )

    # -----------------------------------------------------------------------
    # ChromaDB
    # -----------------------------------------------------------------------
    chroma_persist_directory: str = Field(
        default="chroma_userdata",
        description="ChromaDB 持久化目录路径",
    )
    chroma_collection_name: str = Field(
        default="user_notes",
        description="ChromaDB 集合名称（默认 user_notes，与 chroma_manager.py 的历史默认值保持一致）",
    )

    # -----------------------------------------------------------------------
    # FAISS
    # -----------------------------------------------------------------------
    faiss_index_dir: str = Field(
        default="knowledge_base/faiss_index",
        description="FAISS 索引文件目录路径",
    )
    embedding_dim: int = Field(
        default=1024,
        description="Embedding 向量维度（bge-m3 为 1024；切换模型时需同步调整）",
    )

    # -----------------------------------------------------------------------
    # SiliconFlow Embedding API URL
    # -----------------------------------------------------------------------
    siliconflow_api_url: str = Field(
        default="https://api.siliconflow.cn/v1/embeddings",
        description="SiliconFlow Embedding API 完整 URL（含 /embeddings 路径）",
    )

    # -----------------------------------------------------------------------
    # 诊断 Agent
    # -----------------------------------------------------------------------
    diagnosis_weak_threshold: float = Field(
        default=0.6,
        description="薄弱知识点判定阈值（准确率低于此值视为薄弱，范围 0.0–1.0）",
    )
    diagnosis_recommend_per_point: int = Field(
        default=3,
        description="每个薄弱知识点推荐题目数量",
    )

    # -----------------------------------------------------------------------
    # FastAPI / 服务
    # -----------------------------------------------------------------------
    app_title: str = Field(
        default="考研智能辅导系统 API",
        description="FastAPI 应用标题",
    )
    app_version: str = Field(default="0.2.0", description="API 版本")
    cors_origins: list[str] = Field(
        default=["*"],
        description="CORS 允许的来源列表，生产环境请收紧",
    )
    log_level: str = Field(default="INFO", description="日志级别")

    # -----------------------------------------------------------------------
    # JWT 认证
    # -----------------------------------------------------------------------
    jwt_secret_key: str = Field(
        default="",
        description="JWT 签名密钥（生产环境必须通过 JWT_SECRET_KEY 环境变量配置强随机字符串）",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT 签名算法")
    jwt_expire_minutes: int = Field(default=60 * 24, description="JWT 有效期（分钟），默认 24 小时")

    # -----------------------------------------------------------------------
    # RAG & 检索配置
    # -----------------------------------------------------------------------
    default_n_faiss: int = Field(
        default=5,
        description="FAISS 检索默认返回结果数",
    )
    default_n_chroma: int = Field(
        default=3,
        description="Chroma 检索默认返回结果数",
    )
    max_history_messages: int = Field(
        default=6,
        description="对话历史保留的最大消息条数",
    )
    stream_char_delay: float = Field(
        default=0.01,
        description="SSE 流式输出的字符延迟（秒），用于演示效果",
    )
    mock_history_path: str = Field(
        default="mock_notes/mock_user_history.json",
        description="Mock 用户历史数据路径",
    )
    batch_size: int = Field(
        default=32,
        description="Embedding API 批处理大小",
    )
    retry_base_delay: float = Field(
        default=5.0,
        description="重试基础延迟（秒），用于指数退避",
    )


import logging as _logging  # noqa: E402
import secrets as _secrets  # noqa: E402

_config_logger = _logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局单例 Settings 对象（生产/测试均可用 dependency override 替换）。"""
    s = Settings()
    if not s.jwt_secret_key:
        # 未配置 JWT_SECRET_KEY：运行时生成随机密钥（仅用于开发，重启后 Token 失效）
        _config_logger.warning(
            "JWT_SECRET_KEY not set. A random ephemeral key will be used. "
            "Tokens will be invalidated on restart. "
            "Set JWT_SECRET_KEY in .env for persistent authentication."
        )
        return s.model_copy(update={"jwt_secret_key": _secrets.token_hex(32)})
    return s
