"""
Application configuration via environment variables / .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # LLM provider
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-3.5-turbo"

    # Embedding model (local sentence-transformers model name or HuggingFace path)
    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    # Static knowledge base – FAISS index persisted here
    static_kb_path: str = "data/static_kb"

    # Dynamic knowledge base – SQLite file
    dynamic_kb_db_url: str = "sqlite:///data/dynamic_kb.db"

    # Retrieval
    top_k: int = 4


settings = Settings()
