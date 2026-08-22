# 可信賴雲 AI Agent

| 項目 | 內容 |
| --- | --- |
| 文件版本 | 1.0 |
| 專案性質 | 原型（prototype），非上線系統 |
| 技術架構 | MCP（Model Context Protocol）串接 LLM 推理與工具執行 |
| 系統架構文件 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |

以 MCP 實作的雲端方案 AI Agent，整合可切換的 LLM 供應商、工具呼叫與使用者資料隔離
LLM 僅負責決策，實際動作（查價、VM 生命週期、計費、知識庫檢索、成本最佳化求解）
由 MCP Server 上的 30 個工具執行

## 目次

| 節 | 內容 |
| --- | --- |
| [專案定位與資料邊界](#專案定位與資料邊界) | 各項數據的來源與適用範圍 |
| [環境需求](#環境需求)・[安裝](#安裝)・[設定](#設定) | 部署前準備 |
| [啟動](#啟動) | 網頁版／命令列版 |
| [測試與驗證](#測試與驗證) | smoke test、最佳化驗證、論文模型 |
| [專案架構](#專案架構) | 目錄結構 |
| [可用工具](#可用工具mcp-tools) | 30 個 MCP 工具、計價與折扣規則、FAQ 檢索 |
| [平台能力](#平台能力) | 供應商切換、計費、錢包、計畫 Quota、最佳化、隔離、觀測 |
| [整體流程](#整體流程) | 一則請求的處理順序 |

## 專案定位與資料邊界

本系統為可完整展示、具自動化測試的原型，非已上線系統。以下說明各項數據的來源與適用範圍

- **有外部依據的**：`data/pricing.csv` 的價目、稅、差別費率折扣、分區規則、收費時程
  皆對照官方價目表（qa_code=839）逐格核對過。
- **自訂的**：VM 為 CSV 模擬；錢包的結算規則；FAQ 知識庫內容與評估題目；
  `data/projects.csv` 的計畫、成員與 Quota 額度——**該檔為示範資料**（3 個計畫，涵蓋國科會／學術／企業三種計畫別，含一個 expired 計畫以示範狀態把關），接真實計畫系統時整份替換即可
- **因此**：`smoke_test` 108 項、`test_optimize` 40 項、FAQ `53/53`、工具選擇 `8/8`
  驗的是**系統行為與內部一致性**，**不等於**對真實平台或真實使用者的效度
- **最佳化的邊界**：`optimize_plan_mix` 只做「**成本覆蓋最佳化**」
  **無法做效能最佳化、無法改善吞吐量**。論文的吞吐量係數 `h(c,w)` 已於 2026-08-16
  對真實 vLLM endpoint **實測到一欄且推到飽和**（`paper/profile_vllm.py`）
  但 `|C| = 1` 不是矩陣——而 `|C| = 1` 時論文的式 2、式 4 本來就恆成立
  **沒有配置可選**，不足以支撐效能最佳化的宣稱。
- **環境限制**：本地模型端點需 VPN，且未打通到 Windows 端。因此 Tier 0 語意檢索無法實際啟用
  （自動退回 TF-IDF），歷來 demo 皆由外部 API 代跑——架構圖上的「本地 LLM」目前是**設計目標**

## 環境需求

- Python 3.10+
- pip
- Ubuntu / Linux 環境（建議）
- 連線本地 LLM 前需先連上 VPN

## 安裝

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 設定

所有設定集中在專案根目錄的 `.env`，由 `config/settings.py` 統一讀取。本地 LLM 三個參數為必填，其餘選填：

```
ANTHROPIC_API_KEY=...        # Claude 備援金鑰
LOCAL_LLM_BASE_URL=...       # 本地 LLM 端點
LOCAL_LLM_API_KEY=...        # 本地 LLM 金鑰
LOCAL_LLM_MODEL=...          # 本地 LLM 模型名稱
```

`.env` 含金鑰，已列入 `.gitignore`，請勿提交

```
OPENAI_ENABLED=1                       # 開啟 OpenAI 供應商
OPENAI_API_KEY=...                     # OpenAI 金鑰
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
# LOCAL_LLM_ENABLED / CLAUDE_ENABLED 亦可設 0 關閉對應供應商
```

供應商註冊表在 `config/settings.LLM_PROVIDERS`，要加第三家（如自架 vLLM）在此加一筆
即可，探測與切換自動涵蓋

## 啟動

### 網頁版（建議）

```bash
run_web.bat          # 或：python scripts/start_web.py
```

### 命令列版

適用於僅有 SSH 的環境。需開兩個終端機，先 Server 後 Agent，皆從專案根目錄執行

```bash
uvicorn mcp_server.server:app --host 0.0.0.0 --port 8000 --reload   # 終端機 1
python main.py                                                      # 終端機 2
```



## 測試與驗證

自動化 smoke test（驗證平台能力，可進 CI）：

```bash
python scripts/smoke_test.py            # 離線層 108 項：供應商狀態機/VM 生命週期/計費/錢包/計畫Quota/知識客服/工具可達性/最佳化/負載紀錄/隔離/觀測/Flask 端點
python scripts/smoke_test.py --live     # 額外測 MCP Client→Server 實呼工具（需先啟動 server）
python scripts/smoke_test.py --llm      # 額外測真實 LLM 生成（需 VPN/金鑰）
```

最佳化專項驗證：

```bash
python scripts/test_optimize.py         # 40 項：覆蓋/預算/磁碟/兩區折扣規則/混搭門檻/與窮舉交叉比對
python paper/milp.py            # 論文完整模型（式 1–7）跑論文例子得 28.67s ＋ 五步化簡與 to_milp() 逐項比對
```

## 專案架構

```
Eunice_mcp-agent/
│
├── web.py                  # 網頁版進入點
├── main.py                 # 命令列版進入點
├── admin.py                # 管理介面
├── run_web.bat             # 網頁版啟動器
├── requirements.txt        # 執行期相依套件
│
├── agent/                  # Agent 推理核心
│   ├── providers.py        #   LLM 供應商註冊表
│   ├── llm.py              #   LLM 用戶端相容層
│   ├── core.py             #   組裝訊息、解析 LLM 輸出、忠實度閉環
│   └── tools.py            #   工具呼叫封裝
│
├── common/                 # 共用基礎設施
│   ├── storage.py          #   跨行程檔案鎖、JSONL 記錄
│   ├── accounts.py         #   帳號身分
│   ├── projects.py         #   計畫與 Quota
│   ├── wallet.py           #   錢包餘額與交易
│   ├── workload.py         #   每次 LLM 呼叫的 token 用量（f_w）
│   └── observability.py    #   工具呼叫與 FAQ 未命中記錄
│
├── config/settings.py      # 集中設定
├── prompt/system_prompt.py # System prompt
├── rag/faq.py              # FAQ 分層檢索（embedding → TF-IDF → 關鍵字）＋ 忠實度檢核
│
├── mcp_client/client.py    # MCP Client 連線封裝
├── mcp_server/
│   ├── server.py           #   MCP Server
│   └── tools/              #   pricing / vm_lifecycle / projects / optimize / …
│
├── paper/                  # 論文對應的實作與量測
│   ├── milp.py             #   論文 MILP 四項實驗（E1–E4）
│   ├── profile_vllm.py     #   量測 h(c,w)
│   ├── fw_from_metrics.py  #   由 vLLM /metrics 推算 f_w
│   ├── verify_slides.py    #   核對引用數字與量測檔是否一致
│   ├── vllm_profile_sat.json  # 正式採用的量測結果
│   └── 2502.00722v2.pdf
│
├── scripts/                # 維運與測試
│   ├── start_web.py        #   啟動流程
│   ├── smoke_test.py       #   端到端 smoke test（離線 108 項）
│   ├── test_optimize.py    #   最佳化模型測試
│   ├── eval_faq.py         #   FAQ 檢索命中率與接地檢核
│   ├── probe_tool_selection.py  # 量 LLM 是否選對工具
│   ├── pricing_watch.py    #   價目表變動監看
│   └── workload_report.py  #   負載紀錄彙整（f_w 分布）
│
├── data/                   # 價目、FAQ、各使用者資料、記錄
│   ├── pricing.csv         #   價目表
│   ├── faq.csv             #   FAQ 知識庫
│   ├── workload_log.csv    #   f_w 累積中
│   ├── users/<id>/         #   每位使用者的 VM 與查詢歷史
│   └── logs/               #   工具呼叫、FAQ 未命中
│
├── docs/
│   └──ARCHITECTURE.md     #   系統架構與執行 pipeline
│
├── .env                    # 金鑰與端點
├── .gitignore
└── README.md
```

## 可用工具（MCP Tools）

| 類別 | 工具 | 功能 |
| --- | --- | --- |
| 報價 | `query_pricing(keyword, region)` | 查詢方案報價，可用關鍵字篩選 |
| 報價 | `recommend_server(vcpu, memory_gb, need_gpu, region)` | 依規格需求推薦方案 |
| 報價 | `compare_plans(plan_a, plan_b, region)` | 比較兩方案的規格、價格與月費差異 |
| 報價 | `estimate_cost(plan, hours_per_day, days, region, disk_gb, disk_type)` | 估算特定使用情境下的總花費 |
| 報價 | `estimate_storage_cost(disk_gb, disk_type, months, region)` | 估算加購磁碟費用） |
| 報價 | `plan_budget(budget, plan, region, hours_per_day)` | 反向試算：給預算回可跑多久 |
| 報價 | `compare_regions(plan, hours_per_day, days)` | 跨區比價：套身分折扣後指出哪一區便宜、差多少 |
| **最佳化** | `optimize_plan_mix(vcpu, memory_gb, gpu_count, budget, hours_per_day, days, region)` | 成本最佳化：需求（vCPU／記憶體／GPU／磁碟）＋預算下求總費用最低的機型組合。寫成 MILP 標準式交由 HiGHS 求解（無 scipy 時退回內建分支定界）；磁碟為連續變數，模型為真正的 Mixed-Integer。混搭省不到 3% 會改建議單一機型 |
| 行為 | `log_query(query_type, keyword, selected_plan, note)` | 記錄使用者查詢行為 |
| 行為 | `get_user_history(limit)` | 查看最近的查詢記錄 |
| 行為 | `get_recommendations()` | 依歷史記錄統計推薦 |
| 行為 | `analyze_usage()` | 用 AI 分析使用偏好 |
| VM | `create_vm` / `start_vm` / `stop_vm` / `maintain_vm` / `delete_vm` / `list_vms` / `get_vm` | 模擬 VM 生命週期 |
| 計費 | `get_vm_bill(vm_id)` | 單機累計運行時數與費用 |
| 計費 | `get_account_bill()` | 帳戶所有 VM 的總費用＋錢包餘額與剩餘天數 |
| 成本顧問 | `suggest_savings(business_hours)` | 成本健檢：找出運行中在燒錢的 VM，算排程關機每月省多少、標長時間連續運行 |
| 錢包 | `get_wallet_balance()` | 預付餘額＋依運行中機器每日燃燒率推估餘額耗盡日 |
| 錢包 | `top_up_wallet(amount)` | 儲值：把金額加進錢包餘額 |
| 錢包 | `list_transactions(limit)` | 交易明細：儲值與扣抵流水帳 |
| 計畫 | `list_projects()` | 參與哪些計畫（類別、狀態、核定額度、額度使用摘要，標示使用中） |
| 計畫 | `get_project(project_id)` | 計畫詳情＋掛在該計畫底下的資源明細 |
| Quota | `get_quota(project_id)` | 各服務額度的核定／已用／剩餘與使用率，達 80% 與用罄有警示 |
| 知識庫 | `search_faq(question)` | 從本地 FAQ 知識庫檢索回答依據 |
| 一般 | `get_current_time()` | 取得目前日期時間 |


### 雲端區域（Region）與計價

價目分兩區，`data/pricing.csv` 以 **Region 欄**區分，同方案兩區價格可能不同：

- **AI-Cloud Region**：GPU 為 H200（H200.small/large、H200.vGPU）；系統碟**另計**（不含）；
  磁碟 SSD $2.78／HDD $1.26（每 GB/月）
- **AI-Trust Region**（預設）：H100 與 H200 全系列＋vGPU；系統碟**已含**；
  磁碟 SSD $1.54／HDD $0.75（每 GB/月）

報價/推薦/比較/估算/建立 VM 都可帶 `region`（AI-Cloud 或 AI-Trust），不填用
`settings.DEFAULT_REGION`。Web 右上角可切換區域（X-Region 標頭），VM 建立時記下所屬區域
計費依該區費率。要改價目直接編 `data/pricing.csv`，程式不需更動

> **兩個「記憶體」欄位**：`記憶體(GB)` 是**主機 RAM**（H100.small 為 512GB）
> `顯存(GB)` 才是 **GPU VRAM**（H100.small 為 80GB）

**GPU 顯存與頻寬欄位的來源**（`顯存(GB)`、`顯存頻寬(GB/s)`，皆為該方案的合計值，
與 `記憶體(GB)`／`vCPU` 的計法一致——兩張卡即兩倍）：

| 卡別 | 整卡顯存 | 整卡頻寬 | 依據 |
| --- | --- | --- | --- |
| H100 SXM5 | 80 GB HBM3 | 3,350 GB/s | NVIDIA 官方規格 |
| H200 SXM | 141 GB HBM3e | 4,800 GB/s | NVIDIA 官方規格 |

vGPU 切片以**單一規則**換算，不另外查表：`頻寬 ＝ (該方案顯存 ÷ 整卡顯存) × 整卡頻寬`

### 帳號身分（計畫別）與差別費率折扣

每個帳號帶一種**計畫別身分**（企業／個人／學術／政府法人／國科會），存於
`data/users/<id>/profile.json`。**差別費率折扣**依「身分 × 區域」自動套用（兩區規則不同）：

- AI-Cloud：企業/個人 牌價、學術/政府法人 7折、國科會 5折
- AI-Trust：企業/個人 牌價、政府法人 7折、國科會/學術 5折

`estimate_cost`、`get_vm_bill`、`get_account_bill` 與 `/admin` 都會顯示**牌價與折扣後實收**
（例：國科會的 H100.small 帳單 $349.92 → 實收 $174.96）。Web 右上角「身分」下拉可切換
（`/api/profile`），LLM 不需自己算折扣、如實轉述工具回傳即可。折扣表在 `settings.REGION_DISCOUNTS`。

> **儲存計價**：新制系統碟預設 120GB，需要更多空間**按 GB 加購**（SSD/HDD，費率依區域）
> 不再有 `.disk+` 方案變體。
>
> 價格免責：此為初步暫定價格，僅供參考，最終以實際收費公告為準
> （晶創雲預計 2026/08/01 上線收費，TWCC 轉移用戶 2026/09/01 起）。幣別新台幣、5%營業稅已內含

### FAQ 檢索（RAG）

`search_faq` 採三層檢索，由上而下嘗試，某層不可用才退下一層，與本專案 LLM 的 fallback 同規範：

1. **Tier 0（最佳）**：語意檢索（embedding + 餘弦相似度）
   - 聽得懂同義詞（顯卡≈GPU、划算≈便宜），突破字面比對的天花板
   - 走 OpenAI 相容的 `/embeddings`（設定見下），連不上或未裝 `openai` 自動退下一層
2. **Tier 1（次佳）**：TF-IDF + 餘弦相似度（sklearn，字元 n-gram，免中文斷詞）
3. **Tier 2（後備）**：關鍵字命中 + 字元 bigram 重疊

三層均無結果時回傳「查無相關」，並要求 LLM 據實告知，不得自行補充

**忠實度檢核（生成端）**：用過 `search_faq` 後，`main.py` / `web.py` 會以
`rag.faq.check_grounding()` 比對回答是否「超出」檢索內容，疑似杜撰會標記提醒——
把「忠實原則」從口頭提醒升級成可程式驗證的檢核

**語意檢索設定**（`.env`，選填；不設則沿用本地 LLM 端點，連不上自動退回 TF-IDF）：

```
EMBEDDING_ENABLED=1                         # 設 0 可關閉語意檢索
EMBEDDING_BASE_URL=...                       # 預設沿用 LOCAL_LLM_BASE_URL
EMBEDDING_API_KEY=...                        # 預設沿用 LOCAL_LLM_API_KEY
EMBEDDING_MODEL=text-embedding-3-small       # embedding 模型名稱
EMBEDDING_MIN_SIM=0.35                        # 語意相似度門檻（可調）
```

**評估**：改動知識庫或檢索邏輯後請重跑，會印出命中率、實際服務後端與忠實度檢核示範：

```bash
python scripts/eval_faq.py
```

## 平台能力

以下功能對應「多使用者、可切換、可查核」的營運需求，並沿用「優先使用最佳路徑，不可用時自動降級」的一致原則

### 可切換的 LLM 供應商

- 供應商註冊表（`agent/providers.py` + `settings.LLM_PROVIDERS`）：本地 / Claude / OpenAI
- 探測會明確區分狀態：**可用 / 無法連線 / 金鑰無效 / 額度不足 / 速率受限 / 套件未安裝 / 未啟用**
- Web 右上角可下拉切換與「測試連線」，即時顯示每家狀態與切換結果；串流中若自動回退會明示改用了誰
- 選用狀態寫入 `data/llm_state.json`，跨行程共用

### 計費模組

- 只有 VM 處於 running 才計費；進入 running 記起點，離開（關機/維護/刪除）結算該段用量
  查詢時運行中會把即時未結算用量一併算上。費率取自方案時價（與報價同一事實來源）
- 工具：`get_vm_bill(vm_id)`（單機帳單）、`get_account_bill()`（帳戶總覽）

### 錢包

- **錢包實體**在 `common/wallet.py`：儲值（正向交易）與扣抵（負向交易）記在
  `data/users/<id>/wallet.jsonl`；**餘額＝所有交易金額之和**，避免與流水帳不同步
- **計費改走錢包扣抵**：VM 每段運行在「離開 running 結算」時（關機/維護/刪除），把該段
  **實收費用**（依身分×區域折扣）記成一筆扣抵；仍在 running、尚未結算的費用屬 **pending**
  （未入帳）。三者恆等：`已扣抵 + pending = get_account_bill 的實收總額`
- **burn rate 推估耗盡日**：`get_wallet_balance()` 以「可用餘額（餘額 − pending）÷ 每日實收
  燃燒率」推估還能用幾天、哪天耗盡；`get_account_bill()` 帳單尾也一併顯示「從錢包扣、剩餘 N 天」
- 工具：`get_wallet_balance()`、`top_up_wallet(amount)`、`list_transactions(limit)`

### 計畫與 Quota

- **計畫實體**在 `common/projects.py`（資料在 `data/projects.csv`）：計畫帶
  **類別代碼**（MST 國科會／ACD 學術／GOV 政府／TRI 法人／ENT 企業）、狀態、期間
  核定額度、成員、Tenant Admin 與各服務 quota
- **計畫別「從計畫讀」**：帳號的計畫別（決定差別費率折扣）由**所屬計畫的類別**決定
  接點仍是 `accounts.plan_type()` 一處，下游計費/錢包完全不動
- **Quota 用量不另存數字**：一律由該計畫底下未刪除的 VM 規格即時加總（GPU／vCPU／
  記憶體／儲存／VM 台數），與錢包「餘額＝交易之和」同一套設計，杜絕「已用」與實際資源不同步
- **額度與計費的界線不同**：已關機／維護中的機器**仍佔額度**（資源仍配置著）但**不計費**，
  刪除才釋放；`create_vm` 在建立前就檢查計畫狀態與額度，不足即擋下並指出是哪一項
- 工具：`list_projects()`、`get_project(project_id)`、`get_quota(project_id)`

### 資源最佳化

`recommend_server` 只能在既有方案中挑**一個**，答不出需要混搭的題目（「64 核 / 256GB」
會直接回「沒有符合條件的方案」）。`optimize_plan_mix` 補上這一段：**給定需求與預算
求總費用最低的機型組合**

```
論文完整模型（式 1–7）→ 用論文自己的例子驗證 → 五步化簡 → 本專案模型
    → 擴充 storage 維度 → MILP Formulation → Solver → 三方交叉驗證
```

- **完整模型不上線但保留**（`paper/milp.py`）：式 1–7 ＋ 附錄 F 全部寫出來且可執行
  以論文 §4.2 例子**重現 28.67 s ＝ 論文報告值**。吞吐量係數 `h(c,w)` 已實測且飽和
- **化簡有沒有走樣是可查證的**：`paper/milp.py` 依五步**獨立重建**一次，
  與 `optimize.to_milp()` 逐項比對目標係數／約束矩陣／上下界／整數旗標／變數上下界——**8 項全同**
- **模型與求解器解耦**：`to_milp()` 產生標準式（決策變數 `x_n ∈ ℤ≥0`＝各方案開幾台
  `s ∈ ℝ≥0`＝加購磁碟 GB；目標 `min Σ p_n·x_n + r·s`；約束為三項資源覆蓋 ＋ 磁碟 ＋ 預算 ＋ 台數上限）
  **加入連續的磁碟變數後，模型才是真正的 Mixed-Integer。**
- **求解走 HiGHS**（`scipy.optimize.milp`，**零新依賴**）
  回覆一律標明求解器：`求解：HiGHS（scipy.optimize.milp）`
- **系統碟刻意不折抵**：它綁在各自機器上、**無法跨機器合併成單一磁碟區**
- **3% 混搭門檻**：省不到 3% 就改建議單一方案。
  實測純 CPU/RAM 情境混 4 種機型只省 **0.1%（$36）**
  無限制的成本最小化會給出運維不可行的解。
- **上線版**：不含吞吐量與部署配置維度、**無改善吞吐量**

> 論文的另一組輸入 `f_w`（各類負載請求佔比），已開始累積：
> 每次生成自動記錄輸入／輸出 token 數（`common/workload.py` → `data/workload_log.csv`），
> 分桶沿用論文 Figure 3/4 的九種負載
> 報表：`python scripts/workload_report.py`。

### 使用者隔離

- 每位使用者的 VM 與查詢歷史各自存於 `data/users/<user_id>/`，互不干擾
- 身分由前端 `X-User-Id` 標頭帶入（存 localStorage），Agent 執行期自動注入工具參數
  **LLM 完全不經手 user_id**；對話記憶亦按使用者分開
- **接實體環境時只改一處**：身分來源集中在 `web.py` 的 `current_user()`（區域為 `current_region()`）
  把「信任 `X-User-Id` 標頭」換成「從驗證過的 session/token 取得使用者」即可，下游的隔離
  計費、折扣都吃這個值。目前標頭可被偽造，**正式對外前務必先接真 auth**

### 管理介面

- 瀏覽 `http://127.0.0.1:5000/admin`：一頁彙整 **LLM 供應商狀態 / 各使用者 VM 與計費 /
  工具呼叫記錄 / FAQ 未命中**，每 10 秒自動刷新

### 可觀測性

- **工具呼叫記錄**：每次呼叫（使用者、工具、參數、成敗、耗時、結果摘要）寫入
  `data/logs/tool_calls.jsonl`，CMD/Web 版皆涵蓋
- **FAQ 未命中記錄**：`search_faq` 查無相關時，把問題與當下檢索後端寫入
  `data/logs/faq_misses.jsonl`，資料驅動地知道知識庫該補哪些題目
- 底層以 `common/storage.py` 的跨行程檔案鎖保護所有 CSV/JSONL 讀改寫，避免並發壞檔

## 整體流程

```
使用者輸入
   ↓
Agent（main.py / web.py）
   ↓
LLM 推理（agent/llm.py + agent/core.py）
   ↓
判斷是否需要工具
   ↓
MCP Client 送出請求（mcp_client）
   ↓
MCP Server 執行工具（mcp_server）
   ↓
回傳結果
   ↓
最終回答
```

