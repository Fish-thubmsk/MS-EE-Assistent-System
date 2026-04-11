# GitHub 新闻爬虫集成说明

## 功能概述

自动爬取 GitHub 仓库中的新闻 Markdown 文件，仅下载**当年 1 月 1 日到现在**的文件，支持：
- ✅ 断点续传（跳过已下载文件）
- ✅ 自动重试（指数退避）
- ✅ 速率限制（避免请求过快）
- ✅ 启动时自动同步
- ✅ 手动 API 触发同步
- ✅ ChromaDB 自动索引

## 默认配置

- **源仓库**: `DuckBurnIncense/xin-wen-lian-bo`
- **新闻目录**: `news/`
- **本地保存**: `mock_notes/github_news/`（此目录被 ChromaDB 监控）
- **文件格式**: `YYYYMMDD.md`（例：`20240115.md`）

## 文件位置

```
MS-EE-Assistent-System/
├── utils/
│   └── github_news_spider.py        # 爬虫核心模块
├── backend/
│   ├── main.py                      # 启动时自动同步
│   └── routers/
│       └── admin.py                 # API 端点
├── .env.example                     # 配置示例
└── mock_notes/
    └── github_news/                 # 下载目录（被 ChromaDB 监控）
```

## 环境变量配置

在 `.env` 文件中添加以下配置：

```env
# GitHub 仓库信息
GITHUB_NEWS_OWNER=DuckBurnIncense
GITHUB_NEWS_REPO=xin-wen-lian-bo
GITHUB_NEWS_DIR=news
GITHUB_NEWS_BRANCH=master

# 本地保存目录（被 ChromaDB 监控）
GITHUB_NEWS_LOCAL_DIR=mock_notes/github_news

# GitHub API Token（可选，用于提高 API 限额）
GITHUB_TOKEN=

# 爬虫参数
GITHUB_SPIDER_MAX_RETRIES=3          # 最大重试次数
GITHUB_SPIDER_RETRY_DELAY=1.0        # 初始重试延迟（秒）
GITHUB_SPIDER_DOWNLOAD_TIMEOUT=15    # 下载超时（秒）
GITHUB_SPIDER_RATE_LIMIT_DELAY=0.5   # 下载间隔（秒）
```

## 使用方式

### 1. 启动时自动同步

后端启动时，会自动在后台线程中同步 GitHub 新闻：

```python
# backend/main.py 中的启动事件
@app.on_event("startup")
def startup_event() -> None:
    _start_note_watcher()
    news_sync_thread = threading.Thread(target=_sync_github_news, daemon=True)
    news_sync_thread.start()
```

日志输出示例：
```
INFO - 开始同步 GitHub 新闻...
INFO - 找到 102 个本年度 MD 文件 (20240101-20240412)
INFO - 总文件数: 102, 已有: 5, 待下载: 97
INFO - GitHub 新闻同步完成: 总数=102, 成功=97, 失败=0, 跳过=5
```

### 2. API 手动触发

#### 手动同步新闻

```bash
curl -X POST http://localhost:8000/api/admin/sync-github-news
```

响应示例：
```json
{
  "status": "success",
  "message": "同步完成: 成功97, 失败0, 跳过5",
  "data": {
    "total": 102,
    "success": 97,
    "failed": 0,
    "skipped": 5,
    "files": ["20240101.md", "20240102.md", ...],
    "timestamp": "2024-04-12T10:23:45.123456"
  }
}
```

#### 查看同步状态

```bash
curl http://localhost:8000/api/admin/sync-github-news/status
```

响应示例：
```json
{
  "status": "success",
  "stats": {
    "total": 102,
    "success": 97,
    "failed": 0,
    "skipped": 5,
    "files": ["20240101.md", ...],
    "timestamp": "2024-04-12T10:23:45.123456"
  }
}
```

### 3. 代码中直接调用

```python
from utils.github_news_spider import GitHubNewsSpider

# 初始化爬虫
spider = GitHubNewsSpider()

# 下载新闻（断点续传）
result = spider.download_all_news(resume=True)

# 打印结果
print(f"成功: {result['success']}, 失败: {result['failed']}, 跳过: {result['skipped']}")
```

## 工作流程

### 文件过滤逻辑

1. 获取仓库 `news/` 目录中所有 MD 文件
2. 检查文件名是否为 `YYYYMMDD.md` 格式（8 位数字）
3. 检查日期是否在 `[今年0101, 今天]` 范围内
4. 返回符合条件的文件列表

### 下载逻辑

1. 遍历文件列表
2. 检查本地是否已存在（如启用断点续传）
3. 使用指数退避重试下载
4. 保存到 `mock_notes/github_news/` 目录
5. 应用速率限制（避免过快请求）

### 集成流程

```
后端启动
  ↓
初始化笔记监控 (note_watcher)
  ↓
后台线程: 同步 GitHub 新闻
  ├─ 列出仓库中本年度的文件
  ├─ 断点续传下载（失败重试）
  └─ 保存统计信息
  ↓
note_watcher 自动检测新文件
  ├─ 读取 mock_notes/github_news/ 中的 MD 文件
  ├─ 提取文本并生成 embedding
  └─ 存储到 ChromaDB
  ↓
API 问答时可查询这些新闻
```

## 监控和调试

### 日志查看

爬虫模块使用标准 Python logging，日志级别由 `LOG_LEVEL` 环境变量控制（默认 INFO）：

```bash
LOG_LEVEL=DEBUG python -m uvicorn backend.main:app --reload
```

### 检查下载目录

```bash
# 查看已下载的文件
ls -lah mock_notes/github_news/

# 查看统计信息
cat mock_notes/github_news/download_stats.json | jq
```

### 调试爬虫

```python
from utils.github_news_spider import GitHubNewsSpider

spider = GitHubNewsSpider()

# 列出本年度的所有文件
files = spider.list_news_files()
print(f"找到 {len(files)} 个文件")

# 只下载前 3 个文件进行测试
for file_info in files[:3]:
    spider.download_file(file_info["download_url"], file_info["name"])
```

## 故障排查

### 问题 1: 找不到本年度文件

**原因**: 仓库中没有当年的数据，或文件格式不对

**解决方案**:
1. 验证仓库 URL 是否正确
2. 检查文件名是否为 `YYYYMMDD.md` 格式
3. 查看爬虫日志了解过滤条件

```python
from utils.github_news_spider import GitHubNewsSpider
spider = GitHubNewsSpider()
files = spider.list_news_files()
print(f"找到 {len(files)} 个文件")
```

### 问题 2: 下载失败或超时

**原因**: 网络问题或 GitHub API 限额

**解决方案**:
1. 检查网络连接
2. 配置 GitHub Token 提高 API 限额：
   - 访问 https://github.com/settings/tokens
   - 创建 Personal Access Token（无需特殊权限）
   - 添加到 `.env` 文件: `GITHUB_TOKEN=your_token`
3. 增加重试次数或延迟：
   ```env
   GITHUB_SPIDER_MAX_RETRIES=5
   GITHUB_SPIDER_RETRY_DELAY=2.0
   GITHUB_SPIDER_DOWNLOAD_TIMEOUT=30
   ```

### 问题 3: 文件未被 ChromaDB 索引

**原因**: note_watcher 可能未启动或扫描周期未到

**解决方案**:
1. 检查 note_watcher 是否启动（日志中应有 "启动笔记文件监控")
2. 等待扫描周期（默认 5 秒）
3. 验证 `NOTES_WATCH_DIR` 环境变量指向 `mock_notes/`

## 定制化

### 更改仓库源

```python
spider = GitHubNewsSpider(
    owner="your_org",
    repo="your_repo",
    news_dir="news",
)
```

### 更改本地保存目录

```python
spider = GitHubNewsSpider(
    local_dir="/path/to/news"
)
```

### 禁用断点续传

```python
result = spider.download_all_news(resume=False)  # 重新下载所有文件
```

## 性能指标

- 文件列表获取: ~1 秒
- 单文件下载: ~100-500ms（取决于文件大小和网络）
- 本年度全年数据（~365 个文件）: ~3-5 分钟
- ChromaDB 索引: ~并行进行，不阻塞爬虫

## 注意事项

1. ⚠️ 爬虫在**后台线程**运行，不阻塞主应用启动
2. ⚠️ 本地目录 `mock_notes/github_news/` 由 ChromaDB 自动监控，新文件会自动索引
3. ⚠️ 断点续传依据文件名，重命名文件会被重新下载
4. ⚠️ GitHub API 有速率限制（无 Token: 60 req/h，有 Token: 5000 req/h）
5. ⚠️ 生产环境应考虑配置专用的 GitHub Token

## 常见场景

### 场景 1: 定时同步新闻

目前爬虫仅在启动时运行一次。如需定时同步，可使用 APScheduler：

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

def scheduled_sync():
    from utils.github_news_spider import GitHubNewsSpider
    spider = GitHubNewsSpider()
    spider.download_all_news(resume=True)

scheduler.add_job(scheduled_sync, 'cron', hour=0)  # 每天午夜同步
scheduler.start()
```

### 场景 2: 前端显示最新新闻

新闻文件下载后会自动被 ChromaDB 索引，可通过现有 `/api/answer` 接口查询：

```bash
curl "http://localhost:8000/api/answer?query=最近的新闻&n=5"
```

### 场景 3: 导出已下载的新闻

```python
from pathlib import Path
import json

news_dir = Path("mock_notes/github_news")
news_files = sorted(news_dir.glob("*.md"))

for md_file in news_files:
    print(f"- {md_file.name}")
    # print(md_file.read_text()[:200])  # 预览前 200 字
```

---

**最后更新**: 2024-04-12
**版本**: 1.0
