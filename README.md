# 考研智能辅导系统

基于 **FastAPI + LangGraph + SiliconFlow API** 的考研智能辅导平台。系统集成静态结构化知识库（SQLite + FAISS）与动态个人知识库（ChromaDB），通过多模式 Agent 工作流为考生提供智能问答、刷题练习、错题分析与学习诊断等功能。

---

## 📋 目录

- [功能特性](#-功能特性)
- [技术架构](#️-技术架构)
- [目录结构](#-目录结构)
- [前置条件](#-前置条件)
- [方式一：Docker 部署（推荐）](#-方式一docker-部署推荐)
- [方式二：本地开发部署](#-方式二本地开发部署)
- [环境变量说明](#-环境变量说明)
- [数据库说明](#-数据库说明)
- [API 接口速查](#-api-接口速查)
- [常见问题](#-常见问题)
- [相关文档](#-相关文档)

---

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| **智能问答** | 基于 RAG 的知识点问答，支持 SSE 流式输出，显示引用来源与推荐题目 |
| **刷题练习** | 从题库中随机获取题目，提交答案后获取 LLM 批改意见与流式解析 |
| **学习诊断** | 根据做题记录分析薄弱知识点，生成个性化诊断报告与练习推荐 |
| **笔记管理** | 支持笔记/错题的增量向量化存储与语义检索 |
| **用户认证** | JWT 注册/登录，答题记录与诊断报告与账号关联 |
| **Mock 模式** | 无 API Key 时系统自动降级，前端所有功能仍可正常演示 |

---

## 🏗️ 技术架构

```
┌──────────────────────────────────────────────────────────┐
│                       前端（nginx）                        │
│          HTML / JS 单页面  ←→  /api/、/diagnosis/         │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼───────────────────────────────────┐
│                   FastAPI 后端                             │
│  /api/auth   /api/practice   /api/answer   /diagnosis    │
│  /api/notes  /chat           /health                     │
└──────┬───────────────┬────────────────┬──────────────────┘
       │               │                │
┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────────────────┐
│  LangGraph  │ │  SiliconFlow │ │      数据存储层           │
│  Agent 工作流│ │  API（LLM）  │ │  SQLite  FAISS  ChromaDB │
└─────────────┘ └─────────────┘ └──────────────────────────┘
```

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| **后端** | FastAPI + uvicorn | 提供 RESTful API，支持 SSE 流式响应 |
| **前端** | HTML / JS 静态单页面 | 无需构建，浏览器直接打开或通过 HTTP 服务器访问 |
| **Agent 工作流** | LangGraph | Router / RAG / Quiz / Diagnosis 多模式 Agent |
| **LLM / Embedding** | SiliconFlow API | 支持 DeepSeek-V3、Qwen 等模型；Embedding 使用 BAAI/bge-m3 |
| **静态知识库** | SQLite + FAISS | 考研题库精确查询 + 语义向量检索 |
| **动态知识库** | ChromaDB | 用户笔记与错题的实时增量向量化检索 |
| **用户数据** | SQLAlchemy + SQLite | 用户账号、答题记录、诊断报告 |
| **认证** | PyJWT + bcrypt | JWT Bearer Token，bcrypt 密码哈希 |
| **部署** | Docker + Docker Compose | 多阶段构建，nginx 反向代理，容器化一键启动 |

---

## 📁 目录结构

```
MS-EE-Assistent-System/
├── backend/                    # FastAPI 后端服务
│   ├── main.py                 # 应用入口，注册路由与中间件
│   ├── config.py               # 全局配置（pydantic-settings 读取 .env）
│   ├── dependencies.py         # FastAPI 依赖注入（JWT 认证）
│   ├── database/
│   │   ├── models.py           # SQLAlchemy ORM 模型（User / QuizRecord / DiagnosisReport）
│   │   └── db_manager.py       # userdata.db 初始化与会话管理
│   └── routers/
│       ├── auth.py             # POST /api/auth/register、/login；GET /api/auth/me
│       ├── answer.py           # POST /api/answer、/api/answer/stream；GET /api/answer/mock
│       ├── practice.py         # GET /api/practice/question；POST /api/practice、/api/practice/stream
│       ├── diagnosis.py        # POST /diagnosis/run；GET /diagnosis/mock
│       ├── notes.py            # POST/GET/DELETE /notes/
│       └── chat.py             # POST /chat/route（意图识别）
│
├── agents/                     # LangGraph 多模式 Agent
│   ├── router_agent.py         # 意图识别：将用户输入路由到对应 Agent
│   ├── rag_agent.py            # RAG 问答 Agent（FAISS + ChromaDB 检索 + LLM 生成）
│   ├── quiz_agent.py           # 刷题 Agent（题目获取、答案批改、解析生成）
│   └── diagnosis_agent.py      # 诊断 Agent（薄弱知识点分析与推荐）
│
├── knowledge_base/             # 知识库管理
│   ├── build_faiss_index.py    # 构建 FAISS 向量索引脚本（需配置 API Key）
│   ├── chroma_manager.py       # ChromaDB 管理核心（笔记向量化与检索）
│   ├── note_watcher.py         # mock_notes/ 目录增量监控脚本
│   └── faiss_index/            # FAISS 索引文件（运行时生成，不随仓库分发）
│
├── frontend/                   # Web 前端（纯静态，无需构建）
│   ├── index.html              # 主界面（问答 / 刷题 / 诊断）
│   ├── login.html              # 登录页
│   └── register.html           # 注册页
│
├── datebase/                   # 考研题库（SQLite）
│   ├── knowledge_base.db       # 已就绪的考研题库（政治 + 数学 + 英语，共 2052 条题目）
│   ├── build_knowledge_base.py # 从 JSON 构建数据库脚本
│   └── README.md               # 数据库表结构详细说明
│
├── docker/                     # Docker 部署配置
│   ├── Dockerfile              # 后端多阶段构建镜像
│   ├── Dockerfile.frontend     # 前端 nginx 镜像
│   ├── docker-compose.yml      # 服务编排（backend + frontend）
│   └── nginx.conf              # nginx 反向代理配置
│
├── chroma_userdata/            # ChromaDB 持久化目录（运行时生成）
├── mock_notes/                 # mock 笔记/错题 Markdown 文件
├── tests/                      # 单元 / 集成测试（pytest）
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量配置模板
└── README.md                   # 本文件
```

---

## 🔧 前置条件

### 方式一（Docker 部署）

| 依赖 | 版本要求 | 获取方式 |
|------|----------|----------|
| Docker | 20.10+ | https://docs.docker.com/get-docker/ |
| Docker Compose | v2.1+ | 已内置于 Docker Desktop；Linux 需单独安装 |

### 方式二（本地开发）

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | 3.11+ | 建议使用虚拟环境（venv / conda） |
| pip | 23+ | 随 Python 附带 |

### 可选（启用 LLM / Embedding 功能）

- **SiliconFlow API Key**：在 https://siliconflow.cn 注册并获取。
  - 不配置 Key 时，系统自动降级为 **mock 模式**，前端功能可正常演示，但 LLM 生成内容为预设回复。
  - 构建 FAISS 向量索引时必须配置 Key（Embedding API 调用）。

---

## 🐳 方式一：Docker 部署（推荐）

> 适合快速体验或生产部署，无需本地 Python 环境。

### 第 1 步：克隆仓库

```bash
git clone https://github.com/Fish-thubmsk/MS-EE-Assistent-System.git
cd MS-EE-Assistent-System
```

### 第 2 步：配置环境变量

```bash
cp .env.example .env
```

用文本编辑器打开 `.env`，至少配置以下两项：

```dotenv
# ⚠️ 必填：LLM 模型名称（未填写将导致后端启动失败）
LLM_MODEL=deepseek-ai/DeepSeek-V3

# 推荐填写：SiliconFlow API Key（不填则降级为 mock 模式）
SILICONFLOW_API_KEY=your_key_here

# 生产环境必须替换为强随机字符串（开发环境可保留默认值）
JWT_SECRET_KEY=CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS
```

> 快速生成 JWT_SECRET_KEY：`openssl rand -hex 32`

### 第 3 步：构建并启动服务

```bash
cd docker
docker compose up -d --build
```

Docker Compose 会依次完成：
1. 构建后端镜像（多阶段，安装 Python 依赖与系统库 `libgomp1`）
2. 构建前端镜像（复制静态文件到 nginx）
3. 启动后端服务，等待健康检查通过（`/health` 接口返回 200）
4. 后端健康后启动前端服务

### 第 4 步：验证服务正常

```bash
# 查看容器状态（STATUS 应为 Up，health 状态为 healthy）
docker compose ps

# 测试后端健康接口
curl http://localhost:8000/health
# 预期输出：{"status":"ok","version":"0.2.0"}
```

### 第 5 步：访问应用

| 地址 | 说明 |
|------|------|
| http://localhost:3000 | **前端页面**（问答 / 刷题 / 诊断） |
| http://localhost:8000/docs | **后端 Swagger API 文档** |
| http://localhost:8000/redoc | 后端 ReDoc 文档 |
| http://localhost:8000/health | 健康检查接口 |

> **注意**：Docker 模式下，nginx 已将 `/api/`、`/diagnosis/`、`/notes/`、`/health` 反向代理到后端。前端页面无需修改「后端地址」，保持默认 `http://localhost:8000` 即可。

### 第 6 步：（可选）构建 FAISS 向量索引

> 如需启用「知识库语义检索」功能，需在后端容器内构建 FAISS 索引。**已配置 `SILICONFLOW_API_KEY` 时执行；否则跳过，系统会使用 mock 检索降级。**

```bash
# 进入后端容器
docker compose exec backend bash

# 构建所有学科的向量索引（约需数分钟，取决于 API 速率）
python knowledge_base/build_faiss_index.py

# 或仅构建某个学科
python knowledge_base/build_faiss_index.py --subject 政治
python knowledge_base/build_faiss_index.py --subject 数学
python knowledge_base/build_faiss_index.py --subject 英语

# 退出容器
exit
```

索引文件保存于 `knowledge_base/faiss_index/`，通过 volume 挂载持久化，重启容器后无需重建。

### 查看日志

```bash
# 实时查看后端日志
docker compose logs -f backend

# 实时查看前端日志
docker compose logs -f frontend
```

### 停止与清理

```bash
# 停止服务（保留数据）
docker compose down

# 停止并清除所有持久化数据（ChromaDB / FAISS 索引）
docker compose down -v

# 仅重建某个服务
docker compose build backend
docker compose up -d backend
```

---

## 💻 方式二：本地开发部署

> 适合开发调试，支持热重载。

### 第 1 步：克隆仓库

```bash
git clone https://github.com/Fish-thubmsk/MS-EE-Assistent-System.git
cd MS-EE-Assistent-System
```

### 第 2 步：创建并激活虚拟环境（推荐）

```bash
# 创建虚拟环境
python -m venv .venv

# 激活（Linux / macOS）
source .venv/bin/activate

# 激活（Windows PowerShell）
.venv\Scripts\Activate.ps1
```

### 第 3 步：安装 Python 依赖

```bash
pip install -r requirements.txt
```

> `requirements.txt` 包含 FastAPI、LangGraph、LangChain、FAISS、ChromaDB、SQLAlchemy、PyJWT、bcrypt 等依赖。

### 第 4 步：配置环境变量

```bash
cp .env.example .env
```

打开 `.env`，至少设置：

```dotenv
# 必填
LLM_MODEL=deepseek-ai/DeepSeek-V3

# 推荐填写（不填则 mock 模式）
SILICONFLOW_API_KEY=your_key_here

# JWT 密钥（开发环境可保留默认，生产环境必须替换）
JWT_SECRET_KEY=CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS
```

### 第 5 步：（可选）构建 FAISS 向量索引

> 如需启用知识库语义检索，在启动后端前先构建索引。已配置 `SILICONFLOW_API_KEY` 时执行。

```bash
# 从项目根目录运行（默认构建全部学科）
python knowledge_base/build_faiss_index.py

# 仅构建某学科
python knowledge_base/build_faiss_index.py --subject 政治

# 查看全部选项
python knowledge_base/build_faiss_index.py --help
```

构建完成后，索引文件保存于 `knowledge_base/faiss_index/`（`questions.index` + `id_map.json`），后续无需重复构建（脚本支持增量更新）。

### 第 6 步：（可选）初始化 ChromaDB 笔记库

> 如需启用「动态笔记检索」功能，将 `mock_notes/` 中的 Markdown 文件向量化后存入 ChromaDB。

```bash
# 一次性扫描并写入
python -m knowledge_base.note_watcher --once

# 或启动持续监控（每 5 秒扫描一次新增/修改的文件）
python -m knowledge_base.note_watcher
```

### 第 7 步：启动后端服务

```bash
# 开发模式（热重载，推荐）
uvicorn backend.main:app --reload

# 或指定端口
uvicorn backend.main:app --reload --port 8000
```

后端启动时会自动完成以下初始化：
- 读取 `.env` 配置（`backend/config.py`）
- 初始化 `userdata.db`（用户表、答题记录表、诊断报告表）

启动成功后终端会输出：
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

### 第 8 步：访问前端

前端为纯静态单页面，无需任何构建步骤，有两种访问方式：

**方式 A：通过本地 HTTP 服务器（推荐，避免浏览器跨域限制）**

```bash
python -m http.server 3000 --directory frontend
# 然后访问 http://localhost:3000
```

**方式 B：直接用浏览器打开文件**

```bash
# macOS
open frontend/index.html
# Linux
xdg-open frontend/index.html
# Windows
start frontend/index.html
```

### 第 9 步：验证功能

1. 访问 http://localhost:3000，应显示主界面
2. 访问 http://localhost:8000/docs，应显示 Swagger 文档
3. 在主界面「刷题」Tab 点击「获取题目」，应成功加载题目（mock 模式下返回内置示例题）

> **联调说明**
> - 前端页面左侧栏「后端地址」默认为 `http://localhost:8000`，可按需修改
> - 若 `SILICONFLOW_API_KEY` 未配置，后端自动降级为 mock 模式，LLM 功能仍可演示
> - 若遇到跨域报错，确认使用方式 A（HTTP 服务器）而非直接打开文件

### 第 10 步：运行测试（可选）

```bash
# 运行全部测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/test_backend_routers.py -v
pytest tests/test_chroma_manager.py -v
pytest tests/test_rag_agent.py -v
```

---

## ⚙️ 环境变量说明

完整的环境变量清单见 [`.env.example`](.env.example)。以下列出关键配置项：

### 必填项

| 变量 | 说明 | 示例值 |
|------|------|--------|
| `LLM_MODEL` | LLM 模型名称（**必须配置**，未填写后端无法启动） | `deepseek-ai/DeepSeek-V3` |

### LLM / Embedding 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SILICONFLOW_API_KEY` | `""` | SiliconFlow API Key；为空时降级为 mock 模式 |
| `LLM_BASE_URL` | `https://api.siliconflow.cn/v1` | LLM API 地址（兼容 OpenAI Chat Completions 格式） |
| `LLM_TEMPERATURE` | `0.3` | 采样温度（0.0–1.0） |
| `LLM_MAX_TOKENS` | `2048` | 最大生成 Token 数 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | Embedding 模型 |
| `EMBEDDING_DIM` | `1024` | 向量维度（bge-m3 为 1024，切换模型时需同步修改） |

### 路径配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FAISS_INDEX_DIR` | `knowledge_base/faiss_index` | FAISS 索引目录（相对项目根目录） |
| `KNOWLEDGE_DB_PATH` | `datebase/knowledge_base.db` | SQLite 考研题库路径 |
| `CHROMA_PERSIST_DIRECTORY` | `chroma_userdata` | ChromaDB 持久化目录 |

### 认证配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `JWT_SECRET_KEY` | `CHANGE_ME_...` | JWT 签名密钥，**生产环境必须替换为强随机字符串** |
| `JWT_ALGORITHM` | `HS256` | JWT 签名算法 |
| `JWT_EXPIRE_MINUTES` | `1440` | JWT 有效期（分钟，默认 24 小时） |

### 服务配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CORS_ORIGINS` | `["*"]` | 允许跨域来源，生产环境应收紧为具体域名 |
| `LOG_LEVEL` | `INFO` | 日志级别（DEBUG / INFO / WARNING / ERROR） |

---

## 📊 数据库说明

### 考研题库（`datebase/knowledge_base.db`）

只读 SQLite 数据库，已预置考研历年真题：

| 学科 | 题目数 |
|------|--------|
| 政治 | 495 条 |
| 数学 | 850 条 |
| 英语 | 707 条 + 143 篇文章 |
| **合计** | **2,052 条题目** |

主要数据表：`questions`（题目）、`passages`（英语文章）、`knowledge_point_hierarchy`（知识点树）。详见 [`datebase/README.md`](datebase/README.md)。

### 用户数据库（`userdata.db`，自动初始化）

读写 SQLite 数据库，后端启动时自动创建（无需手动操作）：

| 表名 | 说明 |
|------|------|
| `users` | 用户账号（用户名、密码哈希、昵称、邮箱） |
| `quiz_records` | 答题记录（用户、题目、是否正确、分数、反馈） |
| `diagnosis_reports` | 诊断报告（用户、分析结果 JSON） |

---

## 🔗 API 接口速查

> 完整文档访问 http://localhost:8000/docs

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册，返回 JWT Token |
| POST | `/api/auth/login` | 用户登录，返回 JWT Token |
| GET | `/api/auth/me` | 获取当前用户信息（需 Bearer Token） |

### 问答（RAG）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/answer` | 同步 RAG 问答，返回完整答案 |
| POST | `/api/answer/stream` | SSE 流式 RAG 问答，逐 Token 返回 |
| GET | `/api/answer/mock` | 使用 mock 数据快速体验问答 |

### 刷题

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/practice/subjects` | 获取科目列表 |
| GET | `/api/practice/question` | 随机获取题目（支持科目/题型/年份筛选） |
| POST | `/api/practice` | 提交答案，获取批改结果 |
| POST | `/api/practice/stream` | SSE 流式返回题目解析 |

### 诊断

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/diagnosis/run` | 运行学习诊断，返回薄弱点与推荐报告 |
| GET | `/diagnosis/mock` | 使用 mock 数据快速体验诊断 |

### 笔记

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/notes/` | 新增笔记（向量化存入 ChromaDB） |
| GET | `/notes/query` | 语义检索笔记（`?q=关键词&n=3`） |
| DELETE | `/notes/{doc_id}` | 删除指定笔记 |
| GET | `/notes/count` | 查询笔记总数 |

---

## ❓ 常见问题

**Q: 后端启动时报 `ValidationError: LLM_MODEL` 缺失？**

`LLM_MODEL` 是必填配置项，未设置时后端无法启动。请确保：
1. 项目根目录存在 `.env` 文件（`cp .env.example .env`）
2. `.env` 中 `LLM_MODEL` 已填写（如 `LLM_MODEL=deepseek-ai/DeepSeek-V3`）

---

**Q: 构建 Docker 镜像时报 `libgomp1: not found`？**

后端 Dockerfile 已在 builder 和 runtime 两个阶段均安装 `libgomp1`（faiss-cpu 系统依赖）。如遇此错误，请检查网络连接是否正常，确保 `apt-get` 可以访问 Debian 软件源。

---

**Q: 前端容器启动后访问报 `502 Bad Gateway`？**

前端容器依赖后端健康检查通过后才会启动（`depends_on: condition: service_healthy`）。常见原因：
1. 后端启动失败（缺少 `LLM_MODEL` 等配置），查看日志：
   ```bash
   docker compose logs backend
   ```
2. 后端健康检查超时（默认 15 秒启动期），稍等片刻后重试。

---

**Q: 修改 `.env` 后配置不生效？**

重启对应容器即可：
```bash
docker compose restart backend
```

---

**Q: 如何持久化数据？**

以下目录通过 Docker volume 挂载到宿主机，重建容器后数据不丢失：
- `chroma_userdata/` — ChromaDB 动态笔记库
- `knowledge_base/faiss_index/` — FAISS 向量索引
- `datebase/` — SQLite 考研题库（只读，但挂载保护防覆盖）
- `mock_notes/` — mock 笔记文件

**注意**：执行 `docker compose down -v` 会删除所有 volume，慎用。

---

**Q: 如何在 Docker 容器内手动执行脚本？**

```bash
# 进入后端容器
docker compose exec backend bash

# 例：构建 FAISS 索引
python knowledge_base/build_faiss_index.py --subject 政治

# 例：初始化 ChromaDB 笔记库
python -m knowledge_base.note_watcher --once
```

---

**Q: 本地开发时遇到跨域（CORS）错误？**

确保：
1. 使用 `python -m http.server 3000 --directory frontend` 通过 HTTP 服务器访问前端（而非直接打开 `file://` 路径）
2. 后端 `.env` 中 `CORS_ORIGINS=["*"]`（默认值，开发环境无需修改）

---

## 🔗 相关文档

- [数据库表结构详细说明](datebase/README.md)
- [整体架构设计](datebase/整个idea.md)
- [架构图](datebase/架构图.md)
