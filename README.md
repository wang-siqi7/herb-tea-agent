# 中药茶饮智能顾问 Agent

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![LangChain](https://img.shields.io/badge/langchain-0.3+-orange.svg)](https://python.langchain.com/)

一个基于 LangChain + LangGraph 的中药茶饮智能顾问 Agent。通过 ReAct 循环自主调用工具，实现体质辨识、茶饮推荐和个性化养生报告生成。

## 技术栈

- **框架**: LangChain + LangGraph
- **向量库**: ChromaDB + 通义千问 Embedding
- **模型**: 通义千问 qwen3-max
- **前端**: Streamlit

## 核心能力

### 🤖 1. ReAct Agent 自主决策
Agent 遵循「思考 → 行动 → 观察 → 再思考」循环，自主决定调用 5 个工具。

### 🔄 2. 动态提示词切换
中间件根据 `context["report"]` 标志动态切换系统提示词，报告场景自动使用专用模板。

### 📚 3. RAG 系统优化
- **MD5 去重**: 避免知识库重复向量化
- **智能分块**: `RecursiveCharacterTextSplitter`，chunk_size=200
- **检索增强**: k=3 返回最相似的 3 个文档块

### 📊 4. 中间件监控
- `monitor_tool`: 记录工具调用日志
- `log_before_model`: 记录模型调用前状态
- 通过 `runtime.context` 在中间件间传递状态

## 项目结构

```
herb_tea_agent/
├── agent/          # Agent 核心（5个工具 + 3个中间件）
├── rag/            # RAG 模块（向量库 + 检索服务）
├── utils/          # 工具函数（路径、日志、配置、MD5去重）
├── data/           # 知识库（168份问卷 + 专家访谈）
├── prompts/        # 提示词模板
├── config/         # YAML 配置
└── app.py          # Streamlit 前端
```

## 数据来源

基于团队 2025 年西安市 Z 世代中药茶饮消费意愿调研的 **168 份真实问卷** + **2 场专家访谈**构建知识库。

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/wang-siqi7/herb-tea-agent.git
cd herb-tea-agent

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
export DASHSCOPE_API_KEY="your-key"

# 4. 初始化向量库
python -c "from rag.vector_store import VectorStoreService; VectorStoreService().load_document()"

# 5. 启动 Web 界面
streamlit run app.py
```
## 衍生项目

本项目的研究成果已用于构建：
- **[中药茶饮智能顾问 Agent](https://github.com/wang-siqi7/herb-tea-agent)**：面向消费者的智能茶饮推荐系统
  
## 测试示例

| 用户输入 | 系统响应 |
|----------|----------|
| 湿热体质适合喝什么茶？ | 菊花茶、金银花茶、薏米茶... 经典配方：菊花5g+金银花3g |
| 我手脚冰凉，容易疲劳 | 可能是阳虚体质，推荐姜枣茶（生姜3片+红枣3颗） |
| 帮我生成我的养生报告 | 生成包含体质分析、饮用建议、推荐配方的 Markdown 报告 |

