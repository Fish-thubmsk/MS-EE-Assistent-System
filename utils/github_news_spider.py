"""
GitHub 新闻联播爬虫模块
定期爬取指定 GitHub 仓库的新闻 MD 文件（仅当年1月1日到现在的文件）
"""

import os
import re
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Optional
import json
import time
import logging

logger = logging.getLogger(__name__)

# 配置
GITHUB_OWNER = os.getenv("GITHUB_NEWS_OWNER", "DuckBurnIncense")
GITHUB_REPO = os.getenv("GITHUB_NEWS_REPO", "xin-wen-lian-bo")
GITHUB_BRANCH = os.getenv("GITHUB_NEWS_BRANCH", "master")
GITHUB_NEWS_DIR = os.getenv("GITHUB_NEWS_DIR", "news")
LOCAL_NEWS_DIR = os.getenv("GITHUB_NEWS_LOCAL_DIR", "mock_notes/github_news")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# 爬虫参数
MAX_RETRIES = int(os.getenv("GITHUB_SPIDER_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("GITHUB_SPIDER_RETRY_DELAY", "1.0"))
DOWNLOAD_TIMEOUT = int(os.getenv("GITHUB_SPIDER_DOWNLOAD_TIMEOUT", "15"))
RATE_LIMIT_DELAY = float(os.getenv("GITHUB_SPIDER_RATE_LIMIT_DELAY", "0.5"))


class GitHubNewsSpider:
    """GitHub 新闻爬虫"""

    def __init__(
        self,
        owner: str = GITHUB_OWNER,
        repo: str = GITHUB_REPO,
        branch: str = GITHUB_BRANCH,
        news_dir: str = GITHUB_NEWS_DIR,
        local_dir: str = LOCAL_NEWS_DIR,
        github_token: Optional[str] = None,
        max_retries: int = MAX_RETRIES,
        rate_limit_delay: float = RATE_LIMIT_DELAY,
    ):
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.news_dir = news_dir
        self.local_dir = local_dir
        self.github_token = github_token or GITHUB_TOKEN
        self.base_url = "https://api.github.com"
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay
        self.headers = self._build_headers()

    def _build_headers(self) -> dict:
        """构建 API 请求头"""
        headers = {"Accept": "application/vnd.github.v3.raw"}
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
        return headers

    def list_news_files(self) -> List[dict]:
        """
        列出仓库中本年度的新闻 MD 文件
        使用 README.md 中的文件列表（动态生成，包含最新文件）
        而非 GitHub API contents 端点（可能因缓存过期而不完整）
        
        只返回 YYYYMMDD.md 格式、日期在 [今年1月1日, 今天] 范围内的文件
        """
        # 获取当前年份和日期范围
        now = datetime.now()
        current_year = now.year
        today_str = now.strftime("%Y%m%d")
        year_start = f"{current_year}0101"
        
        md_files = []
        
        try:
            # 获取 README.md 内容（包含完整的文件列表，动态更新）
            readme_url = f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{self.branch}/README.md"
            response = requests.get(readme_url, timeout=DOWNLOAD_TIMEOUT)
            response.raise_for_status()
            
            readme_content = response.text
            
            # 从 README 中提取文件名（格式: [YYYYMMDD](./news/YYYYMMDD.md)）
            import re
            pattern = r'\[(\d{8})\]\(./news/(\d{8})\.md\)'
            matches = re.findall(pattern, readme_content)
            
            logger.info(f"从 README.md 提取 {len(matches)} 个文件链接")
            
            for date_str, filename_prefix in matches:
                # 检查日期是否在本年度范围内
                if year_start <= date_str <= today_str:
                    md_files.append({
                        "name": f"{filename_prefix}.md",
                        "date": date_str,
                        "path": f"{self.news_dir}/{filename_prefix}.md",
                        "download_url": f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{self.branch}/{self.news_dir}/{filename_prefix}.md",
                        "size": 0,  # README 中没有文件大小信息
                    })
            
            logger.info(
                f"找到 {len(md_files)} 个本年度 MD 文件 ({year_start}-{today_str})"
            )
            return sorted(md_files, key=lambda x: x["name"], reverse=True)  # 按日期倒序
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取 README.md 失败: {e}，尝试使用 API 备用方案...")
            return self._list_news_files_via_api()
    
    def _list_news_files_via_api(self) -> List[dict]:
        """
        备用方案：使用 GitHub API contents 端点（可能不完整但保证可用）
        支持分页（单次最多返回 100 条）
        """
        now = datetime.now()
        current_year = now.year
        today_str = now.strftime("%Y%m%d")
        year_start = f"{current_year}0101"
        
        md_files = []
        page = 1
        
        while True:
            url = f"{self.base_url}/repos/{self.owner}/{self.repo}/contents/{self.news_dir}?per_page=100&page={page}"
            
            try:
                response = requests.get(url, headers=self.headers, timeout=DOWNLOAD_TIMEOUT)
                response.raise_for_status()
                
                items = response.json()
                
                if not items:
                    logger.info(f"API 分页获取完成，共 {page - 1} 页")
                    break
                
                for item in items:
                    if not item["name"].endswith(".md"):
                        continue
                    
                    filename_without_ext = item["name"][:-3]
                    
                    if (filename_without_ext.isdigit() and 
                        len(filename_without_ext) == 8 and
                        year_start <= filename_without_ext <= today_str):
                        md_files.append({
                            "name": item["name"],
                            "date": filename_without_ext,
                            "path": item["path"],
                            "download_url": item["download_url"],
                            "size": item["size"],
                        })
                
                page += 1
                
            except requests.exceptions.RequestException as e:
                logger.error(f"API 第 {page} 页获取失败: {e}")
                break
        
        logger.info(
            f"[API 备用] 找到 {len(md_files)} 个本年度 MD 文件 ({year_start}-{today_str})"
        )
        return sorted(md_files, key=lambda x: x["name"], reverse=True)

    def _download_with_retry(self, download_url: str) -> Optional[str]:
        """带重试的下载（指数退避）"""
        for attempt in range(self.max_retries):
            try:
                response = requests.get(download_url, timeout=DOWNLOAD_TIMEOUT)
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    delay = RETRY_DELAY * (2 ** attempt)
                    logger.debug(f"重试 {attempt + 1}/{self.max_retries - 1}，等待 {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    raise e
        return None

    def download_file(self, download_url: str, filename: str) -> bool:
        """下载单个文件"""
        try:
            content = self._download_with_retry(download_url)
            if content is None:
                return False
            
            output_path = Path(self.local_dir) / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")
            
            logger.info(f"✓ 下载: {filename} ({len(content)} 字符)")
            
            # 速率限制
            time.sleep(self.rate_limit_delay)
            return True
            
        except Exception as e:
            logger.error(f"✗ 下载 {filename} 失败: {type(e).__name__}: {e}")
            return False

    def get_already_downloaded(self) -> set:
        """获取已下载的文件列表"""
        path = Path(self.local_dir)
        if not path.exists():
            return set()
        return {f.name for f in path.glob("*.md")}

    def download_all_news(self, resume: bool = True) -> dict:
        """
        下载本年度的新闻文件
        
        Args:
            resume: 是否启用断点续传（跳过已下载的文件）
            
        Returns:
            dict: {
                "total": 本年度总文件数,
                "success": 本次成功下载数,
                "failed": 本次失败数,
                "skipped": 已存在跳过数,
                "files": [已下载的文件名],
                "timestamp": ISO 8601 时间戳
            }
        """
        now = datetime.now()
        year_range = f"{now.year}0101 - {now.strftime('%Y%m%d')}"
        
        logger.info("=" * 60)
        logger.info("GitHub 新闻爬虫 - 本年度模式")
        logger.info(f"源: {self.owner}/{self.repo}/{self.news_dir}")
        logger.info(f"范围: {year_range}")
        logger.info(f"保存: {self.local_dir}")
        logger.info(f"断点续传: {'启用' if resume else '禁用'}")
        logger.info("=" * 60)
        
        files = self.list_news_files()
        if not files:
            result = {
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "files": [],
                "timestamp": datetime.now().isoformat(),
            }
            logger.info("未找到本年度文件")
            return result
        
        # 检查已下载文件
        already_downloaded = self.get_already_downloaded() if resume else set()
        skipped_count = len(already_downloaded)
        
        success_count = 0
        failed_count = 0
        downloaded_files = []
        
        logger.info(f"总文件数: {len(files)}, 已有: {skipped_count}, 待下载: {len(files) - skipped_count}\n")
        
        for idx, file_info in enumerate(files, 1):
            # 断点续传检查
            if resume and file_info["name"] in already_downloaded:
                continue
            
            logger.info(f"[{idx}/{len(files)}] 下载 {file_info['name']}...")
            
            if self.download_file(
                file_info["download_url"],
                file_info["name"]
            ):
                success_count += 1
                downloaded_files.append(file_info["name"])
            else:
                failed_count += 1
        
        result = {
            "total": len(files),
            "success": success_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "files": downloaded_files,
            "timestamp": datetime.now().isoformat(),
        }
        
        logger.info("=" * 60)
        logger.info(f"完成: 成功 {success_count}, 失败 {failed_count}, 跳过 {skipped_count}")
        logger.info("=" * 60)
        
        # 保存统计信息
        self._save_stats(result)
        
        return result

    def _save_stats(self, result: dict):
        """保存下载统计信息"""
        stats_file = Path(self.local_dir) / "download_stats.json"
        stats_file.parent.mkdir(parents=True, exist_ok=True)
        stats_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        logger.info(f"统计已保存: {stats_file}")


async def sync_github_news():
    """
    异步同步函数（用于定时任务或后台任务）
    可在 FastAPI 启动时或定时器中调用
    """
    spider = GitHubNewsSpider()
    result = spider.download_all_news(resume=True)
    return result


def run_sync_demo():
    """演示：同步 GitHub 新闻"""
    spider = GitHubNewsSpider()
    result = spider.download_all_news(resume=True)
    
    print("\n" + "=" * 60)
    print("下载完成统计")
    print("=" * 60)
    print(f"本年度总文件: {result['total']}")
    print(f"本次下载: {result['success']}")
    print(f"下载失败: {result['failed']}")
    print(f"已跳过: {result['skipped']}")
    print(f"时间: {result['timestamp']}")
    
    if result['files']:
        print(f"\n本次下载的文件 (前 5 个):")
        for fname in result['files'][:5]:
            print(f"  - {fname}")
        if len(result['files']) > 5:
            print(f"  ... 及其他 {len(result['files']) - 5} 个文件")


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    run_sync_demo()
