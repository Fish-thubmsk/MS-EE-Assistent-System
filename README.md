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
| **LLM / Embedding** | SiliconFlow API（DeepSeek-R1） | 统一通过 SiliconFlow API 对接，支持推理与向量化 |
| **部署** | Docker | 容器化部署，各服务独立可扩展 |

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动后端

```bash
cd backend
uvicorn main:app --reload
```

### 3. 前端访问

打开 `frontend/index.html`，或按前端框架说明启动开发服务器。

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

## 📝 动态知识库模块（ChromaDB 增量更新）

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
