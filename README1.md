# MCP Agent + PINN Tool Calling

本專案實作 **MCP（Model Context Protocol）架構**，整合：

* MCP Server（工具服務）
* MCP Client / Agent（LLM 推理與工具調用）
* Prompt 管理
* Physics-Informed Neural Network（PINN）
* 一維 Heat Equation 範例

用於驗證 **LLM + MCP + Tool Calling + PINN** 之整合流程，讓使用者可以透過自然語言訓練模型、查詢解、產生切片及計算誤差。

<br />

<p align="center">

<h3 align="center">MCP Agent + PINN Integration</h3>

<p align="center">
MCP Server 提供 PINN 工具，Agent 負責推理並自動呼叫工具，
形成完整的 LLM Tool Calling 架構。
<br />
<br />
</p>

</p>

---

## 目錄

* [上手指南](#上手指南)

  * [配置要求](#配置要求)
  * [安裝步驟](#安裝步驟)
* [專案架構](#專案架構)
* [功能介紹](#功能介紹)
* [整體流程](#整體流程)
* [測試方式](#測試方式)
* [作者](#作者)

---

# 上手指南

## 配置要求

1. Python 3.10+
2. pip
3. Ubuntu / Linux（建議）
4. OpenAI Compatible API（如 Ollama）
5. Docker（可選，用於 MCP Server Container）

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

---

# 專案架構

```text
Work-study-student/
│
├── agent/                 # Agent 推理核心
├── mcp_server/            # MCP Server
│   ├── tools/             # PINN Tools
│   ├── registry.py
│   └── server.py
│
├── mcp_client/            # MCP Client
├── prompt/                # Prompt Templates
├── rag/                   # Retrieval / LLM
├── config/                # 設定檔
│
├── main.py                # Agent Entry
├── requirements_llm.txt
├── test.txt               # 測試指令
├── heat1d.pt              # 訓練模型
├── slice.json             # Slice 輸出
└── README.md
```

---

# 功能介紹

目前提供四個 MCP Tool。

| Tool            | 功能                     |
| --------------- | ---------------------- |
| `train_heat_1D` | 訓練 Heat Equation PINN  |
| `query_u`       | 查詢指定 `(x,t)` 的預測值      |
| `slice_t`       | 固定時間產生空間切片並輸出 JSON     |
| `compute_error` | 計算 PINN 與解析解的 L2 Error |

---

# 整體流程

```text
User Input
      │
      ▼
   Agent (main.py)
      │
      ▼
      LLM
      │
      ▼
判斷是否需要 Tool
      │
      ├──────── No
      │
      ▼
Direct Response
      │
      └──────── Yes
               │
               ▼
         MCP Client
               │
               ▼
         MCP Server
               │
               ▼
          PINN Tools
               │
               ▼
        Tool Execution
               │
               ▼
         Return Result
               │
               ▼
        Final Response
```

---

# 測試方式

可直接參考 `test.txt`。

## 1. 訓練模型

```text
train_heat_1D(alpha=0.1,epochs=1000)
```

---

## 2. 查詢模型

```text
query_u(x=0.3,t=0.5)
```

---

## 3. 產生切片

```text
slice_t(t=0.5)
```

---

## 4. 計算誤差

```text
Compute error with alpha=0.1
```

---

# 作者

Eric
