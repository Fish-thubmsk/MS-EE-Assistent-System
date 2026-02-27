# 考研智能辅导系统

基于 FastAPI + LangGraph + SiliconFlow API 的考研智能辅导平台，集成静态结构化知识库（SQLite + FAISS）与动态个人知识库（ChromaDB），通过多模式 Agent 工作流为考生提供智能问答、错题分析等功能。

---

## 📁 目录结构

```
newrepo/
├── datebase/           # 已有的考研题库数据库与文档说明
├── backend/            # FastAPI 后端服务代码
├── frontend/           # Web 前端（HTML/JS/React/Vue 均可）
├── agents/             # LangGraph 多模式 Agent 逻辑
├── knowledge_base/     # 存放 FAISS 索引等静态向量库文件
├── chroma_userdata/    # 动态个人知识库（ChromaDB）相关文件
├── tests/              # 单元 / 集成测试
├── docker/             # Docker 配置文件（Dockerfile 等）
├── requirements.txt    # Python 依赖清单
└── README.md           # 项目说明（本文件）
```

---

## 🏗️ 技术架构

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| **后端** | FastAPI | 提供 RESTful API，对接前端与 Agent |
| **前端** | HTML / JS（或 React / Vue） | Web 交互界面 |
| **静态知识库** | SQLite + FAISS | 题库元数据精确查询 + 语义向量检索；Embedding 使用 BAAI/bge-m3，经由 SiliconFlow API 调用 |
| **动态知识库** | ChromaDB | 用户笔记、错题等个人私域数据的实时增量更新 |
| **Agent 工作流** | LangGraph | 多模式 Agent（问答、刷题、分析等），节点化流程编排 |
| **LLM / Embedding** | SiliconFlow API（DeepSeek-V3 推荐） | 统一通过 SiliconFlow API 对接，支持推理与向量化；模型由 `LLM_MODEL` 环境变量配置 |
| **部署** | Docker | 容器化部署，各服务独立可扩展 |

---

## 🚀 快速开始

### 方式一：Docker 一键启动（推荐）

> 需要安装 [Docker](https://docs.docker.com/get-docker/) 和 [Docker Compose](https://docs.docker.com/compose/install/)（v2.x）。

#### 1. 配置环境变量

```bash
cp .env.example .env
# 用编辑器打开 .env，填写 SILICONFLOW_API_KEY 等参数
# ⚠️  必须配置 LLM_MODEL，未填写将导致服务启动报错
# 推荐配置（响应快、成本低）：
#   SILICONFLOW_API_KEY=<your_key>
#   LLM_MODEL=deepseek-ai/DeepSeek-V3
# 若无 API Key，保持默认即可（系统自动降级为 mock 模式）
```

#### 2. 构建并启动所有服务

```bash
cd docker
docker compose up -d --build
```

启动后访问：
- **前端页面**：http://localhost:3000
- **后端 API 文档**：http://localhost:8000/docs
- **健康检查**：http://localhost:8000/health

> Docker 方式下前端通过 nginx 反向代理后端（`/api/`、`/diagnosis/`、`/notes/`），**无需在侧边栏修改「后端地址」**，保持默认 `http://localhost:8000` 即可。

#### 3. 查看日志

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

#### 4. 停止服务

```bash
docker compose down
```

如需同时清除挂载卷（**将删除 ChromaDB 持久化数据**）：

```bash
docker compose down -v
```

---

### 方式二：本地开发启动

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 启动后端

```bash
uvicorn backend.main:app --reload
```

#### 3. 前端访问

前端为纯静态单页面，**无需任何构建步骤**，两种启动方式：

**方式一：直接用浏览器打开（最简）**

```bash
# macOS
open frontend/index.html
# Linux
xdg-open frontend/index.html
# Windows
start frontend/index.html
```

**方式二：通过本地 HTTP 服务器（推荐，避免浏览器跨域限制）**

```bash
# Python 3
python -m http.server 3000 --directory frontend
# 然后访问 http://localhost:3000
```

> **联调说明**
>
> 1. 确保后端已在 `http://localhost:8000` 启动（`uvicorn backend.main:app --reload`）。
> 2. 打开前端页面后，左侧栏「后端地址」默认填写 `http://localhost:8000`，可按需修改。
> 3. 若 `SILICONFLOW_API_KEY` 未配置，后端会自动降级为 mock 模式，前端所有功能仍可正常演示。
> 4. 若遇到跨域问题，使用上述方式二通过 HTTP 服务器访问，或确认后端 `CORS_ORIGINS` 已包含前端域名。

---

### 🐳 Docker 常见问题

**Q: 构建时报错 `libgomp1: not found`？**

后端 Dockerfile 已在 builder 阶段安装 `libgomp1`（faiss-cpu 依赖），如遇此错误请确保网络正常，让 `apt-get` 正常安装系统依赖。

**Q: 前端容器启动后报 `502 Bad Gateway`？**

前端依赖后端健康检查通过后才会启动（`depends_on: condition: service_healthy`）。请检查后端日志是否有报错：

```bash
docker compose logs backend
```

**Q: 修改了 `.env` 后如何生效？**

重启后端容器即可：

```bash
docker compose restart backend
```

**Q: 如何持久化数据？**

数据目录通过 volume 挂载到宿主机，以下目录会保留数据：
- `chroma_userdata/` — ChromaDB 动态知识库
- `knowledge_base/faiss_index/` — FAISS 向量索引
- `datebase/` — SQLite 题库
- `mock_notes/` — mock 笔记文件

**Q: 如何仅重新构建某个服务？**

```bash
docker compose build backend   # 仅重建后端镜像
docker compose up -d backend   # 重启后端容器
```

**前端功能一览**

| Tab | 说明 | 对应后端接口 |
|-----|------|------------|
| 问答 | 输入知识点问题，RAG 检索并 LLM 生成答案，支持 SSE 流式输出，显示引用来源与推荐题目 | `POST /api/answer` / `POST /api/answer/stream` |
| 刷题 | 随机获取 mock 题，提交答案后获取批改意见和逐字流式解析 | `GET /api/practice/question` / `POST /api/practice/stream` |
| 诊断 | 根据 mock 用户做题历史分析薄弱知识点，生成诊断报告和推荐练习题/笔记 | `POST /diagnosis/run` |

**侧边栏选项**

- **后端地址**：可动态修改，无需刷新页面
- **当前用户**：模拟三个 mock 用户（user_001/002/003），影响诊断模式的分析结果
- **知识库**：独立开关控制是否启用 FAISS 静态知识库 / Chroma 动态笔记库
- **流式输出**：开关切换 SSE 流式 / 同步两种响应模式

---

## 📊 数据库现状

已就绪的考研题库（位于 `datebase/`）：

| 学科 | 题目数 |
|------|--------|
| 政治 | 495 条 |
| 数学 | 850 条 |
| 英语 | 707 条 + 143 篇文章 |
| **合计** | **2,052 条题目** |

详见 [`datebase/README.md`](datebase/README.md)。

---

---

## 🔍 FAISS 向量索引

FAISS 索引文件（`knowledge_base/faiss_index/`）是运行时生成的二进制产物，**不随仓库分发**。首次使用知识库检索前需手动构建。

### 构建索引

> 前提：已配置 `SILICONFLOW_API_KEY`（用于 Embedding API 调用）并已就绪 SQLite 题库（`datebase/knowledge_base.db`）。

```bash
# 从项目根目录运行（默认构建所有学科）
python knowledge_base/build_faiss_index.py

# 仅构建某学科
python knowledge_base/build_faiss_index.py --subject 政治

# 查看全部选项
python knowledge_base/build_faiss_index.py --help
```

构建完成后索引文件保存于 `knowledge_base/faiss_index/`（`questions.index` + `id_map.json`），后续无需重复构建（脚本支持增量更新）。

### 路径配置

所有路径均通过环境变量配置，无硬编码绝对路径，项目移动或重命名目录后无需修改代码：

| 环境变量 | 说明 | 默认值（相对项目根目录） |
|----------|------|--------------------------|
| `FAISS_INDEX_DIR` | FAISS 索引目录 | `knowledge_base/faiss_index` |
| `KNOWLEDGE_DB_PATH` | SQLite 知识库路径 | `datebase/knowledge_base.db` |
| `CHROMA_PERSIST_DIRECTORY` | ChromaDB 持久化目录 | `chroma_userdata` |

以上变量可在 `.env` 文件中配置（复制 `.env.example` 为 `.env` 后编辑）。

---



本模块实现了基于 ChromaDB 的动态个人知识库，支持用户笔记、错题的增量向量化与检索。

### 模块文件说明

| 文件 | 说明 |
|------|------|
| `knowledge_base/chroma_manager.py` | ChromaDB 管理核心，调用 SiliconFlow BAAI/bge-m3 API 向量化 |
| `knowledge_base/note_watcher.py` | 增量监控脚本，监听 `mock_notes/` 目录的文件变更 |
| `backend/routers/notes.py` | FastAPI 笔记 API 路由（增删查） |
| `mock_notes/` | mock 笔记/错题数据目录 |
| `chroma_userdata/` | ChromaDB 持久化存储目录 |

### mock 数据格式

`mock_notes/` 目录下的 Markdown 文件头部使用 YAML frontmatter 声明元数据：

```markdown
---
subject: 数学          # 学科（数学 / 政治 / 英语）
chapter: 高等数学-极限  # 章节
type: note             # 类型：note（笔记）或 wrong（错题）
date: 2024-01-10       # 日期
---

# 正文内容

...
```

已包含的 mock 示例：

| 文件 | 学科 | 类型 |
|------|------|------|
| `math_calculus_note.md` | 数学 | 笔记（极限与连续） |
| `math_derivative_wrong.md` | 数学 | 错题（导数计算） |
| `politics_materialism_note.md` | 政治 | 笔记（唯物论） |
| `politics_history_wrong.md` | 政治 | 错题（新民主主义革命） |
| `english_reading_note.md` | 英语 | 笔记（长难句分析） |
| `english_writing_wrong.md` | 英语 | 错题（写作失分点） |

### 快速使用

#### 1. 配置 SiliconFlow API Key

```bash
export SILICONFLOW_API_KEY=your_api_key_here
```

#### 2. 一次性扫描 mock_notes 目录并存入 ChromaDB

```bash
python -m knowledge_base.note_watcher --once
```

#### 3. 持续监控（每 5 秒扫描一次）

```bash
python -m knowledge_base.note_watcher
```

#### 4. 使用 API 接口

启动后端：

```bash
uvicorn backend.main:app --reload
```

**新增笔记**

```bash
curl -X POST http://localhost:8000/notes/ \
  -H "Content-Type: application/json" \
  -d '{"content": "# 微积分\n极限是微积分的基础。", "metadata": {"subject": "数学"}}'
```

**向量相似度检索**

```bash
curl "http://localhost:8000/notes/query?q=极限的定义&n=3"
# 按学科过滤
curl "http://localhost:8000/notes/query?q=革命&subject=政治"
```

**删除笔记**

```bash
curl -X DELETE http://localhost:8000/notes/{doc_id}
```

**查询总数**

```bash
curl http://localhost:8000/notes/count
```

#### 5. 运行测试

```bash
pytest tests/test_chroma_manager.py -v
```

---

## 🔗 相关文档

- [数据库说明](datebase/README.md)
- [整体架构设计](datebase/整个idea.md)
- [架构图](datebase/架构图.md)
