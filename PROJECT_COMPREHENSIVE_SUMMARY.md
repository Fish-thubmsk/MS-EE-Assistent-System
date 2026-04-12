# 考研智能辅导系统 - 项目全面总结

## 一. 项目概述

**项目名称**: MS-EE-Assistent-System（考研智能辅导系统）

**技术栈**: 
- 后端: FastAPI + LangGraph + SQLAlchemy + ChromaDB + FAISS
- 前端: 静态 HTML (前期)
- 数据库: SQLite (知识库 + 用户数据)
- LLM 集成: SiliconFlow API (DeepSeek-V3 等模型)
- 向量化: SiliconFlow Embedding API
- 部署: Docker + Docker Compose + Nginx

**应用版本**: 0.2.0

**目标用途**: 为考研学生提供智能化的刷题、问答、学习诊断等功能的综合辅导平台。

---

## 二. 核心架构

### 2.1 整体流程设计

系统采用**模式识别 + 路由分发**的架构:

```
用户输入
   ↓
Router Agent (意图识别)
   ├─→ Quiz Mode (刷题模式)
   │    ├─ Student Agent (追问生成)
   │    └─ Teacher Agent (批改讲解)
   ├─→ QA Mode (问答模式)
   │    └─ RAG Agent (检索增强生成)
   └─→ Diagnosis Mode (诊断模式)
        └─ Diagnosis Agent (学习轨迹分析)
```

### 2.2 关键模块分层

| 层级 | 模块 | 职责 |
|------|------|------|
| **API 层** | backend/routers/* | RESTful 接口定义与处理 |
| **Agent 层** | agents/* | LangGraph 工作流编排 |
| **知识库** | knowledge_base/* | 向量化与检索管理 |
| **存储层** | backend/database/* | SQLAlchemy ORM 与数据持久化 |
| **工具层** | utils/* | 重试机制、爬虫等通用工具 |
| **配置层** | backend/config.py | 环境变量加载与全局设置 |

---

## 三. 数据库架构

### 3.1 双数据库设计

#### A. knowledge_base.db (只读知识库)
**位置**: `datebase/knowledge_base.db` (4.8MB)

**表结构** (7张表):
- **subjects**: 数学科目表 (math1/math2/math3)
- **papers**: 数学试卷表 (year, paper_no等)
- **questions_math**: 数学题目 (stem, question_type等)
- **questions_politics**: 政治题目 (id, year, question_type, stem, correct_answer, analysis, difficulty, score)
- **questions_english**: 英语题目 (id, year, question_number, question_type, content, translation)
- **sub_questions**: 统一小问表 (跨科目)
- **options**: 统一选项表 (跨科目)

**数据规模**:
- 4922 条小问记录
- 11930 条选项记录

#### B. userdata.db (可读写用户数据)
**位置**: `datebase/userdata.db` (通过 SQLAlchemy ORM 管理)

**表结构** (3张表):
- **users**: 用户账号表
  - id (PK), username (UNIQUE), password_hash (bcrypt), display_name, email
  - created_at, last_login

- **quiz_records**: 答题记录表
  - id (PK), user_id (FK), question_id, subject, year, knowledge_point
  - is_correct, score, user_answer, feedback, created_at

- **diagnosis_reports**: 诊断报告表
  - id (PK), user_id (FK), report_date, analysis_result (JSON), created_at

**初始化**: 启动时自动调用 `init_db()`, 自动创建表、插入3条演示用户
- user_001: exam2024 (同学甲)
- user_002: exam2024 (同学乙)
- user_003: exam2024 (同学丙)

### 3.2 向量存储

#### FAISS 索引
**路径**: `knowledge_base/faiss_index/`

**文件**:
- `questions.index`: FAISS 向量索引 (IVF_FLAT)
- `id_map.json`: doc_id 到数据库表的映射

**文档 ID 格式**:
- `qm_<id>`: 数学题 (questions_math)
- `qp_<id>`: 政治题 (questions_politics)
- `qe_<id>`: 英语题 (questions_english)
- `sq_<id>`: 小问 (sub_questions)

**维度**: 1024 (Qwen/Qwen3-Embedding-8B)

#### ChromaDB 向量库
**路径**: `chroma_userdata/`

**用途**: 存储用户笔记、错题等动态内容

**集合**:
- `user_notes`: 默认集合 (可配置)

**元数据**:
- subject: 学科 (数学/政治/英语)
- type: 笔记类型 (note/wrong)

**状态文件**: `.watcher_state.json` (记录已处理文件的 mtime 与 doc_id)

---

## 四. 后端 API 设计

### 4.1 认证模块 (backend/routers/auth.py)

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/auth/register` | POST | 用户注册 (返回 JWT Token) |
| `/api/auth/login` | POST | 用户登录 |
| `/api/auth/me` | GET | 获取当前用户信息 |

**身份验证**: JWT Bearer Token (HS256)
- 密钥: `JWT_SECRET_KEY` (生产必填，开发自动生成)
- 有效期: 默认24小时 (可配置)
- 密码: bcrypt 哈希存储

### 4.2 刷题模块 (backend/routers/practice.py)

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/practice/subjects` | GET | 获取科目列表 (政治/数学/英语) |
| `/api/practice/types/{subject}` | GET | 获取题型列表 |
| `/api/practice/years/{subject}` | GET | 获取年份列表 |
| `/api/practice/question` | GET | 随机获取题目 (支持筛选) |
| `/api/practice` | POST | 提交答案获取批改结果 |
| `/api/practice/stream` | POST | SSE 流式返回解析 |

**题目筛选参数**:
- subject: 科目 (politics/math/english)
- year: 年份
- question_type: 题型

### 4.3 笔记模块 (backend/routers/notes.py)

| 接口 | 方法 | 功能 |
|------|------|------|
| `/notes/` | POST | 新增/更新笔记 (文本) |
| `/notes/file` | POST | 从 MD 文件新增笔记 |
| `/notes/{doc_id}` | DELETE | 删除笔记 |
| `/notes/query` | GET | 向量相似度检索 |
| `/notes/count` | GET | 获取笔记总数 |

**检索参数**:
- q: 查询文本 (必填)
- n: 返回数量 (默认5, 范围1-50)
- subject: 按学科过滤
- type: 按笔记类型过滤 (note/wrong)

### 4.4 问答模块 (backend/routers/answer.py)

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/answer` | POST | 同步 RAG 问答 |
| `/api/answer/stream` | POST | SSE 流式 RAG 问答 |
| `/api/answer/mock` | GET | Mock 数据快速体验 |

**输入参数**:
- user_input: 用户问题 (必填)
- messages: 对话历史 (可选)
- params: 路由参数 (可选)
- use_faiss: 是否检索静态知识库 (默认true)
- use_chroma: 是否检索动态笔记 (默认false)

**输出**:
- answer: 完整答案
- citations: 引用列表 [1], [2]...
- recommendations: 相似推荐

### 4.5 诊断模块 (backend/routers/diagnosis.py)

| 接口 | 方法 | 功能 |
|------|------|------|
| `/diagnosis/run` | POST | 运行学习诊断 |
| `/diagnosis/mock` | GET | Mock 数据快速体验 |

**诊断流程**:
1. 加载用户做题历史 (real DB或mock JSON)
2. 分析薄弱知识点 (准确率低于阈值)
3. 为薄弱点推荐相关题目与笔记
4. 生成结构化诊断报告

**配置参数**:
- weak_threshold: 薄弱点准确率阈值 (默认0.6)
- recommend_per_point: 每个薄弱点推荐题目数 (默认3)

### 4.6 意图路由模块 (backend/routers/chat.py)

| 接口 | 方法 | 功能 |
|------|------|------|
| `/chat/route` | POST | 意图识别与路由 |

**识别模式**:
- quiz: 刷题模式
- qa: 问答模式
- diagnosis: 诊断模式
- unknown: 未识别

**输出**:
- mode: 主模式
- sub_mode: 子模式
- params: 提取的参数 (subject, year等)
- intent_confidence: 置信度 (0.0-1.0)
- messages: 更新后的消息列表
- session_history: 会话历史记录

### 4.7 管理模块 (backend/routers/admin.py)

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/admin/sync-github-news` | POST | 手动同步 GitHub 新闻 |
| `/api/admin/sync-github-news/status` | GET | 获取同步状态统计 |

---

## 五. Agent 工作流

### 5.1 Router Agent (agents/router_agent.py)

**职责**: 用户意图识别与模式路由

**模式注册表**:
```
MODE_REGISTRY = {
    "quiz": {
        "sub_modes": ["follow_up", "grading", "explanation"],
        "description": "刷题辅导：追问、批改、讲解"
    },
    "qa": {
        "sub_modes": ["knowledge", "concept", "with_notes"],
        "description": "知识问答：知识点、概念、融合笔记"
    },
    "diagnosis": {
        "sub_modes": ["trajectory", "weak_analysis"],
        "description": "学习诊断：学习轨迹分析、弱项推荐"
    }
}
```

**识别策略**:
1. 关键词匹配 (快速规则降级)
2. LLM 意图识别 (可用时)

**参数提取**:
- subject: 学科 (数学/政治/英语)
- year: 年份 (2024/2023等)
- difficulty: 难度 (easy/medium/hard)
- knowledge_point: 知识点

### 5.2 Quiz Agent (agents/quiz_agent.py)

**工作流**:
```
START
 ├─ load_question
 ├─ student_agent (生成追问)
 ├─ teacher_agent (判题 → 解析 → 纠错)
 └─ END
```

**功能**:
- **Student Agent**: 自动生成 3-5 个分层追问
- **Teacher Agent**: 
  - 基于 correct_answer + analysis 判题
  - 结合 knowledge_points 分层解析
  - 生成个性化纠错建议
  - 支持 FAISS/Chroma 知识库检索补充

**LLM 降级**: 无 API Key 时使用规则批改

### 5.3 RAG Agent (agents/rag_agent.py)

**工作流**:
```
START
 ├─ retrieve_faiss (静态知识库)
 ├─ retrieve_chroma (动态笔记库，可选)
 ├─ fuse_context (融合去重排序)
 ├─ call_llm (生成答案)
 └─ END
```

**检索策略**:
1. FAISS: 题库内容 (优先)
2. Chroma: 用户笔记 (可选)
3. 融合: 按相似度排序，去重

**答案生成**:
- 引用溯源: [1] 来源: ...
- 相似推荐: 其他相关题目/知识点
- 模板回复: LLM 不可用时的降级方案

**上下文**:
- 历史消息: 最近 6 条 (可配置)
- 融合检索: FAISS 5条 + Chroma 3条

### 5.4 Diagnosis Agent (agents/diagnosis_agent.py)

**工作流**:
```
START
 ├─ load_history (real DB或 mock JSON)
 ├─ analyze_weak_points (Analyzer 子Agent)
 ├─ recommend_resources (Recommender 子Agent)
 ├─ generate_report (汇总报告)
 └─ END
```

**弱点分析**:
- 按知识点统计准确率
- 低于阈值的标记为薄弱点
- 分为高/中/低优先级

**资源推荐**:
- 从 knowledge_base.db 推荐相关题目
- 从 Chroma 推荐相关笔记
- 按难度/优先级排序

**数据源**:
1. 真实数据: quiz_records 表 (用户已答题)
2. Mock 数据: mock_notes/mock_user_history.json (演示用)

---

## 六. 知识库管理

### 6.1 FAISS 索引构建

**脚本**: `knowledge_base/build_faiss_index.py`

**执行命令**:
```bash
python knowledge_base/build_faiss_index.py [--subject 政治] [--batch-size 32]
```

**过程**:
1. 连接 knowledge_base.db
2. 逐批向 SiliconFlow Embedding API 请求向量化
3. 构建 FAISS 索引 (IVF_FLAT 算法)
4. 保存 id_map.json (映射doc_id到源表)

**增量支持**: 已索引文档自动跳过 (通过 id_map.json)

**配置**:
- BATCH_SIZE: 批处理大小 (默认32)
- EMBEDDING_DIM: 向量维度 (默认1024)
- SILICONFLOW_API_KEY: 必填

### 6.2 知识库构建

**脚本**: `datebase/build_knowledge_base.py`

**数据源**: `参考/JSON汇总/` 目录下的 JSON 文件

**数据导入**:
1. 解析政治/数学/英语 JSON
2. 规范化表结构 (7张表)
3. 建立表间关系 (FK约束)
4. 持久化至 knowledge_base.db

**兼容性**: 新旧表结构自动迁移

### 6.3 笔记文件监控

**脚本**: `knowledge_base/note_watcher.py`

**用法**:
```bash
python knowledge_base/note_watcher.py [--notes-dir mock_notes] [--once]
```

**功能**:
- 扫描目录下全部 .md 文件
- 比对 mtime 检测新增/变更/删除
- 自动向量化后存入 ChromaDB
- 删除文件自动移除对应索引

**配置**:
- WATCHER_SCAN_INTERVAL: 扫描间隔 (默认5秒)
- NOTES_WATCH_DIR: 监控目录 (默认 mock_notes/)

**状态持久化**: `.watcher_state.json`

---

## 七. 核心工具库

### 7.1 SiliconFlow 重试机制 (utils/sf_retry.py)

**功能**: HTTP 请求的指数退避重试

**触发条件**:
- HTTP 429 (速率限制)
- 请求超时

**配置**:
| 环境变量 | 默认值 | 说明 |
|---------|-------|------|
| SF_REQUEST_DELAY_SECONDS | 1.0 | 基础延迟 (秒) |
| SF_MAX_RETRIES | 3 | 最大重试次数 |
| SF_API_TIMEOUT | 30 | API 超时时间 (秒) |

**重试策略**: 延迟 = base_delay × 2^attempt

### 7.2 GitHub 新闻爬虫 (utils/github_news_spider.py)

**功能**: 定期爬取 GitHub 仓库新闻

**配置** (环境变量):
| 环境变量 | 默认值 | 说明 |
|---------|-------|------|
| GITHUB_NEWS_OWNER | DuckBurnIncense | 仓库所有者 |
| GITHUB_NEWS_REPO | xin-wen-lian-bo | 仓库名称 |
| GITHUB_NEWS_BRANCH | master | 分支 |
| GITHUB_NEWS_DIR | news | 新闻目录 |
| GITHUB_NEWS_LOCAL_DIR | mock_notes/github_news | 本地保存目录 |
| GITHUB_TOKEN | (空) | GitHub Token (可选，提高速率限制) |

**爬虫参数**:
- MAX_RETRIES: 最大重试次数 (默认3)
- RETRY_DELAY: 重试延迟 (默认1.0秒)
- DOWNLOAD_TIMEOUT: 下载超时 (默认15秒)
- RATE_LIMIT_DELAY: 速率限制延迟 (默认0.5秒)

**数据源**: 仅下载当年 1 月 1 日至今的 YYYYMMDD.md 格式文件

---

## 八. 配置管理

### 8.1 全局配置 (backend/config.py)

**加载方式**: Pydantic Settings (从 .env 或环境变量)

**配置分类**:

#### LLM & API
| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| SILICONFLOW_API_KEY | (无) | SiliconFlow API Key (必填) |
| LLM_MODEL | (无) | LLM 模型名称 (如 deepseek-ai/DeepSeek-V3, 必填) |
| LLM_BASE_URL | https://api.siliconflow.cn/v1 | LLM API 基础 URL |
| LLM_TEMPERATURE | 0.3 | LLM 采样温度 |
| LLM_MAX_TOKENS | 2048 | LLM 最大生成 token 数 |
| LLM_TIMEOUT | 60 | LLM API 超时 (秒) |

#### Embedding
| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| EMBEDDING_MODEL | Qwen/Qwen3-Embedding-8B | Embedding 模型 |
| EMBEDDING_DIM | 1024 | Embedding 向量维度 |
| EMBEDDING_BASE_URL | https://api.siliconflow.cn/v1 | Embedding API 基础 URL |
| SILICONFLOW_API_URL | https://api.siliconflow.cn/v1/embeddings | Embedding API 完整 URL |

#### ChromaDB
| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| CHROMA_PERSIST_DIRECTORY | chroma_userdata | ChromaDB 持久化目录 |
| CHROMA_COLLECTION_NAME | user_notes | ChromaDB 集合名称 |

#### FAISS
| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| FAISS_INDEX_DIR | knowledge_base/faiss_index | FAISS 索引目录 |

#### 诊断配置
| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| DIAGNOSIS_WEAK_THRESHOLD | 0.6 | 薄弱点准确率阈值 |
| DIAGNOSIS_RECOMMEND_PER_POINT | 3 | 每个薄弱点推荐题数 |

#### 服务配置
| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| APP_TITLE | 考研智能辅导系统 API | FastAPI 标题 |
| APP_VERSION | 0.2.0 | API 版本 |
| CORS_ORIGINS | ["*"] | CORS 允许来源 (生产环改) |
| LOG_LEVEL | INFO | 日志级别 |

#### JWT 认证
| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| JWT_SECRET_KEY | (无) | JWT 签名密钥 (生产必填) |
| JWT_ALGORITHM | HS256 | JWT 算法 |
| JWT_EXPIRE_MINUTES | 1440 | JWT 有效期 (24小时) |

#### RAG 检索
| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| DEFAULT_N_FAISS | 5 | FAISS 默认返回数 |
| DEFAULT_N_CHROMA | 3 | Chroma 默认返回数 |
| MAX_HISTORY_MESSAGES | 6 | 对话历史最大消息数 |
| STREAM_CHAR_DELAY | 0.01 | SSE 流式字符延迟 (秒) |

### 8.2 环境变量文件

**文件**: `.env` (项目根目录)

**示例**:
```env
SILICONFLOW_API_KEY=sk-xxxxxxxxxxxx
LLM_MODEL=deepseek-ai/DeepSeek-V3
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
JWT_SECRET_KEY=your-secret-key-here
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
LOG_LEVEL=INFO
```

---

## 九. 依赖管理

### 9.1 核心依赖 (requirements.txt)

#### Web 框架
- fastapi >= 0.110.0
- uvicorn[standard] >= 0.29.0
- python-multipart >= 0.0.9

#### AI/ML
- langgraph >= 0.1.0
- langchain >= 0.2.0
- langchain-community >= 0.2.0
- langchain-openai >= 0.1.0

#### 向量存储
- faiss-cpu >= 1.8.0
- chromadb >= 0.5.0

#### 数据库
- sqlalchemy >= 2.0.0

#### 认证
- PyJWT >= 2.12.0
- bcrypt >= 4.0.0

#### HTTP
- httpx >= 0.27.0
- requests >= 2.31.0

#### 工具
- python-dotenv >= 1.0.0
- pydantic >= 2.0.0
- pydantic-settings >= 2.0.0

#### 测试
- pytest >= 8.0.0
- pytest-asyncio >= 0.23.0

---

## 十. 启动与运行

### 10.1 后端启动

**脚本**: `backend/main.py`

**启动方式**:
```bash
# 开发环境
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 生产环境
gunicorn -w 4 -k uvicorn.workers.UvicornWorker backend.main:app
```

**自启任务** (后台线程):
1. 笔记文件监控 (note_watcher)
2. GitHub 新闻同步 (github_news_spider)

**初始化** (startup event):
1. 初始化 userdata.db (幂等)
2. 启动笔记监控线程
3. 启动 GitHub 新闻同步线程

### 10.2 API 文档

**Swagger UI**: `http://localhost:8000/docs`
**ReDoc**: `http://localhost:8000/redoc`
**OpenAPI JSON**: `http://localhost:8000/openapi.json`

### 10.3 健康检查

| 端点 | 响应 |
|------|------|
| GET / | {"status": "ok"} |
| GET /health | {"status": "ok", "version": "0.2.0"} |

---

## 十一. 数据库初始化流程

### 11.1 启动时初始化

**触发点**: `backend/main.py` 应用启动

**调用栈**:
```
FastAPI 启动
 ├─ init_db() [backend/database/db_manager.py]
 │   ├─ get_engine() ← 创建 SQLite 引擎
 │   ├─ Base.metadata.create_all() ← 创建所有表
 │   └─ _seed_demo_users() ← 插入演示账号
 └─ 记录初始化完成日志
```

### 11.2 演示用户种子数据

**自动插入** (仅当不存在时):
```
user_001 / exam2024 / 同学甲
user_002 / exam2024 / 同学乙
user_003 / exam2024 / 同学丙
```

**密码**: 使用 bcrypt 哈希存储

### 11.3 知识库初始化

**执行命令**:
```bash
python datebase/build_knowledge_base.py
```

**流程**:
1. 读取 `参考/JSON汇总/` JSON 文件
2. 解析数据并规范化
3. 创建表并插入数据
4. 验证数据完整性

**结果**: `datebase/knowledge_base.db` (4.8MB, 只读)

---

## 十二. 前端架构

### 12.1 静态页面

**位置**: `frontend/`

**文件**:
- `index.html`: 主页 (首页/导航)
- `login.html`: 登录页面
- `register.html`: 注册页面

**当前状态**: 基础布局，与后端 API 集成开发中

### 12.2 API 集成流程

**流程**:
1. 用户通过 login.html 登录
2. 后端返回 JWT Token (stored in localStorage)
3. 后续请求带上 `Authorization: Bearer <token>`
4. 前端根据 /chat/route 响应动态渲染页面

---

## 十三. 部署配置

### 13.1 Docker 构建

**文件**: `docker/Dockerfile` (后端) 和 `docker/Dockerfile.frontend` (前端)

**构建命令**:
```bash
docker build -f docker/Dockerfile -t ms-ee-backend:latest .
docker build -f docker/Dockerfile.frontend -t ms-ee-frontend:latest .
```

### 13.2 Docker Compose

**文件**: `docker/docker-compose.yml`

**服务**:
- backend: FastAPI 服务 (端口8000)
- frontend: Nginx 静态服务 (端口3000)

**启动命令**:
```bash
docker-compose -f docker/docker-compose.yml up -d
```

### 13.3 Nginx 配置

**文件**: `docker/nginx.conf`

**功能**:
- 静态文件托管 (frontend/)
- 反向代理 API (/api -> backend)

---

## 十四. 核心交互示例

### 14.1 刷题流程

```
1. GET /api/practice/subjects → 获取科目列表
2. GET /api/practice/question?subject=math → 获取随机题目
3. POST /api/practice {user_answer, question_id} → 提交答案
   ↓ (后端)
   Quiz Agent 工作流
   ├─ 基于 correct_answer 判题
   ├─ 生成详细解析 (含 analysis 字段)
   ├─ 生成追问 (Student Agent)
   └─ 返回批改结果与讲解
4. 前端显示: 判题结果 + 解析 + 追问
```

### 14.2 问答流程

```
1. POST /chat/route {user_input} → 意图识别
   ← mode: "qa", confidence: 0.95
2. POST /api/answer {user_input} → 获取答案
   ↓ (后端)
   RAG Agent 工作流
   ├─ FAISS 检索 (静态知识库)
   ├─ Chroma 检索 (可选，用户笔记)
   ├─ 融合上下文
   ├─ 调用 LLM 生成答案
   └─ 返回答案 + 引用 + 推荐
3. 前端显示: 答案 + 溯源引用
```

### 14.3 诊断流程

```
1. POST /diagnosis/run {user_id} → 运行诊断
   ↓ (后端)
   Diagnosis Agent 工作流
   ├─ 加载 quiz_records (用户做题历史)
   ├─ 按知识点统计准确率
   ├─ 识别薄弱点 (阈值: 0.6)
   ├─ 推荐相关题目 + 笔记
   └─ 生成诊断报告
2. 前端显示: 薄弱点列表 + 推荐资源
```

---

## 十五. 模块依赖关系

```
frontend/ (HTML 页面)
   ↓
   ← /docs → backend/main.py (FastAPI 应用)
              ├─ backend/routers/* (API 路由)
              │   ├─ auth.py (认证)
              │   ├─ practice.py (刷题)
              │   ├─ notes.py (笔记)
              │   ├─ answer.py (问答)
              │   ├─ chat.py (路由)
              │   ├─ diagnosis.py (诊断)
              │   └─ admin.py (管理)
              │
              ├─ agents/* (LangGraph 工作流)
              │   ├─ router_agent.py (意图识别)
              │   ├─ quiz_agent.py (刷题)
              │   ├─ rag_agent.py (问答)
              │   └─ diagnosis_agent.py (诊断)
              │
              ├─ backend/database/* (ORM 与持久化)
              │   ├─ models.py (SQLAlchemy 模型)
              │   └─ db_manager.py (引擎管理)
              │
              ├─ knowledge_base/* (向量库)
              │   ├─ chroma_manager.py (ChromaDB)
              │   ├─ build_faiss_index.py (FAISS 构建)
              │   └─ note_watcher.py (文件监控)
              │
              ├─ utils/* (工具库)
              │   ├─ sf_retry.py (重试机制)
              │   └─ github_news_spider.py (爬虫)
              │
              └─ backend/config.py (配置管理)

数据流:
   SiliconFlow API (LLM + Embedding)
           ↑
           |
   Backend (处理逻辑)
      ├─ knowledge_base.db (只读题库)
      ├─ userdata.db (用户数据)
      ├─ FAISS 索引 (向量检索)
      └─ ChromaDB (动态笔记)
```

---

## 十六. 关键特性

### 16.1 多模式智能识别

- 自动识别用户意图 (刷题/问答/诊断)
- 支持跨轮次模式切换
- 可配置意图置信度阈值

### 16.2 混合检索 (RAG)

- FAISS (题库优先)
- ChromaDB (用户笔记)
- 自动融合排序去重

### 16.3 流式输出 (SSE)

- 实时返回 LLM 生成内容
- 配置字符延迟以优化用户体验
- 支持同步和异步接口

### 16.4 个性化诊断

- 基于做题历史分析薄弱点
- 分层推荐相关题目
- 生成结构化学习报告

### 16.5 JWT 认证

- 用户登录/注册
- Token 有效期管理
- bcrypt 密码哈希

### 16.6 增量笔记监控

- 自动检测文件变更
- 增量向量化入库
- 状态持久化避免重复处理

### 16.7 LLM 优雅降级

- API 不可用时自动切换规则模式
- 提供基础功能保障
- 清晰的日志提示

---

## 十七. 测试框架

### 17.1 测试工具

**框架**: pytest + pytest-asyncio

**配置**: `tests/conftest.py`
- 预设 LLM_MODEL 环境变量 (CI 友好)

### 17.2 测试文件

| 文件 | 功能 |
|------|------|
| test_backend_routers.py | API 路由测试 |
| test_chroma_manager.py | ChromaDB 管理测试 |
| test_faiss_index.py | FAISS 索引测试 |
| test_router_agent.py | 路由意图识别测试 |
| test_quiz_agent.py | 刷题工作流测试 |
| test_rag_agent.py | RAG 问答测试 |
| test_diagnosis_agent.py | 诊断工作流测试 |
| test_note_watcher.py | 笔记监控测试 |
| test_sf_retry.py | 重试机制测试 |

---

## 十八. 项目文件树

```
MS-EE-Assistent-System/
├── backend/
│   ├── __init__.py
│   ├── main.py                    ← FastAPI 应用入口
│   ├── config.py                  ← 全局配置管理
│   ├── dependencies.py            ← JWT 认证依赖
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py              ← SQLAlchemy ORM 模型
│   │   └── db_manager.py          ← 数据库管理与初始化
│   └── routers/
│       ├── __init__.py
│       ├── auth.py                ← 认证路由
│       ├── practice.py            ← 刷题路由
│       ├── notes.py               ← 笔记路由
│       ├── chat.py                ← 路由意图识别
│       ├── answer.py              ← 问答路由
│       ├── diagnosis.py           ← 诊断路由
│       └── admin.py               ← 管理路由
├── agents/
│   ├── __init__.py
│   ├── router_agent.py            ← 意图识别
│   ├── quiz_agent.py              ← 刷题工作流
│   ├── rag_agent.py               ← RAG 问答工作流
│   └── diagnosis_agent.py         ← 学习诊断工作流
├── knowledge_base/
│   ├── __init__.py
│   ├── chroma_manager.py          ← ChromaDB 管理
│   ├── build_faiss_index.py       ← FAISS 索引构建
│   ├── note_watcher.py            ← 笔记文件监控
│   ├── faiss_index/               ← FAISS 索引存储
│   │   ├── questions.index
│   │   └── id_map.json
│   └── [其他可选模块]
├── datebase/
│   ├── build_knowledge_base.py    ← 知识库构建脚本
│   ├── knowledge_base.db          ← 题库 (只读)
│   └── userdata.db                ← 用户数据 (读写)
├── utils/
│   ├── __init__.py
│   ├── sf_retry.py                ← SiliconFlow 重试
│   └── github_news_spider.py      ← GitHub 爬虫
├── frontend/
│   ├── index.html                 ← 主页
│   ├── login.html                 ← 登录页
│   └── register.html              ← 注册页
├── docker/
│   ├── Dockerfile                 ← 后端镜像
│   ├── Dockerfile.frontend        ← 前端镜像
│   ├── docker-compose.yml         ← 编排配置
│   └── nginx.conf                 ← Nginx 配置
├── tests/
│   ├── conftest.py                ← 测试配置
│   ├── test_*.py                  ← 各模块测试
│   └── [其他测试]
├── mock_notes/                    ← Mock 笔记与历史数据
│   ├── *.md                       ← 示例笔记文件
│   ├── mock_user_history.json     ← Mock 做题记录
│   └── github_news/               ← GitHub 新闻存储
├── chroma_userdata/               ← ChromaDB 数据 (动态生成)
│   └── .watcher_state.json        ← 笔记监控状态
├── 参考/                          ← 参考资料与数据
│   └── JSON汇总/                  ← 题目 JSON 数据源
├── requirements.txt               ← Python 依赖
├── .env.example                   ← 配置示例
├── .gitignore
├── README.md
├── LICENSE
└── [其他配置文件]
```

---

## 十九. 常见操作指南

### 19.1 启动开发服务

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 SILICONFLOW_API_KEY 等

# 3. 初始化知识库 (首次)
python datebase/build_knowledge_base.py

# 4. 构建 FAISS 索引 (首次或更新)
python knowledge_base/build_faiss_index.py

# 5. 启动后端
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 6. 访问 API 文档
# http://localhost:8000/docs
```

### 19.2 启动笔记监控 (手动)

```bash
python knowledge_base/note_watcher.py --notes-dir mock_notes
```

### 19.3 同步 GitHub 新闻 (手动)

```bash
curl -X POST http://localhost:8000/api/admin/sync-github-news
```

### 19.4 运行测试

```bash
pytest tests/ -v
pytest tests/test_backend_routers.py -v
pytest tests/test_quiz_agent.py -v --asyncio-mode=auto
```

### 19.5 Docker 部署

```bash
docker-compose -f docker/docker-compose.yml up -d
# 服务运行于:
# - 后端: http://localhost:8000
# - 前端: http://localhost:3000
```

---

## 二十. 技术栈总结

| 类别 | 选型 | 版本要求 |
|------|------|---------|
| **Web 框架** | FastAPI | >= 0.110.0 |
| **ASGI 服务器** | Uvicorn | >= 0.29.0 |
| **工作流编排** | LangGraph | >= 0.1.0 |
| **LLM 集成** | LangChain + OpenAI SDK | >= 0.2.0 |
| **向量检索** | FAISS + ChromaDB | >= 1.8.0 / >= 0.5.0 |
| **ORM** | SQLAlchemy | >= 2.0.0 |
| **认证** | JWT + bcrypt | PyJWT >= 2.12.0 / bcrypt >= 4.0.0 |
| **HTTP 客户端** | httpx + requests | >= 0.27.0 / >= 2.31.0 |
| **配置管理** | Pydantic Settings | >= 2.0.0 |
| **测试框架** | pytest | >= 8.0.0 |
| **容器化** | Docker + Docker Compose | 最新版 |
| **反向代理** | Nginx | 最新版 |

---

## 二十一. 环境要求

### 最低配置
- **OS**: Windows/Linux/macOS
- **Python**: 3.10+
- **内存**: 4GB+ (FAISS 索引加载)
- **磁盘**: 5GB+ (知识库 + 向量索引 + ChromaDB)

### 依赖服务
- **SiliconFlow API**: LLM 与 Embedding 模型调用
- **GitHub API**: 新闻爬取 (可选)
- **网络**: 对外网络连接 (调用第三方 API)

---

## 二十二. 已知限制与后续规划

### 当前限制
1. 前端为静态页面，集成开发中
2. 笔记监控仅支持本地文件系统
3. 诊断功能基于准确率统计，可继续优化算法
4. 向量模型固定为 Qwen/Qwen3-Embedding-8B

### 后续规划
1. 构建完整的 React/Vue 前端
2. 支持用户文件上传与处理
3. 实现更复杂的学习轨迹分析
4. 多模型支持与动态切换
5. 细粒度权限控制与多租户
6. 本地 LLM 部署支持

---

## 二十三. 故障排查

### 问题: ChromaDB 初始化失败

**症状**: `ChromaManager 初始化失败，Chroma 检索将不可用`

**原因**: SILICONFLOW_API_KEY 未配置或 embedding_model 参数错误

**解决**: 
1. 检查 .env 中的 SILICONFLOW_API_KEY
2. 确认 EMBEDDING_MODEL 值有效

### 问题: FAISS 索引加载失败

**症状**: `IndexError: index out of range`

**原因**: 向量维度不匹配或索引文件损坏

**解决**:
1. 检查 EMBEDDING_DIM 与实际嵌入维度一致 (默认1024)
2. 重新构建索引: `python knowledge_base/build_faiss_index.py`

### 问题: LLM API 超时

**症状**: `TimeoutException: Request timed out`

**原因**: SiliconFlow API 响应慢或网络问题

**解决**:
1. 检查网络连接
2. 提高 LLM_TIMEOUT 配置值 (默认60秒)
3. 系统自动重试 (SF_MAX_RETRIES, 默认3次)

### 问题: JWT Token 验证失败

**症状**: `401 Unauthorized: 无效的认证 Token`

**原因**: Token 已过期或签名密钥不匹配

**解决**:
1. 重新登录获取新 Token
2. 确保 JWT_SECRET_KEY 在服务器重启后一致 (生产必配)

---

## 附录: 关键代码片段

### A. 快速 API 测试

```bash
# 注册用户
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass123"}'

# 登录
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass123"}'

# 获取题目
curl "http://localhost:8000/api/practice/question?subject=math"

# 意图识别
curl -X POST http://localhost:8000/chat/route \
  -H "Content-Type: application/json" \
  -d '{"user_input":"我想做一道数学题"}'
```

### B. 环境变量最小配置

```env
SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxxx
LLM_MODEL=deepseek-ai/DeepSeek-V3
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
JWT_SECRET_KEY=dev-key-change-in-production
CORS_ORIGINS=["*"]
LOG_LEVEL=INFO
```

---

**文档生成时间**: 2025年4月11日
**项目版本**: 0.2.0
**作者**: Copilot (代码库全面分析)
