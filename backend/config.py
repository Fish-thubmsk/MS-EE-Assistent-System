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
        default="deepseek-ai/DeepSeek-V3",
        description="LLM 模型名称，默认 DeepSeek-V3",
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
        default=30,
        description="SiliconFlow API 请求超时时间（秒）",
    )

    # -----------------------------------------------------------------------
    # Embedding
    # -----------------------------------------------------------------------
    embedding_model: str = Field(
        default="BAAI/bge-m3",
        description="Embedding 模型名称",
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
        default="notes",
        description="ChromaDB 集合名称",
    )

    # -----------------------------------------------------------------------
    # FAISS
    # -----------------------------------------------------------------------
    faiss_index_dir: str = Field(
        default="knowledge_base/faiss_index",
        description="FAISS 索引文件目录路径",
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全局单例 Settings 对象（生产/测试均可用 dependency override 替换）。"""
    return Settings()
