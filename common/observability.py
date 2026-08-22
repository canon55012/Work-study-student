from datetime import datetime

from config import settings
from common import storage


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_tool_call(user_id, tool, params, ok, latency_ms, result_preview=""):
    storage.append_jsonl(settings.TOOL_CALL_LOG, {
        "ts": _ts(),
        "user_id": user_id,
        "tool": tool,
        "params": params,
        "ok": bool(ok),
        "latency_ms": round(float(latency_ms), 1),
        "preview": (result_preview or "").replace("\n", " ")[:160],
    })


def read_tool_calls(limit=200):
    return storage.read_jsonl(settings.TOOL_CALL_LOG, limit)


def log_faq_miss(question, backend, user_id="anon"):
    storage.append_jsonl(settings.FAQ_MISS_LOG, {
        "ts": _ts(),
        "user_id": user_id,
        "question": (question or "").strip()[:200],
        "backend": backend or "unknown",
    })


def read_faq_misses(limit=200):
    return storage.read_jsonl(settings.FAQ_MISS_LOG, limit)


def maybe_log_weak_faq_miss(question, faq_context, grounding, user_id="anon"):
    if not faq_context or faq_context.startswith("知識庫中查無相關"):
        return False
    if grounding and grounding.get("ok"):
        return False
    log_faq_miss(question, "低相關(未接地)", user_id)
    return True
