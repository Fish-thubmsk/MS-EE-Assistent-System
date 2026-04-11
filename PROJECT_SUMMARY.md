# 考研智能辅导系统 — 项目全面汇总文档

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈与依赖](#2-技术栈与依赖)
3. [目录结构](#3-目录结构)
4. [配置管理](#4-配置管理)
5. [数据库设计](#5-数据库设计)
6. [后端服务](#6-后端服务)
7. [智能 Agent 层](#7-智能-agent-层)
8. [知识库管理](#8-知识库管理)
9. [工具模块](#9-工具模块)
10. [前端页面](#10-前端页面)
11. [Docker 部署](#11-docker-部署)
12. [API 接口全览](#12-api-接口全览)
13. [数据流与系统调用链](#13-数据流与系统调用链)
14. [环境变量一览](#14-环境变量一览)
15. [测试体系](#15-测试体系)

---

## 1. 项目概述

本系统是一套面向考研学生的智能辅导平台，提供刷题批改、RAG 知识问答、学习诊断三大核心功能。

**系统名称**：考研智能辅导系统（MS-EE-Assistent-System）  
**API 版本**：0.2.0  
**核心框架**：FastAPI + LangGraph  
**向量检索**：FAISS（静态知识库）+ ChromaDB（动态用户笔记）  
**LLM 服务**：SiliconFlow OpenAI-compatible API（默认模型 deepseek-ai/DeepSeek-V3）  
**Embedding 服务**：SiliconFlow API（默认模型 BAAI/bge-m3，维度 1024）  

**三大核心模式**：

| 模式 | 说明 |
|------|------|
| quiz（刷题模式） | 随机抽题、提交答案、自动批改、详细解析、追问生成 |
| qa（问答模式） | 用户提问、FAISS + ChromaDB 混合检索、LLM 生成带引用的答案、SSE 流式输出 |
| diagnosis（诊断模式） | 分析做题历史、识别薄弱知识点、推荐相关题目和笔记、生成诊断报告 |

---

## 2. 技术栈与依赖

### 2.1 Python 依赖（requirements.txt）

| 包名 | 版本 | 用途 |
|------|------|------|
| fastapi | >=0.110.0 | Web 框架 |
| uvicorn[standard] | >=0.29.0 | ASGI 服务器 |
| python-multipart | >=0.0.9 | 文件上传支持 |
| langgraph | >=0.1.0 | Agent 状态机工作流 |
| langchain | >=0.2.0 | LLM 抽象层 |
| langchain-community | >=0.2.0 | 社区集成 |
| langchain-openai | >=0.1.0 | OpenAI 兼容 LLM 接口 |
| faiss-cpu | >=1.8.0 | FAISS 向量检索 |
| chromadb | >=0.5.0 | 向量数据库（持久化） |
| sqlalchemy | >=2.0.0 | ORM（userdata.db） |
| PyJWT | >=2.12.0 | JWT 令牌签发与验证 |
| bcrypt | >=4.0.0 | 密码哈希 |
| httpx | >=0.27.0 | 异步 HTTP 客户端 |
| requests | >=2.31.0 | 同步 HTTP 客户端 |
| python-dotenv | >=1.0.0 | 环境变量加载 |
| pydantic | >=2.0.0 | 数据校验 |
| pydantic-settings | >=2.0.0 | 配置管理 |
| pytest | >=8.0.0 | 测试框架 |
| pytest-asyncio | >=0.23.0 | 异步测试支持 |

### 2.2 外部服务依赖

| 服务 | 用途 | 必要性 |
|------|------|--------|
| SiliconFlow API | LLM 推理、Embedding 向量化 | 生产必需；开发可降级 |
| GitHub API | 新闻爬虫（可选功能） | 可选 |

---

## 3. 目录结构

```
MS-EE-Assistent-System/
├── .env.example                   # 环境变量配置示例
├── .gitignore
├── requirements.txt               # Python 依赖
├── LICENSE
│
├── backend/                       # FastAPI 后端服务
│   ├── __init__.py
│   ├── main.py                    # 应用入口、路由注册、启动事件
│   ├── config.py                  # pydantic-settings 全局配置
│   ├── dependencies.py            # JWT 认证依赖（get_current_user）
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py              # SQLAlchemy ORM 模型（User/QuizRecord/DiagnosisReport）
│   │   └── db_manager.py          # 引擎管理、表初始化、演示用户种子
│   └── routers/
│       ├── __init__.py
│       ├── auth.py                # 注册/登录/用户信息接口
│       ├── practice.py            # 刷题接口（取题/提交/SSE 流式）
│       ├── answer.py              # RAG 问答接口（同步/SSE 流式/mock）
│       ├── chat.py                # 意图识别与路由接口
│       ├── diagnosis.py           # 学习诊断接口
│       ├── notes.py               # ChromaDB 笔记管理接口
│       └── admin.py               # 管理接口（GitHub 新闻同步）
│
├── agents/                        # LangGraph 智能 Agent
│   ├── __init__.py
│   ├── router_agent.py            # 意图识别与三模式路由
│   ├── rag_agent.py               # RAG 检索增强生成问答
│   ├── quiz_agent.py              # 刷题批改（Teacher + Student）
│   └── diagnosis_agent.py         # 学习诊断（弱点分析 + 推荐）
│
├── knowledge_base/                # 知识库管理
│   ├── __init__.py
│   ├── chroma_manager.py          # ChromaDB 动态笔记库管理
│   ├── note_watcher.py            # 笔记目录增量监控与自动索引
│   ├── build_faiss_index.py       # FAISS 索引构建脚本（离线）
│   ├── search_demo.py             # FAISS 检索接口（供 Agent 调用）
│   ├── rag_demo.py                # RAG 端到端演示脚本
│   └── faiss_index/               # FAISS 索引文件目录（运行时生成）
│       ├── questions.index
│       └── id_map.json
│
├── datebase/                      # 数据库文件与构建脚本
│   ├── build_knowledge_base.py    # 题库数据库构建脚本（从 JSON 导入）
│   ├── knowledge_base.db          # 只读题库 SQLite（政治/数学/英语）
│   └── userdata.db                # 可读写用户数据 SQLite（运行时生成）
│
├── utils/                         # 通用工具模块
│   ├── __init__.py
│   ├── sf_retry.py                # SiliconFlow API 指数退避重试
│   └── github_news_spider.py      # GitHub 新闻爬虫
│
├── frontend/                      # 静态前端页面
│   ├── index.html                 # 主页面
│   ├── login.html                 # 登录页面
│   └── register.html              # 注册页面
│
├── mock_notes/                    # 模拟用户笔记（供开发测试）
│   ├── mock_user_history.json     # 模拟用户做题历史
│   ├── math_calculus_note.md
│   ├── math_derivative_wrong.md
│   ├── english_reading_note.md
│   ├── english_writing_wrong.md
│   ├── politics_materialism_note.md
│   ├── politics_history_wrong.md
│   └── github_news/               # 爬取的 GitHub 新闻（运行时填充）
│
├── docker/                        # Docker 部署配置
│   ├── Dockerfile                 # 后端镜像
│   ├── Dockerfile.frontend        # 前端镜像
│   ├── docker-compose.yml         # 多容器编排
│   └── nginx.conf                 # Nginx 反向代理配置
│
├── tests/                         # 测试套件
│   ├── conftest.py
│   ├── test_backend_routers.py
│   ├── test_chroma_manager.py
│   ├── test_diagnosis_agent.py
│   ├── test_faiss_index.py
│   ├── test_note_watcher.py
│   ├── test_quiz_agent.py
│   ├── test_rag_agent.py
│   ├── test_router_agent.py
│   └── test_sf_retry.py
│
└── 参考/                          # 原始参考数据（离线使用）
    └── JSON汇总/
        ├── quiz_app.py
        ├── script/                # 数据导入脚本
        ├── 政治/                  # 政治题库 JSON
        ├── 数学/                  # 数学题库 JSON
        └── 英语/                  # 英语题库 JSON
```

---

## 4. 配置管理

### 4.1 配置入口（backend/config.py）

通过 `pydantic-settings` 的 `BaseSettings` 从 `.env` 文件或环境变量加载配置。  
使用 `@lru_cache(maxsize=1)` 保证全局单例（`get_settings()`）。

若 `JWT_SECRET_KEY` 未配置，运行时生成随机临时密钥（重启后 Token 失效，仅用于开发）。

### 4.2 Settings 类字段分类

**SiliconFlow / LLM API**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| siliconflow_api_key | 空 | SiliconFlow API Key |
| llm_model | 无默认（必填） | LLM 模型名称（推荐 deepseek-ai/DeepSeek-V3） |
| llm_base_url | https://api.siliconflow.cn/v1 | LLM API 基础 URL |
| llm_temperature | 0.3 | 采样温度 |
| llm_max_tokens | 2048 | 最大生成 token 数 |
| llm_timeout | 60 | API 超时（秒） |

**速率限制与重试**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| sf_request_delay_seconds | 1.0 | 请求基础延迟（秒） |
| sf_max_retries | 3 | 最大重试次数 |
| sf_api_timeout | 60 | 请求超时（秒） |

**Embedding**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| embedding_model | Qwen/Qwen3-Embedding-8B | Embedding 模型 |
| embedding_base_url | https://api.siliconflow.cn/v1 | Embedding API URL |
| siliconflow_api_url | https://api.siliconflow.cn/v1/embeddings | 完整 Embedding URL |
| embedding_dim | 1024 | 向量维度（bge-m3=1024；Qwen3-Embedding-8B=4096） |

**ChromaDB**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| chroma_persist_directory | chroma_userdata | 持久化目录 |
| chroma_collection_name | user_notes | 集合名称 |

**FAISS**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| faiss_index_dir | knowledge_base/faiss_index | 索引目录 |

**JWT 认证**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| jwt_secret_key | 空（运行时生成） | JWT 签名密钥 |
| jwt_algorithm | HS256 | 签名算法 |
| jwt_expire_minutes | 1440（24小时） | Token 有效期 |

**FastAPI 服务**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| app_title | 考研智能辅导系统 API | 应用标题 |
| app_version | 0.2.0 | API 版本 |
| cors_origins | ["*"] | CORS 来源（生产环境收紧） |
| log_level | INFO | 日志级别 |

**RAG 与检索**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| default_n_faiss | 5 | FAISS 默认检索数量 |
| default_n_chroma | 3 | Chroma 默认检索数量 |
| max_history_messages | 6 | 对话历史保留条数 |
| stream_char_delay | 0.01 | SSE 字符延迟（秒） |
| mock_history_path | mock_notes/mock_user_history.json | Mock 历史数据路径 |
| batch_size | 32 | Embedding API 批处理大小 |
| retry_base_delay | 5.0 | 重试基础延迟（秒） |

**诊断 Agent**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| diagnosis_weak_threshold | 0.6 | 薄弱知识点准确率阈值 |
| diagnosis_recommend_per_point | 3 | 每个薄弱点推荐题目数 |

---

## 5. 数据库设计

### 5.1 knowledge_base.db（只读题库）

由 `datebase/build_knowledge_base.py` 从 `参考/JSON汇总/` 下的 JSON 文件构建。

**规范化七表设计：**

#### subjects — 数学科目表（3 条记录）

| 列名 | 类型 | 说明 |
|------|------|------|
| subject_code | TEXT PK | 科目代码（math1/math2/math3） |
| subject_name | TEXT | 科目名称 |

#### papers — 数学试卷表（121 条记录）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| subject_code | TEXT FK | 关联 subjects |
| paper_no | INTEGER | 试卷编号 |
| paper_title | TEXT | 试卷标题（含年份，如"2024数学一"） |

#### questions_math — 数学题目表（2868 条记录）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| paper_id | INTEGER FK | 关联 papers |
| question_no | INTEGER | 题目编号 |
| question_type | TEXT | 题型（single_choice/fill_blank/subjective） |
| stem | TEXT | 题干 |

#### questions_politics — 政治题目表（439 条记录）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| original_id | INTEGER | 原始数据 ID |
| year | INTEGER | 考试年份 |
| question_type | TEXT | 题型（单选题/多选题/材料分析题） |
| stem | TEXT | 题干 |
| correct_answer | TEXT | 参考答案 |
| analysis | TEXT | 解析 |
| difficulty | INTEGER | 难度 |
| score | REAL | 分值 |

#### questions_english — 英语文章/大题表（396 条记录）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| year | INTEGER | 考试年份 |
| question_number | INTEGER | 大题编号（1=完形，2-5=阅读，6=新题型，7=翻译，8=小作文，9=大作文） |
| question_type | TEXT | 题型（cloze/reading/new_type/translation/writing_small/writing_large） |
| content | TEXT | 文章正文或题目内容 |
| translation | TEXT | 翻译（可选） |

#### sub_questions — 统一小问表（4922 条记录）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| subject_type | TEXT | 学科（politics/english/math），CHECK 约束 |
| question_id | INTEGER | 对应大题 ID |
| question_number | INTEGER | 大题编号 |
| sub_question_number | INTEGER | 小题编号 |
| stem | TEXT | 小题题干 |
| answer | TEXT | 参考答案 |
| analysis | TEXT | 解析 |

索引：`idx_sq_subject`（subject_type），`idx_sq_question`（question_id）

#### options — 统一选项表（11930 条记录）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| subject_type | TEXT | 学科，CHECK 约束 |
| sub_question_id | INTEGER FK | 关联 sub_questions，级联删除 |
| option_key | TEXT | 选项键（A/B/C/D） |
| option_text | TEXT | 选项文本 |

唯一约束：(sub_question_id, option_key)；索引：`idx_opt_sub_q`

#### quiz_records — 做题记录表（6 条记录，来自旧版兼容）

| 列名 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | TEXT | 用户 ID |
| question_id | INTEGER | 题目 ID |
| subject | TEXT | 学科 |
| knowledge_point | TEXT | 知识点 |
| is_correct | INTEGER | 是否答对（0/1） |
| answered_at | TEXT | 作答时间 |

**数据汇总**：

| 表名 | 条数 |
|------|------|
| subjects | 3 |
| papers | 121 |
| questions_math | 2868 |
| questions_politics | 439 |
| questions_english | 396 |
| sub_questions | 4922 |
| options | 11930 |
| quiz_records | 6 |

---

### 5.2 userdata.db（可读写用户数据）

由 `backend/database/db_manager.py` 的 `init_db()` 在应用启动时自动创建，路径默认为 `datebase/userdata.db`，可通过 `USERDATA_DB_PATH` 环境变量覆盖。

采用 SQLAlchemy ORM，开启外键约束（`PRAGMA foreign_keys=ON`）。

#### users — 用户账号表

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增主键 |
| username | Text UNIQUE | 用户名（唯一） |
| password_hash | Text | bcrypt 哈希密码 |
| display_name | Text | 显示名称（可选） |
| email | Text | 邮箱（可选） |
| created_at | DateTime | 创建时间（server_default） |
| last_login | DateTime | 最后登录时间（可选） |

关系：一对多关联 quiz_records 和 diagnosis_reports（级联删除）

#### quiz_records — 答题记录表

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增主键 |
| user_id | Integer FK | 关联 users（SET NULL on delete） |
| user_id_str | Text | 字符串形式用户 ID（兼容匿名用户） |
| question_id | Integer | 题目 ID |
| subject | Text | 学科 |
| year | Integer | 年份 |
| knowledge_point | Text | 知识点 |
| is_correct | Boolean | 是否答对 |
| score | Float | 得分（0-100） |
| user_answer | Text | 用户答案 |
| feedback | Text | 批改反馈 |
| created_at | DateTime | 创建时间 |

#### diagnosis_reports — 诊断报告表

| 列名 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 自增主键 |
| user_id | Integer FK | 关联 users（SET NULL on delete） |
| user_id_str | Text | 字符串形式用户 ID |
| report_date | DateTime | 报告日期 |
| analysis_result | Text | JSON 格式完整分析结果 |
| created_at | DateTime | 创建时间 |

#### 演示用户种子数据

启动时自动插入三个演示账号（若不存在）：

| 用户名 | 密码 | 显示名称 |
|--------|------|----------|
| user_001 | exam2024 | 同学甲 |
| user_002 | exam2024 | 同学乙 |
| user_003 | exam2024 | 同学丙 |

---

## 6. 后端服务

### 6.1 应用入口（backend/main.py）

**FastAPI 应用配置**：

- 标题：考研智能辅导系统 API
- docs_url：/docs（Swagger UI）
- redoc_url：/redoc
- openapi_url：/openapi.json

**CORS 中间件**：`CORSMiddleware`，默认允许所有来源（`["*"]`），生产环境须收紧。

**路由注册顺序**：

1. `auth_router`（/api/auth）
2. `notes_router`（/notes）
3. `chat_router`（/chat）
4. `diagnosis_router`（/diagnosis）
5. `answer_router`（/api/answer）
6. `practice_router`（/api/practice）
7. `admin_router`（/api/admin，ImportError 时跳过）

**启动事件（startup）**：

1. 在后台守护线程中启动 `note_watcher.watch()`，持续监控 `mock_notes/` 目录，增量同步到 ChromaDB。
2. 在后台守护线程中执行 `GitHubNewsSpider.download_all_news(resume=True)`，同步当年 GitHub 新闻（非阻塞）。

**健康检查端点**：

- `GET /` — 返回 `{"status": "ok"}`
- `GET /health` — 返回 `{"status": "ok", "version": "0.2.0"}`

---

### 6.2 JWT 认证（backend/dependencies.py）

`get_current_user(credentials, settings) -> int`：从 `Authorization: Bearer <token>` 头中提取并验证 JWT，返回 `user_id`（int）。

错误处理：

| 情形 | HTTP 状态码 | 错误信息 |
|------|-------------|---------|
| credentials 为 None | 401 | 未提供认证 Token |
| Token 已过期 | 401 | Token 已过期，请重新登录 |
| Token 签名无效 | 401 | 无效的认证 Token |
| sub 字段缺失 | 401 | Token 载荷缺少 sub 字段 |
| sub 字段格式错误 | 401 | Token 载荷 sub 字段格式错误 |

---

### 6.3 认证路由（backend/routers/auth.py）

前缀：`/api/auth`，标签：auth

#### POST /api/auth/register

请求体：`RegisterRequest`

| 字段 | 类型 | 说明 |
|------|------|------|
| username | str | 用户名，3-50 字符 |
| password | str | 密码，至少 6 位 |
| display_name | str（可选） | 昵称，最长 100 字符 |
| email | str（可选） | 邮箱 |

流程：检查用户名是否重复 → bcrypt 哈希密码 → 写入 users 表 → 签发 JWT

响应：`TokenResponse`（access_token + user_id + username + display_name）

HTTP 状态码：201（成功），409（用户名已存在）

#### POST /api/auth/login

请求体：`LoginRequest`（username + password）

流程：查询用户 → bcrypt 验证密码 → 更新 last_login → 签发 JWT

响应：`TokenResponse`

HTTP 状态码：200（成功），401（用户名或密码错误）

#### GET /api/auth/me

需要 Bearer Token。

响应：`UserInfo`（user_id + username + display_name + email + created_at）

---

### 6.4 刷题路由（backend/routers/practice.py）

前缀：`/api/practice`，标签：practice

**学科配置**：

| 学科 ID | 学科名 |
|---------|--------|
| politics | 政治 |
| math | 数学 |
| english | 英语 |

**政治题型**：单选题、多选题、材料分析题  
**数学题型**：single_choice（单选题）、fill_blank（填空题）、subjective（解答题）  
**英语题型**：cloze（完形填空）、reading（阅读理解）、new_type（新题型）、translation（翻译）、writing_small（小作文）、writing_large（大作文）

**英语大题与 question_number 对应关系**：

| 题型 ID | question_number 范围 |
|---------|----------------------|
| cloze | 1 |
| reading | 2–5 |
| new_type | 6 |
| translation | 7 |
| writing_small | 8 |
| writing_large | 9 |

#### GET /api/practice/subjects

返回科目列表（id + name + icon）。

#### GET /api/practice/types/{subject}

返回指定科目的题型列表。

#### GET /api/practice/years/{subject}

返回该科目在数据库中有数据的年份列表。

#### GET /api/practice/question

查询参数：`subject`（必填）、`question_type`（可选）、`year`（可选）

从 knowledge_base.db 随机抽取一道题。不同学科分别调用 `_fetch_politics_question`、`_fetch_math_question`、`_fetch_english_question`。

若数据库不存在，降级为 `MOCK_MATH_QUESTIONS`。

响应：`QuestionOut`

| 字段 | 说明 |
|------|------|
| id | 题目 ID |
| subject | 学科 |
| year | 年份 |
| question_type | 题型 |
| content | 题目内容 |
| options | 选项字典（A/B/C/D），可选 |
| correct_answer | 正确答案，可选 |
| analysis | 解析，可选 |
| passage_text | 英语阅读原文，可选 |
| knowledge_points | 知识点列表 |
| sub_questions | 材料分析题小问列表 |

#### POST /api/practice

提交答案，获取批改结果与解析。

请求体：`PracticeRequest`（user_id + user_input + current_question + messages 等）

流程：调用 `run_quiz()` → 保存做题记录到 userdata.db（`_save_quiz_record`）

响应：`PracticeResponse`（grade_result + explanation + followup_questions + messages + quiz_history）

**做题记录写入 userdata.db 字段**：user_id_str、question_id、subject、year、knowledge_point、is_correct、score、user_answer、feedback、created_at

#### POST /api/practice/stream

SSE 流式返回解析内容。逐字符以 `event: token` 事件流式发送，结束时发送 `event: done`。

---

### 6.5 RAG 问答路由（backend/routers/answer.py）

前缀：`/api/answer`，标签：answer

ChromaDB 依赖通过 `get_optional_chroma_manager()` 注入，初始化失败时静默返回 None（答案接口降级跳过 Chroma 检索）。

请求体：`AnswerRequest`

| 字段 | 默认值 | 说明 |
|------|--------|------|
| user_input | 必填 | 用户问题 |
| messages | [] | 历史消息 |
| params | {} | 路由参数 |
| use_faiss | True | 是否检索 FAISS |
| use_chroma | False | 是否检索 Chroma |
| n_faiss_results | 5 | FAISS 检索数量（1-20） |
| n_chroma_results | 3 | Chroma 检索数量（1-10） |
| chroma_filter | None | Chroma 元数据过滤 |

#### POST /api/answer

同步 RAG 问答。调用 `run_rag()`，在 executor 中运行（非阻塞）。

若 `SILICONFLOW_API_KEY` 未配置，返回基于检索结果的模板答案。

响应：`AnswerResponse`（answer + citations + recommendations + messages）

#### POST /api/answer/stream

SSE 流式问答。

流程：
1. 调用 `run_rag()`（api_key="" 跳过 LLM 生成，只做检索）
2. 构建含 RAG 上下文的完整 prompt（可选拼接历史消息）
3. 调用 `_stream_siliconflow()` 流式调用 LLM

若 `SILICONFLOW_API_KEY` 未配置，返回 `_stream_mock()` 演示内容。

SSE 事件序列：

| 事件名 | 数据格式 | 说明 |
|--------|---------|------|
| metadata | {"citations": [...], "recommendations": [...]} | 首个事件，包含引用与推荐 |
| token | {"token": "..."} | 逐 token 发送 |
| done | {"status": "done"} | 生成完毕 |
| error | {"error": "..."} | 发生错误 |

#### GET /api/answer/mock

无需配置，使用 mock 问题"什么是极限？"演示完整 RAG 问答流程。

---

### 6.6 意图识别路由（backend/routers/chat.py）

前缀：`/chat`，标签：chat

#### POST /chat/route

接收用户输入，调用 `run_router()` 识别意图。

请求体：`RouteRequest`

| 字段 | 说明 |
|------|------|
| user_input | 当前用户输入文本 |
| messages | 历史消息列表 |
| session_history | 历史会话模式记录 |
| multimodal_attachments | 多模态附件（预留） |

响应：`RouteResponse`

| 字段 | 说明 |
|------|------|
| mode | 识别到的主模式（quiz/qa/diagnosis/unknown） |
| sub_mode | 子模式 |
| params | 提取的参数（subject/difficulty/year/knowledge_point） |
| intent_confidence | 意图置信度（0.0–1.0） |
| messages | 更新后的消息列表 |
| session_history | 更新后的会话历史 |
| mode_description | 模式说明文字 |

---

### 6.7 学习诊断路由（backend/routers/diagnosis.py）

前缀：`/diagnosis`，标签：diagnosis

#### POST /diagnosis/run

请求体：`DiagnosisRequest`

| 字段 | 默认值 | 说明 |
|------|--------|------|
| user_id | user_001 | 用户 ID |
| subject | None | 可选限定学科 |
| history_records | [] | 做题历史（空则从 DB 或 mock 读取） |
| weak_threshold | 0.6 | 薄弱点准确率阈值 |
| recommend_per_point | 3 | 每薄弱点推荐题目数 |

流程：调用 `run_diagnosis()`

响应：`DiagnosisResponse`（user_id + subject + weak_points + recommended_questions + recommended_notes + report）

#### GET /diagnosis/mock

使用内置 mock 数据（user_001）体验诊断流程，无需参数。

---

### 6.8 笔记管理路由（backend/routers/notes.py）

前缀：`/notes`，标签：notes

`ChromaManager` 通过 `lru_cache` 单例工厂 `_get_manager()` 提供，使用应用全局配置（collection_name、persist_dir、api_key、embedding_model、api_url）。

#### POST /notes/

新增或更新笔记。接受 `NoteRequest`（content + doc_id + metadata），调用 `manager.add_note()`。

#### POST /notes/file

从 `.md` 文件路径读取并存入 ChromaDB。接受 `NoteFileRequest`（file_path），调用 `manager.add_note_from_file()`。

#### DELETE /notes/{doc_id}

删除指定 doc_id 的笔记。

#### GET /notes/query

向量相似度检索。参数：`q`（查询文本）、`n`（返回数量，1-50）、`subject`（学科过滤）、`type`（类型过滤：note/wrong）。

#### GET /notes/count

返回 ChromaDB 集合中的笔记总数。

---

### 6.9 管理路由（backend/routers/admin.py）

前缀：`/api/admin`，标签：admin

#### POST /api/admin/sync-github-news

手动触发 GitHub 新闻同步（本年度增量下载）。

响应：`{"status": "success", "message": "...", "data": {...}}`

#### GET /api/admin/sync-github-news/status

读取本地下载统计文件 `mock_notes/github_news/download_stats.json`。

---

## 7. 智能 Agent 层

所有 Agent 均基于 LangGraph `StateGraph` 构建，通过节点函数链式处理状态，支持 LLM 增强和规则降级两种模式。

---

### 7.1 Router Agent（agents/router_agent.py）

**职责**：识别用户输入的意图，路由到 quiz / qa / diagnosis / unknown 四种模式。

#### 核心枚举

**主模式（Mode）**：

| 值 | 说明 |
|----|------|
| quiz | 刷题模式 |
| qa | 问答模式 |
| diagnosis | 诊断模式 |
| unknown | 未识别 |

**刷题子模式（QuizSubMode）**：follow_up（追问）、grading（批改）、explanation（讲解，默认）  
**问答子模式（QASubMode）**：knowledge（知识点，默认）、concept（概念）、with_notes（融合笔记）  
**诊断子模式（DiagnosisSubMode）**：trajectory（学习轨迹，默认）、weak_analysis（弱项分析）

#### 关键词规则库

| 正则 | 匹配模式 |
|------|---------|
| `_QUIZ_KEYWORDS` | 做题/刷题/批改/解析/追问/下一题 等 |
| `_QA_KEYWORDS` | 什么是/解释一下/如何/笔记/知识点/总结 等 |
| `_DIAGNOSIS_KEYWORDS` | 诊断/薄弱/弱项/学情/提升建议 等 |

#### 参数提取

| 参数 | 正则示例 |
|------|---------|
| subject | 数学/英语/政治/专业课/物理等 |
| difficulty | 简单/中等/困难/高难度等 |
| year | 20XX/19XX年 |
| knowledge_point | 关于/有关/考察 后的 2-15 字内容 |

#### LangGraph 工作流

```
START
  -> recognize_intent（关键词 + 可选 LLM 识别，更新 mode/sub_mode/params/confidence）
  -> [条件路由]
     -> quiz     -> END
     -> qa       -> END
     -> diagnosis -> END
     -> unknown  -> END
```

Quiz 模式节点为真实的 `create_quiz_node()`；其余模式为占位节点（待后续替换）。

#### RouterState 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| messages | list[dict] | 对话历史 |
| raw_input | str | 当前用户输入 |
| mode | str | 当前主模式 |
| sub_mode | str | 当前子模式 |
| params | RouterParams | 提取的参数 |
| intent_confidence | float | 意图置信度 |
| session_history | list[dict] | 历史轮次快照 |
| multimodal_attachments | list[dict] | 多模态附件（预留） |

---

### 7.2 RAG Agent（agents/rag_agent.py）

**职责**：检索增强生成，回答用户知识问答。

#### LangGraph 工作流

```
START
  -> retrieve_faiss（FAISS 向量检索，可按 use_faiss 跳过）
  -> retrieve_chroma（Chroma 检索，可按 use_chroma 和 chroma_manager 跳过）
  -> fuse_results（融合去重，最多 5 条引用 + 3 条推荐）
  -> generate_answer（LLM 生成答案，三级降级）
  -> END
```

#### RAGState 关键字段

| 字段 | 说明 |
|------|------|
| use_faiss / use_chroma | 检索开关 |
| n_faiss_results / n_chroma_results | 检索数量 |
| chroma_filter | Chroma 元数据过滤（如 {"subject": "数学"}） |
| faiss_results / chroma_results | 各自检索结果 |
| fused_context | 融合后的上下文（含 citation_index） |
| answer | LLM 生成的答案 |
| citations | 答案引用列表（最多 5 条） |
| recommendations | 相似推荐列表（最多 3 条） |

#### 答案生成三级降级策略

1. LangChain LLM 实例（若提供）
2. SiliconFlow API 直接调用（若 api_key 已配置）
3. 基于检索结果的模板答案（始终可用）

#### 结果融合策略（fuse_results）

- FAISS 结果优先（按 score 降序）
- 基于内容前 100 字符去重
- 引用最多保留 5 条（分配 citation_index 1–5）
- 推荐从未被引用的 FAISS 结果中取，最多 3 条

#### LLM 调用接口

`_call_siliconflow_llm(prompt, api_key, model, base_url, timeout, temperature, max_tokens)`：
- 调用 SiliconFlow `/chat/completions` 端点
- 底层使用 `call_with_retry()` 指数退避重试

#### Prompt 模板

```
你是一个专业的学习助手，请根据以下检索到的参考资料，为用户的问题提供清晰、准确的答案。

参考资料：
[1] (知识库题目 | 学科 | 年份)
内容...

[2] (个人笔记/错题 | ...)
内容...

用户问题：{question}

要求：
1. 答案中需引用参考资料，用 [序号] 标注
2. 若参考资料中有题目，可附上正确答案
3. 如有相关知识点，可适当补充说明
4. 支持中英文混合回答
5. 若参考资料不足以回答，请说明并给出基于已有知识的回答

答案：
```

---

### 7.3 Quiz Agent（agents/quiz_agent.py）

**职责**：刷题批改（Teacher Agent）+ 追问生成（Student Agent）。

#### QuizState 专属字段

| 字段 | 说明 |
|------|------|
| current_question | 当前题目（content/correct_answer/analysis/knowledge_points） |
| user_answer | 用户答案 |
| grade_result | 判题结果（is_correct/score/feedback） |
| explanation | 详细解析 |
| followup_questions | 追问列表 |
| quiz_history | 多轮刷题历史 |
| knowledge_context | FAISS 检索结果 |
| dynamic_context | Chroma 检索结果 |

#### LangGraph 工作流

```
START
  -> retrieve_context（Teacher：FAISS + Chroma 检索，可选，各取 top_k=3）
  -> grade_answer（Teacher：判题批改）
  -> explain（Teacher：详细解析，写入 messages 和 quiz_history）
  -> student_followup（Student：追问生成）
  -> END
```

#### Teacher Agent 批改逻辑

**规则批改（_rule_grade）**：

| 判断条件 | 结果 |
|---------|------|
| 答案为空 | is_correct=False, score=0 |
| 无参考答案 | is_correct=None, score=None |
| 精确匹配 | is_correct=True, score=100 |
| 大小写不敏感匹配 | is_correct=True, score=100 |
| 参考答案被包含 | is_correct=True, score=90 |
| 关键词重叠 ≥50% | is_correct=False, score=重叠率×80 |
| 其他 | is_correct=False, score=0 |

**LLM 批改（_llm_grade）**：输出 JSON `{"is_correct": bool, "score": 0-100, "feedback": "..."}`，支持 Markdown 代码块和 raw_decode 三种 JSON 提取策略。

#### Student Agent 追问生成

**规则追问（_rule_followup）**：

| 条件 | 追问模板 |
|------|---------|
| 答错或分数 <60 | 核心概念是什么？再出一道练习题？完整解题步骤？ |
| 答对 | 有其他解法？能出综合题？有哪些易错题型？ |
| 其他 | 知识点不理解？与哪些知识点相关？ |

#### Mock 数据

`MOCK_MATH_QUESTIONS`：3 道数学题（极限、导数、定积分），含完整解析和知识点标注，用于数据库不可用时的降级。

---

### 7.4 Diagnosis Agent（agents/diagnosis_agent.py）

**职责**：分析做题历史，识别薄弱知识点，生成推荐和诊断报告。

#### LangGraph 工作流

```
START
  -> load_history（优先从 userdata.db quiz_records 表读取真实记录；无数据时 fallback 到 mock JSON）
  -> analyze_weak_points（统计各知识点准确率，评定薄弱点和优先级）
  -> recommend_resources（从 knowledge_base.db 题库 + Chroma 笔记推荐）
  -> generate_report（生成结构化文本诊断报告）
  -> END
```

#### DiagnosisState 关键字段

| 字段 | 说明 |
|------|------|
| user_id | 用户 ID |
| subject | 可选学科过滤 |
| history_records | 做题历史列表 |
| knowledge_stats | 知识点统计字典（key="subject::知识点"） |
| weak_points | 薄弱知识点列表（按准确率升序） |
| recommended_questions | 推荐题目列表 |
| recommended_notes | 推荐笔记/错题列表 |
| report | 完整诊断报告文本 |

#### KnowledgePointStat 结构

| 字段 | 说明 |
|------|------|
| total | 总作答次数 |
| correct | 正确次数 |
| accuracy | 准确率（0.0–1.0，保留 4 位小数） |

#### WeakPoint 结构

| 字段 | 说明 |
|------|------|
| knowledge_point | 知识点名称 |
| subject | 所属学科 |
| accuracy | 准确率 |
| total_attempts | 总作答次数 |
| priority | 优先级（准确率<0.4为高，0.4-阈值为中） |

#### 历史记录加载策略

1. 优先从 `userdata.db` 的 `quiz_records` 表读取（通过 `user_id_str` 过滤）
2. DB 不存在或无记录时，从 `mock_notes/mock_user_history.json` 读取 mock 数据
3. 若传入 `history_records` 参数，直接使用

#### 题目推荐查询

按学科分别查询 `knowledge_base.db`：

- 政治：从 `questions_politics` 按 stem LIKE 匹配知识点关键词
- 数学：从 `questions_math` 按 stem LIKE 匹配
- 英语：从 `questions_english` 按 content LIKE 匹配

每个薄弱点随机推荐 `RECOMMEND_PER_POINT`（默认 3）道题。

#### 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| DIAGNOSIS_WEAK_THRESHOLD | 0.6 | 薄弱点准确率阈值 |
| DIAGNOSIS_RECOMMEND_PER_POINT | 3 | 每薄弱点推荐题目数 |
| KNOWLEDGE_DB_PATH | datebase/knowledge_base.db | 题库路径 |
| USERDATA_DB_PATH | datebase/userdata.db | 用户数据路径 |
| MOCK_HISTORY_PATH | mock_notes/mock_user_history.json | Mock 历史路径 |

---

## 8. 知识库管理

### 8.1 ChromaDB 管理器（knowledge_base/chroma_manager.py）

**功能**：管理动态用户笔记的向量化存储与检索，通过 SiliconFlow Embedding API 进行文本向量化。

#### ChromaManager 类

**初始化参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| collection_name | user_notes | ChromaDB 集合名称 |
| persist_dir | chroma_userdata/ | 持久化目录 |
| api_key | 环境变量 SILICONFLOW_API_KEY | SiliconFlow API Key |
| embedding_fn | None（使用内置 get_embedding） | 自定义 Embedding 函数（测试用） |
| embedding_model | BAAI/bge-m3 | Embedding 模型 |
| api_url | https://api.siliconflow.cn/v1/embeddings | Embedding API URL |

ChromaDB 使用余弦相似度空间（`hnsw:space: cosine`），不使用内置 embedding 函数（全部通过 SiliconFlow 显式计算）。

#### 公开方法

**add_note(content, doc_id, metadata) -> str**：
1. 解析 Markdown YAML frontmatter（`---\n key: value\n---`）
2. 合并 frontmatter 元数据与传入 metadata
3. 将所有元数据值转换为字符串（ChromaDB 要求）
4. 若 doc_id 为 None，以 content MD5 生成
5. 调用 `get_embedding()` 向量化正文
6. 调用 `collection.upsert()` 存入 ChromaDB

**add_note_from_file(file_path) -> str**：读取 .md 文件后调用 `add_note()`，doc_id 使用文件绝对路径的 MD5。

**delete_note(doc_id)**：调用 `collection.delete(ids=[doc_id])`。

**delete_note_by_file(file_path)**：根据文件路径计算 doc_id 后删除。

**query(query_text, n_results, where) -> list[dict]**：
- 向量化查询文本
- 调用 `collection.query()`
- 返回 `[{id, document, metadata, distance}]`（cosine distance）
- 实际 n_results 不超过集合中的文档总数

**count() -> int**：返回集合文档总数。

**doc_exists(doc_id) -> bool**：检查指定 doc_id 是否存在。

**doc_id_from_path(file_path) -> str**：公开的路径转 doc_id 辅助方法。

#### Embedding 函数（get_embedding）

调用 `SiliconFlow Embedding API`（POST /v1/embeddings），底层使用 `call_with_retry()` 进行指数退避重试。返回浮点向量列表。

---

### 8.2 笔记监控（knowledge_base/note_watcher.py）

**功能**：持续监控指定目录中的 `.md` 文件，增量同步到 ChromaDB。

**状态持久化**：`chroma_userdata/.watcher_state.json`

状态格式：`{"/absolute/path/to/file.md": {"mtime": 时间戳, "doc_id": "..."}}`

支持旧格式迁移（值为 float 时自动转换为新格式）。

#### scan_and_update 函数

1. 收集目录中所有 `.md` 文件的绝对路径
2. 检测已删除文件（在状态中但不在目录中），删除对应 ChromaDB 索引
3. 遍历当前文件，若 mtime 变更则重新向量化并写入 ChromaDB
4. 清理孤立记录（状态有记录但 ChromaDB 中已不存在的 doc_id）

#### watch 函数

- `notes_dir`：监控目录（默认 NOTES_WATCH_DIR 环境变量，回退 mock_notes/）
- `persist_dir`：ChromaDB 目录（默认 CHROMA_PERSIST_DIRECTORY，回退 chroma_userdata/）
- `once`：True 时扫描一次后退出

扫描间隔由 `WATCHER_SCAN_INTERVAL` 环境变量控制（默认 5 秒）。

**CLI 入口**：

```
python knowledge_base/note_watcher.py [--notes-dir mock_notes] [--persist-dir chroma_userdata] [--once]
```

---

### 8.3 FAISS 索引构建（knowledge_base/build_faiss_index.py）

**功能**：从 `knowledge_base.db` 的题库表提取文本，向量化后构建 FAISS 索引（离线脚本，非运行时逻辑）。

**支持的数据表**：

| 表名 | 文本列 | doc_id 前缀 |
|------|--------|-------------|
| questions_math | stem | qm |
| questions_politics | stem | qp |
| questions_english | content | qe |
| sub_questions | stem | sq |

**学科过滤**：`--subject 政治/数学/英语`（可只索引单一学科）

**FAISS 索引类型**：`IndexFlatIP`（内积搜索）+ L2 归一化向量 = 余弦相似度搜索

**增量构建**：已在 `id_map.json` 中的 doc_id 跳过，每批次处理后保存检查点。

**输出文件**：

- `knowledge_base/faiss_index/questions.index`：FAISS 索引文件
- `knowledge_base/faiss_index/id_map.json`：`[{"doc_id": "qm_1", "source_table": "questions_math"}, ...]`

**使用方法**：

```
python knowledge_base/build_faiss_index.py [--subject 政治] [--batch-size 32]
```

**环境变量**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| SILICONFLOW_API_KEY | 必填 | API Key |
| KNOWLEDGE_DB_PATH | datebase/knowledge_base.db | 题库路径 |
| FAISS_INDEX_DIR | knowledge_base/faiss_index | 索引输出目录 |
| EMBEDDING_MODEL | BAAI/bge-m3 | Embedding 模型 |
| EMBEDDING_DIM | 1024 | 向量维度 |
| BATCH_SIZE | 32 | 批处理大小 |
| SF_MAX_RETRIES | 3 | 最大重试次数 |
| RETRY_BASE_DELAY | 5.0 | 重试基础延迟（秒） |

---

## 9. 工具模块

### 9.1 SiliconFlow 重试工具（utils/sf_retry.py）

#### call_with_retry(fn, max_retries, delay) -> httpx.Response

对 HTTP 调用进行指数退避重试，统一处理 429（速率限制）和超时错误。

**重试流程**：

1. 首次调用前等待 `delay` 秒
2. 遇到 HTTP 429 → 按 `delay × 2^attempt` 退避后重试
3. 遇到 `httpx.TimeoutException` → 同上退避重试
4. 其他 HTTP 错误 → 立即抛出，不重试
5. 达到 `max_retries` 次后仍失败 → 抛出最后的异常

**配置参数**：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| SF_MAX_RETRIES | 3 | 最大重试次数 |
| SF_REQUEST_DELAY_SECONDS | 1.0 | 基础延迟（秒） |
| SF_API_TIMEOUT | 30 | API 超时（秒） |

`get_sf_timeout()` 函数：从 `SF_API_TIMEOUT` 读取超时时间。

---

### 9.2 GitHub 新闻爬虫（utils/github_news_spider.py）

**功能**：爬取指定 GitHub 仓库中的新闻 Markdown 文件，仅下载当年 1 月 1 日至今的文件，支持断点续传。

**默认目标仓库**：DuckBurnIncense/xin-wen-lian-bo，master 分支，news/ 目录

**本地保存目录**：`mock_notes/github_news/`（会被 note_watcher 自动索引）

#### GitHubNewsSpider 类

**主要配置**（均可通过环境变量覆盖）：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| GITHUB_NEWS_OWNER | DuckBurnIncense | 仓库 owner |
| GITHUB_NEWS_REPO | xin-wen-lian-bo | 仓库名 |
| GITHUB_NEWS_BRANCH | master | 分支 |
| GITHUB_NEWS_DIR | news | 远程目录 |
| GITHUB_NEWS_LOCAL_DIR | mock_notes/github_news | 本地目录 |
| GITHUB_TOKEN | 空 | GitHub Token（提高 API 限额） |
| GITHUB_SPIDER_MAX_RETRIES | 3 | 下载重试次数 |
| GITHUB_SPIDER_RETRY_DELAY | 1.0 | 重试基础延迟 |
| GITHUB_SPIDER_DOWNLOAD_TIMEOUT | 15 | 下载超时（秒） |
| GITHUB_SPIDER_RATE_LIMIT_DELAY | 0.5 | 下载速率限制延迟 |

#### 文件列表获取策略

**主方案**：从 README.md 中解析文件链接（正则：`\[(\d{8})\]\(./news/(\d{8})\.md\)`）。

**备用方案**（主方案失败时）：调用 GitHub API `/repos/{owner}/{repo}/contents/{dir}` 分页获取（每页 100 条）。

只处理 `YYYYMMDD.md` 格式文件，日期范围：当年 1 月 1 日至今天。

#### download_all_news(resume=True) -> dict

返回结果：`{"total": 总数, "success": 成功数, "failed": 失败数, "skipped": 跳过数, "files": [文件名列表], "timestamp": ISO 时间戳}`

下载完成后将统计信息保存至 `mock_notes/github_news/download_stats.json`。

下载使用指数退避重试（`_download_with_retry`），每次成功下载后按 `rate_limit_delay` 延迟。

---

## 10. 前端页面

### 10.1 页面文件

| 文件 | 说明 |
|------|------|
| frontend/index.html | 主页面（刷题/问答/诊断主界面） |
| frontend/login.html | 用户登录页面 |
| frontend/register.html | 用户注册页面 |

前端为静态 HTML，由 Nginx 提供服务（Docker 部署时），直接调用后端 API。

---

## 11. Docker 部署

### 11.1 文件说明

| 文件 | 说明 |
|------|------|
| docker/Dockerfile | 后端镜像（Python FastAPI） |
| docker/Dockerfile.frontend | 前端镜像（Nginx 静态文件服务） |
| docker/docker-compose.yml | 多容器编排 |
| docker/nginx.conf | Nginx 反向代理配置 |

### 11.2 部署方式

**容器架构**：

- `backend` 容器：FastAPI 服务（Uvicorn，8000 端口）
- `frontend` 容器：Nginx 静态文件服务，同时反向代理 API 请求到后端

**启动命令**：

```
cd docker
docker-compose up -d
```

**生产环境注意事项**：

- `JWT_SECRET_KEY` 必须配置为强随机字符串（建议 `openssl rand -hex 32`）
- `CORS_ORIGINS` 须收紧为实际前端域名
- `SILICONFLOW_API_KEY` 通过 `.env` 或 Docker secrets 注入
- `LLM_MODEL` 必须显式配置

---

## 12. API 接口全览

### 12.1 接口汇总

| 方法 | 路径 | 说明 | 需要认证 |
|------|------|------|---------|
| GET | / | 健康检查 | 否 |
| GET | /health | 健康检查（含版本） | 否 |
| GET | /docs | Swagger UI | 否 |
| GET | /redoc | ReDoc UI | 否 |
| POST | /api/auth/register | 用户注册 | 否 |
| POST | /api/auth/login | 用户登录 | 否 |
| GET | /api/auth/me | 当前用户信息 | 是 |
| GET | /api/practice/subjects | 科目列表 | 否 |
| GET | /api/practice/types/{subject} | 科目题型列表 | 否 |
| GET | /api/practice/years/{subject} | 科目年份列表 | 否 |
| GET | /api/practice/question | 随机抽题 | 否 |
| POST | /api/practice | 提交答案批改 | 否 |
| POST | /api/practice/stream | SSE 流式批改解析 | 否 |
| POST | /api/answer | RAG 同步问答 | 否 |
| POST | /api/answer/stream | RAG SSE 流式问答 | 否 |
| GET | /api/answer/mock | Mock 问答演示 | 否 |
| POST | /chat/route | 意图识别与路由 | 否 |
| POST | /diagnosis/run | 运行学习诊断 | 否 |
| GET | /diagnosis/mock | Mock 诊断演示 | 否 |
| POST | /notes/ | 新增或更新笔记 | 否 |
| POST | /notes/file | 从文件导入笔记 | 否 |
| DELETE | /notes/{doc_id} | 删除笔记 | 否 |
| GET | /notes/query | 向量检索笔记 | 否 |
| GET | /notes/count | 笔记总数 | 否 |
| POST | /api/admin/sync-github-news | 手动同步新闻 | 否 |
| GET | /api/admin/sync-github-news/status | 查看同步状态 | 否 |

---

## 13. 数据流与系统调用链

### 13.1 刷题模式（quiz）调用链

```
用户请求 POST /api/practice/question
  -> practice.py: _fetch_politics/math/english_question()
  -> knowledge_base.db: RANDOM() 查询
  <- 返回 QuestionOut

用户提交 POST /api/practice
  -> practice.py
  -> agents/quiz_agent.py: run_quiz()
     -> create_quiz_graph().invoke()
        -> TeacherAgent.retrieve_context()
           -> FAISS search_demo.search() [可选]
           -> ChromaManager.query() [可选]
        -> TeacherAgent.grade_answer()
           -> LLM 批改 [可选] / 规则批改
        -> TeacherAgent.explain()
           -> LLM 解析 [可选] / 规则解析
        -> StudentAgent.generate_followup()
           -> LLM 追问 [可选] / 规则追问
  -> _save_quiz_record() -> userdata.db
  <- 返回 PracticeResponse
```

### 13.2 RAG 问答模式（qa）调用链

```
用户请求 POST /api/answer
  -> answer.py
  -> agents/rag_agent.py: run_rag()
     -> create_rag_graph().invoke()
        -> RAGAgent.retrieve_faiss()
           -> knowledge_base/search_demo.search()
              -> faiss_index/questions.index 向量检索
              <- list[{id, subject, year, question_type, content, score}]
        -> RAGAgent.retrieve_chroma()
           -> ChromaManager.query()
              -> SiliconFlow Embedding API 向量化查询
              -> ChromaDB 余弦相似度检索
              <- list[{id, document, metadata, distance}]
        -> RAGAgent.fuse_results()
           -> 归一化格式 -> 按 score 降序 -> 去重 -> 分配 citation_index
        -> RAGAgent.generate_answer()
           -> _call_siliconflow_llm() / _call_langchain_llm()
              -> SiliconFlow /chat/completions API
  <- 返回 AnswerResponse (answer + citations + recommendations + messages)
```

### 13.3 学习诊断模式调用链

```
用户请求 POST /diagnosis/run
  -> diagnosis.py
  -> agents/diagnosis_agent.py: run_diagnosis()
     -> DiagnosisGraph.invoke()
        -> load_history()
           -> _load_db_history() 从 userdata.db quiz_records 读取
           -> 若无数据: _load_mock_history() 从 mock JSON 读取
        -> analyze_weak_points()
           -> _compute_knowledge_stats() 统计准确率
           -> _identify_weak_points() 按阈值筛选薄弱点
        -> recommend_resources()
           -> _query_questions_by_knowledge_point() 从 knowledge_base.db 检索
           -> ChromaManager.query() 检索相关笔记 [可选]
        -> generate_report()
           -> 生成结构化文本报告
  <- 返回 DiagnosisResponse
```

### 13.4 笔记自动索引链

```
应用启动 (startup_event)
  -> threading.Thread(_start_note_watcher, daemon=True)
     -> note_watcher.watch(notes_dir="mock_notes", once=False)
        -> 每 5 秒: scan_and_update()
           -> 检测新增/变更 .md 文件
           -> ChromaManager.add_note_from_file()
              -> 读取文件内容
              -> 解析 YAML frontmatter
              -> SiliconFlow Embedding API 向量化
              -> ChromaDB upsert
           -> 检测删除 .md 文件
           -> ChromaManager.delete_note()
           -> 保存状态到 .watcher_state.json
  -> threading.Thread(_sync_github_news, daemon=True)
     -> GitHubNewsSpider.download_all_news()
        -> 获取本年度新闻文件列表
        -> 下载到 mock_notes/github_news/
        -> 由 note_watcher 自动检测并索引到 ChromaDB
```

### 13.5 意图识别与路由链

```
用户请求 POST /chat/route
  -> chat.py
  -> agents/router_agent.py: run_router()
     -> create_router_graph().invoke()
        -> RouterAgent.recognize_intent()
           -> _keyword_classify() 关键词规则识别
           -> _llm_classify() LLM 识别 [可选，置信度更高时覆盖]
           -> _detect_sub_mode() 子模式识别
           -> _extract_params() 参数提取（subject/difficulty/year/knowledge_point）
        -> RouterAgent.route() -> 路由到对应模式节点
           -> quiz: create_quiz_node()（真实 Quiz Agent）
           -> qa/diagnosis/unknown: 占位节点
  <- 返回 RouteResponse
```

---

## 14. 环境变量一览

以下为 `.env.example` 中所有支持的环境变量，括号内为默认值。

**LLM 相关**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| SILICONFLOW_API_KEY | 空（必填） | SiliconFlow API Key |
| LLM_MODEL | deepseek-ai/DeepSeek-V3 | LLM 模型（必填） |
| LLM_BASE_URL | https://api.siliconflow.cn/v1 | LLM API 基础 URL |
| LLM_TEMPERATURE | 0.3 | 采样温度 |
| LLM_MAX_TOKENS | 2048 | 最大 token 数 |
| LLM_TIMEOUT | 60 | API 超时（秒） |

**速率限制**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| SF_REQUEST_DELAY_SECONDS | 1.0 | 请求基础延迟 |
| SF_MAX_RETRIES | 3 | 最大重试次数 |
| SF_API_TIMEOUT | 30 | 请求超时（秒） |

**Embedding**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| EMBEDDING_MODEL | BAAI/bge-m3 | Embedding 模型 |
| EMBEDDING_BASE_URL | https://api.siliconflow.cn/v1 | Embedding 基础 URL |
| SILICONFLOW_API_URL | https://api.siliconflow.cn/v1/embeddings | 完整 Embedding URL |
| EMBEDDING_DIM | 1024 | 向量维度 |
| BATCH_SIZE | 32 | 批处理大小 |
| RETRY_BASE_DELAY | 5 | 重试基础延迟（秒） |

**ChromaDB**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| CHROMA_PERSIST_DIRECTORY | chroma_userdata | 持久化目录 |
| CHROMA_COLLECTION_NAME | user_notes | 集合名称 |

**笔记监控**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| NOTES_WATCH_DIR | mock_notes | 监控目录 |
| WATCHER_SCAN_INTERVAL | 5 | 扫描间隔（秒） |

**FAISS**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| FAISS_INDEX_DIR | knowledge_base/faiss_index | 索引目录 |
| KNOWLEDGE_DB_PATH | datebase/knowledge_base.db | 题库路径 |

**诊断 Agent**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| DIAGNOSIS_WEAK_THRESHOLD | 0.6 | 薄弱点准确率阈值 |
| DIAGNOSIS_RECOMMEND_PER_POINT | 3 | 每薄弱点推荐题目数 |

**FastAPI 服务**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| APP_TITLE | 考研智能辅导系统 API | 应用标题 |
| APP_VERSION | 0.2.0 | 版本号 |
| CORS_ORIGINS | ["*"] | CORS 来源 |
| LOG_LEVEL | INFO | 日志级别 |

**JWT 认证**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| JWT_SECRET_KEY | 空字符串（触发运行时随机生成） | 签名密钥；未设置时 `get_settings()` 自动生成临时随机密钥，重启后 Token 失效；生产环境必须显式配置强随机字符串 |
| JWT_ALGORITHM | HS256 | 签名算法 |
| JWT_EXPIRE_MINUTES | 1440 | Token 有效期（分钟） |

**RAG 与检索**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| DEFAULT_N_FAISS | 5 | FAISS 检索数量 |
| DEFAULT_N_CHROMA | 3 | Chroma 检索数量 |
| MAX_HISTORY_MESSAGES | 6 | 对话历史条数 |
| STREAM_CHAR_DELAY | 0.01 | SSE 字符延迟（秒） |
| MOCK_HISTORY_PATH | mock_notes/mock_user_history.json | Mock 历史路径 |

**GitHub 新闻爬虫**：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| GITHUB_NEWS_OWNER | DuckBurnIncense | 仓库 owner |
| GITHUB_NEWS_REPO | xin-wen-lian-bo | 仓库名 |
| GITHUB_NEWS_DIR | news | 远程目录 |
| GITHUB_NEWS_BRANCH | master | 分支 |
| GITHUB_NEWS_LOCAL_DIR | mock_notes/github_news | 本地保存目录 |
| GITHUB_TOKEN | 空 | GitHub Token |
| GITHUB_SPIDER_MAX_RETRIES | 3 | 下载最大重试次数 |
| GITHUB_SPIDER_RETRY_DELAY | 1.0 | 重试基础延迟（秒） |
| GITHUB_SPIDER_DOWNLOAD_TIMEOUT | 15 | 下载超时（秒） |
| GITHUB_SPIDER_RATE_LIMIT_DELAY | 0.5 | 速率限制延迟（秒） |

**其他路径覆盖**：

| 变量名 | 说明 |
|--------|------|
| REPO_ROOT | 项目根目录（默认 os.getcwd()） |
| USERDATA_DB_PATH | userdata.db 路径 |

---

## 15. 测试体系

### 15.1 测试文件

| 文件 | 测试内容 |
|------|---------|
| tests/conftest.py | 测试夹具（pytest fixtures） |
| tests/test_backend_routers.py | FastAPI 路由集成测试 |
| tests/test_chroma_manager.py | ChromaManager 单元测试 |
| tests/test_diagnosis_agent.py | DiagnosisAgent 单元测试 |
| tests/test_faiss_index.py | FAISS 索引相关测试 |
| tests/test_note_watcher.py | NoteWatcher 单元测试 |
| tests/test_quiz_agent.py | QuizAgent 单元测试 |
| tests/test_rag_agent.py | RAGAgent 单元测试 |
| tests/test_router_agent.py | RouterAgent 单元测试 |
| tests/test_sf_retry.py | sf_retry 模块单元测试 |

### 15.2 运行测试

```
pytest tests/ -v
```

**注意**：各 Agent 测试文件中的 ChromaManager 和 LLM 通常通过 mock 注入，无需真实 API Key 即可运行。

---

*本文档根据项目各 Python 源文件（backend、agents、knowledge_base、utils、datebase）及 SQLite 数据库 schema 全量梳理生成，涵盖系统架构、模块职责、接口规范、数据模型和调用链路，供开发维护参考。*
