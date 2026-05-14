# MCP Agent + Server 測試用範例

本專案為 MCP（Model Context Protocol）架構實作，整合：

- MCP Server（工具服務端）
- MCP Client / Agent（推理與工具調用端）
- Prompt 管理
- Pipeline 整合測試

用於驗證「LLM + Tool Calling + Server 架構」之整合流程。

<br />

<p align="center">

  <h3 align="center">MCP Agent + Server Integration</h3>

  <p align="center">
    MCP Server 彙整工具，Agent 負責推理與調用工具，形成完整 LLM 架構
    <br />
    <br />
  </p>

</p>

---

## 目錄

- [上手指南](#上手指南)
  - [配置要求](#配置要求)
  - [安裝步驟](#安裝步驟)
- [文件目錄說明](#文件目錄說明)
- [用途](#用途)
- [部署](#部署)
- [版本控制](#版本控制)
- [作者](#作者)

---

## 上手指南

### 配置要求

1. Python 3.10+
2. pip
3. Ubuntu / Linux 環境（建議）
4. Docker（可選，用於 MCP Server container 化）

---

## 安裝步驟

### 1️ 建立虛擬環境

```bash
python3 -m venv Work-study-student
```

### 2️ 進入虛擬環境並安裝所需library

```bash
source Work-study-student/bin/activate

cd Work-study-student

pip install -r requirements_llm.txt
```

### 3 啟動 MCP Server

```bash
uvicorn mcp_server.server:app --host 0.0.0.0 --port 8000 --reload
```

### 4 啟動 MCP Agent

```bash
source Work-study-student/bin/activate

cd Work-study-student

python main.py
```

## 專案架構

```bash
llm_agent/
│
├── agent/                 # Agent core（推理 / tool calling）
├── mcp_server/            # MCP Server（API service）
├── mcp_client/            # Client 呼叫層
├── rag/                   # 檢索增強模組
├── prompt/                # prompt templates
├── config/                # 設定檔
│
├── main.py                # Agent entry point
├── requirements_llm.txt   # 依賴套件
├── .gitignore
└── README.md
```

## 整體流程

```bash
User Input
   ↓
Agent (main.py)
   ↓
LLM / Router
   ↓
判斷是否需要 tool
   ↓
MCP Client request
   ↓
MCP Server execution
   ↓
return result
   ↓
final response
```


