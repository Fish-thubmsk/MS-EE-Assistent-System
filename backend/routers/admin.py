"""
管理路由 - 系统管理操作（同步新闻、缓存清理、环境变量配置等）
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pathlib import Path
from typing import Annotated
import json
import logging
import re

from backend.dependencies import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)

CurrentUserDep = Annotated[int, Depends(get_current_user)]

# .env 文件路径（项目根目录）
ENV_FILE = Path(".env")

# 允许通过 API 读写的 .env 键白名单（含说明）
ALLOWED_ENV_KEYS: dict[str, dict] = {
    # SiliconFlow / LLM
    "SILICONFLOW_API_KEY":   {"label": "SiliconFlow API Key",       "group": "LLM", "secret": True},
    "LLM_MODEL":             {"label": "LLM 模型名称",               "group": "LLM", "secret": False},
    "LLM_BASE_URL":          {"label": "LLM API 基础 URL",           "group": "LLM", "secret": False},
    "LLM_TEMPERATURE":       {"label": "LLM 采样温度（0.0–1.0）",    "group": "LLM", "secret": False},
    "LLM_MAX_TOKENS":        {"label": "LLM 最大生成 Token 数",      "group": "LLM", "secret": False},
    "LLM_TIMEOUT":           {"label": "LLM API 超时（秒）",         "group": "LLM", "secret": False},
    # 速率限制
    "SF_REQUEST_DELAY_SECONDS": {"label": "请求基础延迟（秒）",      "group": "速率限制", "secret": False},
    "SF_MAX_RETRIES":           {"label": "最大重试次数",             "group": "速率限制", "secret": False},
    "SF_API_TIMEOUT":           {"label": "API 请求超时（秒）",       "group": "速率限制", "secret": False},
    # Embedding
    "EMBEDDING_MODEL":       {"label": "Embedding 模型名称",         "group": "Embedding", "secret": False},
    "EMBEDDING_BASE_URL":    {"label": "Embedding API 基础 URL",     "group": "Embedding", "secret": False},
    "SILICONFLOW_API_URL":   {"label": "SiliconFlow Embedding URL",  "group": "Embedding", "secret": False},
    "EMBEDDING_DIM":         {"label": "Embedding 向量维度",         "group": "Embedding", "secret": False},
    "BATCH_SIZE":            {"label": "Embedding 批处理大小",       "group": "Embedding", "secret": False},
    # ChromaDB
    "CHROMA_PERSIST_DIRECTORY": {"label": "ChromaDB 持久化目录",    "group": "ChromaDB", "secret": False},
    "CHROMA_COLLECTION_NAME":   {"label": "ChromaDB 集合名称",       "group": "ChromaDB", "secret": False},
    # FAISS
    "FAISS_INDEX_DIR":       {"label": "FAISS 索引目录",             "group": "FAISS", "secret": False},
    "KNOWLEDGE_DB_PATH":     {"label": "SQLite 知识库路径",          "group": "FAISS", "secret": False},
    # 诊断 Agent
    "DIAGNOSIS_WEAK_THRESHOLD":    {"label": "薄弱知识点阈值（0.0–1.0）", "group": "诊断", "secret": False},
    "DIAGNOSIS_RECOMMEND_PER_POINT": {"label": "每点推荐题目数",       "group": "诊断", "secret": False},
    # FastAPI / 服务
    "APP_TITLE":             {"label": "应用标题",                   "group": "服务", "secret": False},
    "APP_VERSION":           {"label": "应用版本",                   "group": "服务", "secret": False},
    "CORS_ORIGINS":          {"label": "CORS 允许来源",              "group": "服务", "secret": False},
    "LOG_LEVEL":             {"label": "日志级别",                   "group": "服务", "secret": False},
    # JWT
    "JWT_SECRET_KEY":        {"label": "JWT 签名密钥",               "group": "JWT", "secret": True},
    "JWT_ALGORITHM":         {"label": "JWT 签名算法",               "group": "JWT", "secret": False},
    "JWT_EXPIRE_MINUTES":    {"label": "JWT 有效期（分钟）",         "group": "JWT", "secret": False},
    # RAG
    "DEFAULT_N_FAISS":       {"label": "FAISS 默认返回结果数",       "group": "RAG", "secret": False},
    "DEFAULT_N_CHROMA":      {"label": "Chroma 默认返回结果数",      "group": "RAG", "secret": False},
    "MAX_HISTORY_MESSAGES":  {"label": "对话历史最大条数",           "group": "RAG", "secret": False},
    "STREAM_CHAR_DELAY":     {"label": "流式输出字符延迟（秒）",     "group": "RAG", "secret": False},
    "RAG_USE_RERANK":        {"label": "启用重排",                   "group": "RAG", "secret": False},
    "RAG_USE_RRF":           {"label": "启用 RRF 融合",              "group": "RAG", "secret": False},
    "RRF_K":                 {"label": "RRF 参数 k",                 "group": "RAG", "secret": False},
    "RERANK_MODEL":          {"label": "重排模型",                   "group": "RAG", "secret": False},
    "RERANK_TOP_N":          {"label": "重排候选数量",               "group": "RAG", "secret": False},
    # GitHub 新闻爬虫
    "GITHUB_NEWS_OWNER":     {"label": "GitHub 仓库所有者",          "group": "GitHub爬虫", "secret": False},
    "GITHUB_NEWS_REPO":      {"label": "GitHub 仓库名称",            "group": "GitHub爬虫", "secret": False},
    "GITHUB_NEWS_DIR":       {"label": "GitHub 新闻目录",            "group": "GitHub爬虫", "secret": False},
    "GITHUB_NEWS_BRANCH":    {"label": "GitHub 分支",                "group": "GitHub爬虫", "secret": False},
    "GITHUB_NEWS_LOCAL_DIR": {"label": "本地保存目录",               "group": "GitHub爬虫", "secret": False},
    "GITHUB_TOKEN":          {"label": "GitHub API Token",           "group": "GitHub爬虫", "secret": True},
}


def _read_env_file() -> dict[str, str]:
    """解析 .env 文件，返回 key -> value 映射（仅非注释行）。"""
    result: dict[str, str] = {}
    if not ENV_FILE.exists():
        return result
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def _write_env_key(key: str, value: str) -> None:
    """将 .env 文件中 key 的值更新为 value；若键不存在则追加。"""
    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
    else:
        content = ""

    pattern = re.compile(r'^(' + re.escape(key) + r')=.*$', re.MULTILINE)
    escaped_value = value.replace('\\', '\\\\')
    if pattern.search(content):
        content = pattern.sub(r'\g<1>=' + escaped_value, content)
    else:
        if content and not content.endswith('\n'):
            content += '\n'
        content += f"{key}={value}\n"

    ENV_FILE.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# 环境变量配置接口
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_config(current_user_id: CurrentUserDep):
    """
    返回 .env 配置项（仅白名单键）。
    密钥类字段（secret=True）以掩码形式返回，不暴露真实值。
    """
    env_vals = _read_env_file()
    items = []
    for key, meta in ALLOWED_ENV_KEYS.items():
        raw = env_vals.get(key, "")
        if meta["secret"] and raw:
            display = "●" * min(len(raw), 12)
        else:
            display = raw
        items.append({
            "key":    key,
            "value":  display,
            "label":  meta["label"],
            "group":  meta["group"],
            "secret": meta["secret"],
        })
    return {"status": "success", "items": items}


@router.put("/config/{key}")
async def update_config(key: str, body: dict, current_user_id: CurrentUserDep):
    """
    更新 .env 中指定键的值（仅白名单键可写）。
    body: {"value": "new_value"}
    修改后需重启后端才能使新配置生效。
    """
    if key not in ALLOWED_ENV_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不允许修改配置项：{key}",
        )
    value = body.get("value")
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请求体中缺少 'value' 字段",
        )
    try:
        _write_env_key(key, str(value))
    except Exception as exc:
        logger.error("写入 .env 失败 key=%s: %s", key, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="写入配置文件失败",
        )
    logger.info("Admin user_id=%d updated config key=%s", current_user_id, key)
    return {"status": "success", "key": key, "message": "配置已更新，重启后端后生效"}


@router.post("/sync-github-news")
async def sync_github_news():
    """
    手动触发 GitHub 新闻同步
    
    仅下载本年度的新闻文件（YYYYMMDD.md 格式，日期从 1 月 1 日到今天）
    """
    try:
        from utils.github_news_spider import GitHubNewsSpider
        
        spider = GitHubNewsSpider()
        result = spider.download_all_news(resume=True)
        
        return {
            "status": "success",
            "message": f"同步完成: 成功{result['success']}, 失败{result['failed']}, 跳过{result['skipped']}",
            "data": result,
        }
    except Exception as e:
        logger.error(f"同步失败: {e}")
        return {
            "status": "error",
            "message": str(e),
        }


@router.get("/sync-github-news/status")
async def get_sync_status():
    """获取本地 GitHub 新闻下载统计信息"""
    from utils.github_news_spider import LOCAL_NEWS_DIR
    
    stats_file = Path(LOCAL_NEWS_DIR) / "download_stats.json"
    
    if stats_file.exists():
        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                stats = json.load(f)
            return {
                "status": "success",
                "stats": stats,
            }
        except Exception as e:
            logger.error(f"读取统计失败: {e}")
            return {
                "status": "error",
                "message": str(e),
            }
    else:
        return {
            "status": "not_synced",
            "message": "未曾同步过新闻",
        }

