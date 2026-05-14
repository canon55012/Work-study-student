# MCP Agent + Server 整合專案

本專案為 MCP（Model Context Protocol）架構實作，整合：

- MCP Server（工具服務端）
- MCP Client / Agent（推理與工具調用端）
- RAG 模組（檢索增強生成）
- Prompt 管理
- Pipeline 整合測試

用於驗證「LLM + Tool Calling + Server 架構」之整合流程。

<br />

<p align="center">

  <h3 align="center">MCP Agent + Server Integration</h3>

  <p align="center">
    MCP Server 提供工具能力，Agent 負責推理與調用工具，形成完整 LLM 工具鏈架構
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
4. Ollama（如有使用 LLM 本地模型）
   - version >= 0.3.11
5. Docker（可選，用於 MCP Server container 化）

---

## 安裝步驟

### 1️⃣ 建立虛擬環境

```bash
python3 -m venv venv
