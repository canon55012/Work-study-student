import os
import pathlib

def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default) not in ("0", "false", "False", "")

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

DOTENV_LOADED = False
DOTENV_ERROR = ""
try:
    from dotenv import load_dotenv
    DOTENV_LOADED = bool(load_dotenv(BASE_DIR / ".env"))
    if not DOTENV_LOADED:
        DOTENV_ERROR = f"找不到或讀不到 {BASE_DIR / '.env'}"
except Exception as _e:
    DOTENV_ERROR = f"{type(_e).__name__}: {_e}"

if not DOTENV_LOADED:
    import sys as _sys
    print(f" .env 未載入（{DOTENV_ERROR}）——設定將使用程式內預設值，"
          f"金鑰可能為空。直譯器：{_sys.executable}", file=_sys.stderr)

LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://140.110.160.178:8000/v1")
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "google/gemma-4-31b-it")
LOCAL_LLM_PROBE_TIMEOUT = float(os.getenv("LOCAL_LLM_PROBE_TIMEOUT", "6"))
LOCAL_LLM_TIMEOUT = float(os.getenv("LOCAL_LLM_TIMEOUT", "120"))
LLM_CONNECT_TIMEOUT = float(os.getenv("LLM_CONNECT_TIMEOUT", "3"))
LLM_COOLDOWN_SECONDS = float(os.getenv("LLM_COOLDOWN_SECONDS", "60"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "8192"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

EMBEDDING_ENABLED = os.getenv("EMBEDDING_ENABLED", "1") not in ("0", "false", "False", "")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", LOCAL_LLM_BASE_URL)
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", LOCAL_LLM_API_KEY)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_MIN_SIM = float(os.getenv("EMBEDDING_MIN_SIM", "0.35"))
EMBEDDING_TIMEOUT = float(os.getenv("EMBEDDING_TIMEOUT", "8"))

MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")
MCP_SERVER_HOST = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
MCP_SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8000"))

WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "5000"))

DEFAULT_REGION = os.getenv("DEFAULT_REGION", "AI-Trust")
REGIONS = ["AI-Cloud", "AI-Trust"]
REGION_LABELS = {"AI-Cloud": "AI-Cloud Region", "AI-Trust": "AI-Trust Region"}


def safe_region(region: str) -> str:
    r = (region or "").strip()
    return r if r in REGIONS else DEFAULT_REGION


DISK_RATES = {
    "AI-Cloud": {"SSD": 2.78, "HDD": 1.26, "系統碟": "另計（不含）"},
    "AI-Trust": {"SSD": 1.54, "HDD": 0.75, "系統碟": "已含"},
}

STORAGE_DISCOUNT_REGIONS = {"AI-Cloud"}


def disk_rate(region: str, disk_type: str) -> float:
    dt = (disk_type or "SSD").strip().upper()
    val = DISK_RATES.get(safe_region(region), {}).get(dt)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def storage_discount_applies(region: str) -> bool:
    return safe_region(region) in STORAGE_DISCOUNT_REGIONS

REGION_DISCOUNTS = {
    "AI-Cloud": {"企業": 1.0, "個人": 1.0, "學術": 0.7, "政府法人": 0.7, "國科會": 0.5},
    "AI-Trust": {"企業": 1.0, "個人": 1.0, "政府法人": 0.7, "國科會": 0.5, "學術": 0.5},
}

PLAN_TYPES = ["企業", "個人", "學術", "政府法人", "國科會"]
DEFAULT_PLAN_TYPE = os.getenv("DEFAULT_PLAN_TYPE", "個人")


PROJECT_CATEGORIES = {
    "MST": "國科會",
    "ACD": "學術",
    "GOV": "政府法人",
    "TRI": "政府法人",
    "ENT": "企業",
}
PROJECT_CATEGORY_LABELS = {
    "MST": "國科會計畫",
    "ACD": "學術計畫",
    "GOV": "政府機關計畫",
    "TRI": "法人機構計畫",
    "ENT": "企業計畫",
}

PROJECT_ACTIVE = "active"

QUOTA_ITEMS = [
    ("gpu", "GPU", "顆"),
    ("vcpu", "vCPU", "核"),
    ("memory_gb", "記憶體", "GB"),
    ("storage_gb", "儲存", "GB"),
    ("vm", "VM 台數", "台"),
]
QUOTA_WARN_RATIO = float(os.getenv("QUOTA_WARN_RATIO", "0.8"))


def discount_rate(region: str, plan_type: str) -> float:
    return REGION_DISCOUNTS.get(safe_region(region), {}).get(plan_type, 1.0)

PRICING_DISCLAIMER = (
    "晶創雲預計 2026/08/01 正式上線收費（TWCC 轉移用戶 2026/09/01 起）；"
    "此價目表為初步暫定價格，僅供參考，最終以實際收費公告為準。"
    "List Price 幣別為新台幣（5%營業稅已內含）。"
)

DATA_DIR = BASE_DIR / "data"
PRICING_CSV = str(DATA_DIR / "pricing.csv")
FAQ_CSV = str(DATA_DIR / "faq.csv")
PROJECTS_CSV = str(DATA_DIR / "projects.csv")
WORKLOAD_CSV = str(DATA_DIR / "workload_log.csv")

USERS_DIR = DATA_DIR / "users"
DEFAULT_USER = "default"


def safe_user(user_id: str) -> str:
    uid = "".join(c for c in (user_id or "").strip() if c.isalnum() or c in ("-", "_"))
    return uid or DEFAULT_USER


def user_dir(user_id: str) -> pathlib.Path:
    return USERS_DIR / safe_user(user_id)


def user_vm_csv(user_id: str) -> str:
    return str(user_dir(user_id) / "vm_instances.csv")


def user_history_csv(user_id: str) -> str:
    return str(user_dir(user_id) / "history.csv")


def list_users() -> list:
    if not USERS_DIR.exists():
        return []
    return sorted(d.name for d in USERS_DIR.iterdir() if d.is_dir())


LOGS_DIR = DATA_DIR / "logs"
TOOL_CALL_LOG = str(LOGS_DIR / "tool_calls.jsonl")
FAQ_MISS_LOG = str(LOGS_DIR / "faq_misses.jsonl")

LLM_STATE_FILE = str(DATA_DIR / "llm_state.json")

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _provider(pid, label, kind, base_url, api_key, model, enabled=True):
    return {"id": pid, "label": label, "kind": kind, "base_url": base_url,
            "api_key": api_key, "model": model, "enabled": bool(enabled)}


LLM_PROVIDERS = [
    _provider("local", "本地LLM", "openai",
              LOCAL_LLM_BASE_URL, LOCAL_LLM_API_KEY, LOCAL_LLM_MODEL,
              enabled=_flag("LOCAL_LLM_ENABLED", "1")),
    _provider("claude", "Claude", "anthropic",
              "", ANTHROPIC_API_KEY, CLAUDE_MODEL,
              enabled=_flag("CLAUDE_ENABLED", "1")),
    _provider("openai", "OpenAI", "openai",
              OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL,
              enabled=_flag("OPENAI_ENABLED", "0")),
]

DEFAULT_LLM_ORDER = [p["id"] for p in LLM_PROVIDERS if p["enabled"]]
