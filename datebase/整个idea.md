---
creation date: 2025-04-08 20:53
tags: 
status: colsed
flag: ✔️
member: 
grade: 
aliases: []
---
🎉 **您的想法非常棒！** 让我帮您理清思路并优化设计：

---

## ✅ **优化后的架构设计**

### **核心理念**
1. ✅ **简化知识库** → 只维护两个：**结构化知识库** + **动态知识库**
2. ✅ **用户可选知识库** → 根据场景手动切换
3. ✅ **不同Agent对应不同工作流** → 根据使用场景激活不同的Agent组合

---

## 📚 **知识库架构（简化版）**

### **方案：两大知识库**

```
┌─────────────────────────────────────────────────┐
│          知识库层（两大库）                       │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────────────────┐  ┌─────────────────┐ │
│  │ 1. 结构化知识库      │  │ 2. 动态知识库   │ │
│  │   (静态+元数据)      │  │   (用户个人)    │ │
│  └──────────────────────┘  └─────────────────┘ │
│         ↓                          ↓            │
│   FAISS向量库                 Chroma向量库       │
│   + SQLite元数据              (支持增量更新)     │
└─────────────────────────────────────────────────┘
```

---

### **知识库1：结构化知识库（静态 + 可查询）**

#### **存储内容**
| 数据类型      | 格式             | 存储方式              | 更新频率 |
| --------- | -------------- | ----------------- | ---- |
| 历年真题 JSON | 结构化            | SQLite表 + FAISS向量 | 每年1次 |
| 考研大纲      | 文本             | FAISS向量           | 每年1次 |
| 新闻联播汇总    | **AI处理后的JSON** | SQLite表 + FAISS向量 | 每月1次 |

#### **技术方案**

```python
# ========== 结构化知识库设计 ==========

# 1. SQLite 表结构
"""
表1:  questions (题库)
- id (主键)
- subject (学科:  数学/英语/政治/408)
- year (年份)
- module (模块: 如数学的17个模块)
- content (题目内容)
- answer (答案)
- knowledge_points (知识点标签, JSON格式)
- difficulty (难度)
- vector_id (对应的向量ID)

表2: news (新闻联播)
- id
- date (日期)
- title (标题)
- summary (AI生成的摘要)
- knowledge_tags (AI提取的知识点标签)
- vector_id

表3: syllabus (考研大纲)
- id
- subject
- chapter (章节)
- content (大纲内容)
- vector_id
"""

# 2. FAISS 向量库
static_kb = FAISS.from_documents(
    documents=[真题文本, 大纲文本, 新闻文本],
    embedding=embeddings
)
static_kb.save_local("./static_kb")

# 3. 混合检索（向量 + 元数据过滤）
def search_static_kb(query, filters=None):
    """
    query: 用户问题
    filters: 元数据过滤，如 {"subject": "数学", "year": 2024}
    """
    # 先向量检索
    candidates = static_kb.similarity_search(query, k=20)
    
    # 再用SQLite精确过滤
    if filters:
        cursor. execute("""
            SELECT content FROM questions
            WHERE subject=? AND year=? 
        """, (filters['subject'], filters['year']))
        filtered_results = cursor.fetchall()
        
        # 匹配向量检索结果和SQL结果
        final_results = [c for c in candidates if c. page_content in filtered_results]
    else: 
        final_results = candidates[: 5]
    
    return final_results
```

---

### **知识库2：动态知识库（用户个人）**

#### **存储内容**
| 数据类型 | 格式 | 存储方式 | 更新频率 |
|---------|------|---------|---------|
| Obsidian 笔记 | Markdown | Chroma向量库 | 每次保存笔记时 |
| 错题本 | JSON + 图片 | Chroma向量库 + SQLite | 每次添加错题时 |
| 用户上传PDF | 文本 | Chroma向量库 | 上传时 |
| 对话历史 | 文本 | Chroma向量库 | 每次对话后 |

#### **技术方案**

```python
# ========== 动态知识库设计 ==========

from langchain.vectorstores import Chroma

# 每个用户独立的向量库
user_kb = Chroma(
    collection_name=f"user_{user_id}",
    embedding_function=embeddings,
    persist_directory=f"./user_data/{user_id}"
)

# 添加笔记
def add_note(user_id, note_content, metadata):
    """
    metadata: {
        "type": "note",
        "subject": "数学",
        "chapter": "微分",
        "time": "2025-12-28"
    }
    """
    user_kb.add_texts([note_content], metadatas=[metadata])
    user_kb.persist()

# 添加错题（OCR识别后）
def add_wrong_question(user_id, ocr_text, question_data):
    """
    ocr_text: OCR识别的题目文本
    question_data: {
        "subject": "数学",
        "type": "错题",
        "correct_answer": ".. .",
        "my_answer": ".. .",
        "error_reason": "AI分析的错误原因"
    }
    """
    # 同时存入向量库和SQLite
    user_kb.add_texts([ocr_text], metadatas=[question_data])
    
    # SQLite记录错题次数
    cursor.execute("""
        INSERT INTO wrong_questions 
        (user_id, content, subject, error_count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(content) DO UPDATE SET error_count = error_count + 1
    """, (user_id, ocr_text, question_data['subject']))
    
    user_kb.persist()
```

---

## 🎛️ **用户可选知识库 + Agent工作流**

### **核心设计**

用户在**每次提问时**可以选择：
1. **使用哪个知识库**（结构化 / 动态 / 两者）
2. **使用哪个Agent工作流**（刷题模式 / 问答模式 / 学习路径模式）

---

### **前端界面设计**

```
┌────────────────────────────────────────────────┐
│          个性化考研辅导系统                     │
├────────────────────────────────────────────────┤
│                                                 │
│  📚 知识库选择:                                  │
│  [ ] 结构化知识库 (真题/大纲/时事)              │
│  [✓] 我的笔记 (Obsidian)                       │
│  [✓] 我的错题本                                │
│                                                 │
│  🤖 模式选择:                                   │
│  ◉ 刷题模式 (Router→Student/Teacher)           │
│  ○ 问答模式 (RAG Agent)                        │
│  ○ 学习诊断模式 (分析薄弱点)                    │
│                                                 │
│  💬 输入框:                                     │
│  ┌─────────────────────────────────────────┐  │
│  │ 泰勒公式什么时候用？                     │  │
│  └─────────────────────────────────────────┘  │
│                          [发送] [清空]          │
└────────────────────────────────────────────────┘
```

---

### **工作流设计：三种模式**

#### **模式1：刷题模式（借鉴EasyDS）**

**适用场景**：用户刷题、讲解题目

**工作流**：
```
用户提交答案
    ↓
Router Agent (评估正误+完整性)
    ↓
┌───┴────┐
↓        ↓
Student   Teacher
Agent     Agent
(追问)   (纠错/总结)
```

**知识库使用**：
- **优先检索**：动态知识库（用户的错题本、笔记）
- **备用检索**：结构化知识库（相似真题）

```python
# 刷题模式 Workflow
def create_practice_workflow():
    workflow = StateGraph(State)
    
    # 添加节点
    workflow.add_node("router", RouterAgent())
    workflow.add_node("student", StudentAgent())
    workflow.add_node("teacher", TeacherAgent())
    workflow.add_node("rag_tool", RAGToolNode())  # 检索工具
    
    # 流程
    workflow.add_edge(START, "router")
    workflow.add_edge("rag_tool", "teacher")
    workflow.add_edge("student", END)
    
    # Router动态路由
    workflow.add_conditional_edges(
        "router",
        lambda state: state.evaluation['next_agent'],
        {
            "student": "student",
            "teacher": "teacher"
        }
    )
    
    # Teacher可能调用RAG工具
    workflow. add_conditional_edges(
        "teacher",
        lambda state: "rag_tool" if state.need_search else END
    )
    
    return workflow. compile()
```

---

#### **模式2：问答模式（RAG主导）**

**适用场景**：用户问知识点、概念查询

**工作流**：
```
用户提问
    ↓
Question Classifier (问题分类)
    ↓
┌───┴────────┬────────┐
↓            ↓        ↓
RAG Agent    RAG      RAG
(笔记)      (真题)   (时事)
    ↓            ↓        ↓
    └────────┬───────┘
             ↓
    Answer Generator (生成答案)
             ↓
    引用溯源 + 推荐题目
```

**知识库使用**：
- 根据用户**勾选的知识库**进行检索
- 合并结果，生成答案

```python
# 问答模式 Workflow
def create_qa_workflow():
    workflow = StateGraph(State)
    
    # 添加节点
    workflow.add_node("classifier", QuestionClassifier())  # 分类问题
    workflow.add_node("rag_static", RAGAgent(kb="static"))  # 检索结构化库
    workflow.add_node("rag_dynamic", RAGAgent(kb="dynamic"))  # 检索动态库
    workflow.add_node("generator", AnswerGenerator())  # 生成答案
    
    # 流程
    workflow.add_edge(START, "classifier")
    
    # 根据用户选择的知识库并行检索
    def get_search_nodes(state):
        nodes = []
        if state.use_static_kb:
            nodes.append("rag_static")
        if state.use_dynamic_kb:
            nodes.append("rag_dynamic")
        return nodes
    
    workflow.add_conditional_edges(
        "classifier",
        get_search_nodes
    )
    
    # 合并结果
    workflow.add_edge(["rag_static", "rag_dynamic"], "generator")
    workflow.add_edge("generator", END)
    
    return workflow.compile()
```

---

#### **模式3：学习诊断模式**

**适用场景**：分析薄弱点、生成学习报告

**工作流**：
```
用户请求分析
    ↓
Analyzer Agent (分析学习轨迹)
    ↓
┌───┴────────┐
↓            ↓
计算掌握度    提取错题模式
    ↓            ↓
    └────┬───────┘
         ↓
生成学习报告 + 推荐题目
```

**知识库使用**：
- **必须**：动态知识库（用户的刷题记录、错题）
- **可选**：结构化知识库（推荐相关真题）

```python
# 学习诊断模式
def create_diagnosis_workflow():
    workflow = StateGraph(State)
    
    workflow.add_node("analyzer", AnalyzerAgent())  # 分析学习数据
    workflow.add_node("recommender", RecommenderAgent())  # 推荐题目
    
    workflow.add_edge(START, "analyzer")
    workflow.add_edge("analyzer", "recommender")
    workflow.add_edge("recommender", END)
    
    return workflow.compile()
```

---

## 🎨 **完整系统架构图**

```
┌────────────────────────────────────────────────────────┐
│                    前端界面                             │
│  [知识库选择] [模式选择] [输入框]                        │
└────────────────────┬───────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────────┐
│               Workflow调度器                            │
│  根据用户选择的模式，加载不同的Agent工作流               │
├────────────────────┬───────────────────────────────────┤
│  模式1: 刷题模式   │  模式2: 问答模式  │ 模式3: 学习诊断│
│  Router→S/T Agent  │  RAG Agent       │ Analyzer Agent │
└────────────────────┴───────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────────┐
│                 检索协调器                              │
│  根据用户勾选的知识库，决定检索哪些库                   │
├────────────────────┬───────────────────────────────────┤
│  结构化知识库      │         动态知识库                │
│  ────────────      │         ──────────                │
│  ├ FAISS向量       │         ├ Chroma向量 (user_001)   │
│  ├ SQLite元数据    │         ├ Chroma向量 (user_002)   │
│  │  ├ questions表  │         └ SQLite (错题记录)       │
│  │  ├ news表       │                                   │
│  │  └ syllabus表   │                                   │
└────────────────────┴───────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────────┐
│                  数据源                                 │
│  真题JSON | 考研大纲 | 新闻联播 | Obsidian笔记 | 错题   │
└────────────────────────────────────────────────────────┘
```

---

## 💡 **关键实现细节**

### **1. 新闻联播如何处理成JSON？**

```python
import requests
from bs4 import BeautifulSoup

def crawl_news():
    """爬取新闻联播"""
    url = "http://news.cctv.com/lianbo/"
    html = requests.get(url).text
    soup = BeautifulSoup(html, 'html. parser')
    
    news_items = soup.find_all('li', class_='item')
    news_list = []
    
    for item in news_items:
        news_list.append({
            "date": item.find('span').text,
            "title": item. find('a').text,
            "url": item.find('a')['href']
        })
    
    return news_list

def process_with_ai(news_list):
    """用AI提取知识点标签和摘要"""
    processed = []
    
    for news in news_list:
        # 调用LLM
        prompt = f"""
        新闻标题: {news['title']}
        
        任务: 
        1. 生成100字摘要
        2. 提取政治知识点标签 (如: 马克思主义, 时事政治, 经济建设)
        
        输出JSON格式:
        {{
            "summary": ".. .",
            "tags": ["tag1", "tag2"]
        }}
        """
        result = llm. invoke(prompt)
        
        processed.append({
            **news,
            "summary": result['summary'],
            "tags": result['tags']
        })
    
    # 保存到SQLite + 向量化
    save_to_db(processed)
    vectorize_and_save(processed)
    
    return processed
```

---

### **2. 用户选择知识库的逻辑**

```python
class WorkflowManager:
    def __init__(self):
        self.workflows = {
            "practice": create_practice_workflow(),
            "qa": create_qa_workflow(),
            "diagnosis": create_diagnosis_workflow()
        }
    
    def run(self, mode, use_static, use_dynamic, user_input):
        """
        mode: "practice" | "qa" | "diagnosis"
        use_static: bool (是否使用结构化知识库)
        use_dynamic: bool (是否使用动态知识库)
        user_input: 用户输入
        """
        # 构建状态
        state = {
            "messages": [HumanMessage(content=user_input)],
            "use_static_kb": use_static,
            "use_dynamic_kb": use_dynamic,
            "user_id": "user_001"
        }
        
        # 选择工作流
        workflow = self.workflows[mode]
        
        # 执行
        result = workflow.invoke(state)
        
        return result
```

---

## 📝 **开题报告怎么写？**

### **第4章 系统设计 - 4.2 知识库设计**

```markdown
#### 4.2.1 双知识库架构

本系统采用**结构化知识库 + 动态知识库**的设计：

1. **结构化知识库**（静态 + 可查询）
   - 内容：历年真题（JSON格式）、考研大纲、新闻联播（AI处理）
   - 存储：FAISS向量库 + SQLite元数据表
   - 特点：支持混合检索（语义检索 + 元数据过滤）

2. **动态知识库**（用户个人）
   - 内容：Obsidian笔记、OCR识别的错题、上传的PDF
   - 存储：Chroma向量库（支持增量更新）
   - 特点：每个用户独立的向量空间

#### 4.2.2 用户可选知识库机制

用户在提问时可灵活选择使用哪些知识库：
- 仅使用结构化库：适合查询真题、大纲
- 仅使用个人库：适合复习笔记、错题
- 两者结合：全面检索

#### 4.2.3 新闻联播智能处理

政治时事新闻通过爬虫 + AI处理流程：
1. 爬取新闻联播文本
2. LLM提取摘要和知识点标签
3. 结构化存储（JSON → SQLite）
4. 向量化后加入FAISS索引
```

---

### **第4章 系统设计 - 4.3 多模式Agent工作流**

```markdown
#### 4.3.1 三种工作模式

系统根据用户选择的模式，加载不同的Agent工作流：

1. **刷题模式**（借鉴费曼学习法）
   - Agent组合：Router → Student/Teacher
   - 适用场景：题目讲解、错题分析
   - 知识库：优先检索用户错题本

2. **问答模式**（RAG主导）
   - Agent组合：Question Classifier → RAG Agents → Answer Generator
   - 适用场景：知识点查询、概念解释
   - 知识库：根据用户勾选动态检索

3. **学习诊断模式**
   - Agent组合：Analyzer → Recommender
   - 适用场景：生成学习报告、推荐题目
   - 知识库：分析用户学习轨迹数据

#### 4.3.2 LangGraph工作流设计

使用LangGraph构建可切换的工作流：
- 条件路由：根据用户选择动态加载workflow
- 并行检索：同时查询多个知识库
- 状态管理：维护对话历史和用户选择
```

---

## ✅ **总结：您的方案优势**

| 决策 | 优势 |
|------|------|
| ✅ 只维护两个知识库 | 简化架构，降低维护成本 |
| ✅ 新闻联播AI处理成JSON | 统一数据格式，便于检索 |
| ✅ 用户可选知识库 | 灵活性强，适应不同场景 |
| ✅ 多模式Agent工作流 | 功能明确，避免混乱 |

---

## 🚀 接下来

您觉得这个方案如何？我们可以：
1. **开始写开题报告的具体章节**
2. **设计三种模式的详细Prompt**
3. **画完整的系统架构图（用draw.io）**

告诉我下一步想做什么！😊
______
```toc

```