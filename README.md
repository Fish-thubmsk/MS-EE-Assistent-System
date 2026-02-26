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

## 🔗 相关文档

- [数据库说明](datebase/README.md)
- [整体架构设计](datebase/整个idea.md)
- [架构图](datebase/架构图.md)
