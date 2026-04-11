"""
管理路由 - 系统管理操作（同步新闻、缓存清理等）
"""

from fastapi import APIRouter
from pathlib import Path
import json
import logging

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)


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

