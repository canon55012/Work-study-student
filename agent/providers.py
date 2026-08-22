"""LLM"""
import json
import os
import time

from config import settings
from common import storage

OK = "ok"
UNREACHABLE = "unreachable"
AUTH = "auth_error"
QUOTA = "quota_exceeded"
RATE = "rate_limited"
DISABLED = "disabled"
NO_SDK = "no_sdk"
ERROR = "error"

STATUS_ZH = {
    OK: "可用",
    UNREACHABLE: "無法連線",
    AUTH: "金鑰無效",
    QUOTA: "額度不足",
    RATE: "速率受限",
    DISABLED: "未啟用",
    NO_SDK: "套件未安裝",
    ERROR: "錯誤",
}

LAST_USED = None
LAST_USAGE = (0, 0)
LAST_ERRORS = []

_COOLDOWN = {}
_LONG_COOLDOWN = {UNREACHABLE, AUTH, QUOTA, NO_SDK}
_SHORT_COOLDOWN_SECONDS = 10.0


def _timeout(total: float):
    try:
        import httpx
        return httpx.Timeout(total, connect=settings.LLM_CONNECT_TIMEOUT)
    except Exception:
        return total


def _in_cooldown(pid: str) -> bool:
    until = _COOLDOWN.get(pid)
    return bool(until and time.time() < until)


def _mark_down(pid: str, status: str):
    secs = (settings.LLM_COOLDOWN_SECONDS if status in _LONG_COOLDOWN
            else _SHORT_COOLDOWN_SECONDS)
    _COOLDOWN[pid] = time.time() + secs


def _clear_cooldown(pid: str):
    _COOLDOWN.pop(pid, None)


def all_providers() -> list:
    return list(settings.LLM_PROVIDERS)


def get_provider(pid: str):
    for p in settings.LLM_PROVIDERS:
        if p["id"] == pid:
            return p
    return None


def _read_state() -> dict:
    try:
        with open(settings.LLM_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_state(state: dict):
    parent = os.path.dirname(settings.LLM_STATE_FILE)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with storage.file_lock(settings.LLM_STATE_FILE):
        with open(settings.LLM_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)


def active_id() -> str:
    state = _read_state()
    aid = state.get("active")
    p = get_provider(aid) if aid else None
    if p and p["enabled"]:
        return aid
    for p in settings.LLM_PROVIDERS:
        if p["enabled"]:
            return p["id"]
    return None


def active_label() -> str:
    p = get_provider(active_id())
    return p["label"] if p else "無"


def active_kind() -> str:
    p = get_provider(active_id())
    return p["kind"] if p else "openai"


def set_active(pid: str) -> tuple:
    p = get_provider(pid)
    if not p:
        return False, f"未知供應商：{pid}"
    if not p["enabled"]:
        return False, f"{p['label']} 未啟用（請於 .env 開啟並填金鑰）"
    state = _read_state()
    state["active"] = pid
    _write_state(state)
    _clear_cooldown(pid)
    return True, f"已切換至 {p['label']}"


def _client(p: dict):
    if p["kind"] == "anthropic":
        import anthropic
        kwargs = {}
        if p["api_key"]:
            kwargs["api_key"] = p["api_key"]
        return anthropic.Anthropic(**kwargs)
    from openai import OpenAI
    return OpenAI(base_url=p["base_url"], api_key=p["api_key"] or "none", max_retries=0)


def _classify(e: Exception) -> str:
    code = getattr(e, "status_code", None)
    name = type(e).__name__.lower()
    msg = str(getattr(e, "message", "") or e).lower()

    if isinstance(e, ImportError) or "no module named" in msg:
        return NO_SDK
    if "connection" in name or "timeout" in name:
        return UNREACHABLE
    if code == 401 or "authentication" in name or "permission" in name:
        return AUTH
    if code == 429 or "ratelimit" in name:
        if any(k in msg for k in ("insufficient_quota", "quota", "credit", "billing")):
            return QUOTA
        return RATE
    if isinstance(code, int) and 500 <= code < 600:
        return UNREACHABLE
    return ERROR


def probe(pid: str, timeout: float = None) -> dict:
    p = get_provider(pid)
    if not p:
        return {"id": pid, "label": pid, "status": ERROR, "detail": "未知供應商"}
    base = {"id": pid, "label": p["label"], "model": p["model"]}
    if not p["enabled"]:
        return {**base, "status": DISABLED, "detail": "未啟用（可在 .env 開啟）"}

    tmo = _timeout(timeout or settings.LOCAL_LLM_PROBE_TIMEOUT)
    t0 = time.time()
    try:
        c = _client(p)
        if p["kind"] == "anthropic":
            c.messages.create(model=p["model"], max_tokens=1,
                              messages=[{"role": "user", "content": "ping"}],
                              timeout=tmo)
        else:
            c.chat.completions.create(model=p["model"], max_tokens=1,
                                      messages=[{"role": "user", "content": "ping"}],
                                      timeout=tmo)
        _clear_cooldown(pid)
        return {**base, "status": OK, "detail": STATUS_ZH[OK],
                "latency_ms": round((time.time() - t0) * 1000, 1)}
    except Exception as e:
        st = _classify(e)
        return {**base, "status": st, "detail": STATUS_ZH.get(st, st),
                "error": str(e)[:200],
                "latency_ms": round((time.time() - t0) * 1000, 1)}


def probe_all() -> list:
    from concurrent.futures import ThreadPoolExecutor

    aid = active_id()
    ids = [p["id"] for p in settings.LLM_PROVIDERS]
    with ThreadPoolExecutor(max_workers=max(1, len(ids))) as ex:
        results = list(ex.map(probe, ids))
    for p, r in zip(settings.LLM_PROVIDERS, results):
        r["active"] = (p["id"] == aid)
        r["enabled"] = p["enabled"]
    return results


def _try_order() -> list:
    aid = active_id()
    ids = ([aid] if aid else []) + [
        p["id"] for p in settings.LLM_PROVIDERS if p["enabled"] and p["id"] != aid
    ]
    return ids


class _JsonSpotter:

    def __init__(self):
        self.buf = []
        self.started = self.in_str = self.esc = self.done = False
        self.depth = 0
        self.extra = 0

    def feed(self, chunk: str) -> int:
        for ch in chunk:
            self.buf.append(ch)
            if self.done:
                self.extra += 1
                continue
            if not self.started:
                if ch == "{":
                    self.started, self.depth = True, 1
                continue
            if self.esc:
                self.esc = False
            elif self.in_str:
                if ch == "\\":
                    self.esc = True
                elif ch == '"':
                    self.in_str = False
            elif ch == '"':
                self.in_str = True
            elif ch == "{":
                self.depth += 1
            elif ch == "}":
                self.depth -= 1
                if self.depth == 0:
                    self.done = True
        return self.extra

    def text(self) -> str:
        return "".join(self.buf)


_JSON_TAIL_GRACE = 40

PROGRESS = {"chars": 0, "streaming": False}


def _complete_anthropic(c, kw: dict) -> str:
    global LAST_USAGE
    sp = _JsonSpotter()
    in_tok = out_tok = 0
    PROGRESS.update(chars=0, streaming=True)
    with c.messages.stream(**kw) as stream:
        for ev in stream:
            etype = getattr(ev, "type", "")
            if etype == "text":
                PROGRESS["chars"] = len(sp.buf)
                if sp.feed(ev.text) > _JSON_TAIL_GRACE:
                    break
            elif etype == "message_start":
                u = getattr(getattr(ev, "message", None), "usage", None)
                in_tok = getattr(u, "input_tokens", 0) or 0 if u else 0
            else:
                u = getattr(ev, "usage", None)
                if u is not None:
                    out_tok = getattr(u, "output_tokens", 0) or out_tok
    LAST_USAGE = (in_tok, out_tok)
    PROGRESS.update(chars=len(sp.buf), streaming=False)
    return sp.text().strip()


def _usage_of(resp, kind: str) -> tuple:
    u = getattr(resp, "usage", None)
    if u is None:
        return 0, 0
    if kind == "anthropic":
        return getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0
    return getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0


def _complete(p: dict, messages: list, max_tokens: int = None) -> str:
    global LAST_USAGE
    PROGRESS.update(chars=0, streaming=False)
    max_tokens = max_tokens or settings.LLM_MAX_TOKENS
    c = _client(p)
    if p["kind"] == "anthropic":
        sys_txt, conv = None, []
        for m in messages:
            if m["role"] == "system":
                sys_txt = m["content"]
            else:
                conv.append(m)
        kw = {"model": p["model"], "max_tokens": max_tokens, "messages": conv,
              "timeout": _timeout(settings.LOCAL_LLM_TIMEOUT)}
        if sys_txt:
            kw["system"] = sys_txt
        return _complete_anthropic(c, kw)
    resp = c.chat.completions.create(
        model=p["model"], messages=messages,
        timeout=_timeout(settings.LOCAL_LLM_TIMEOUT),
    )
    LAST_USAGE = _usage_of(resp, "openai")
    return resp.choices[0].message.content.strip()


def chat(messages: list, user_id: str = "") -> str:
    global LAST_USED, LAST_USAGE, LAST_ERRORS
    order = _try_order()
    active = order[0] if order else None

    live = [pid for pid in order if pid == active or not _in_cooldown(pid)]
    if not live:
        _COOLDOWN.clear()
        live = order

    errs = []
    for pid in order:
        if pid not in live:
            p = get_provider(pid)
            errs.append(f"{p['label']}=稍早失敗，冷卻中暫時跳過")
            continue
        p = get_provider(pid)
        LAST_USAGE = (0, 0)
        t0 = time.time()
        try:
            txt = _complete(p, messages)
        except Exception as e:
            st = _classify(e)
            _mark_down(pid, st)
            detail = " ".join(str(getattr(e, "message", "") or e).split())
            errs.append(f"{p['label']}={STATUS_ZH.get(st, 'error')}"
                        + (f"（{detail[:140]}）" if detail else ""))
            continue

        _clear_cooldown(pid)
        LAST_USED = (p["id"], p["label"])
        LAST_ERRORS = list(errs)
        elapsed_ms = (time.time() - t0) * 1000
        try:
            from common import workload
            workload.record(p["label"], p["model"], LAST_USAGE[0], LAST_USAGE[1],
                            elapsed_ms, user_id)
        except Exception:
            pass
        return txt
    LAST_ERRORS = list(errs)
    raise RuntimeError("所有 LLM 供應商皆不可用：" + "；".join(errs))


def generate(prompt: str):
    try:
        return chat([{"role": "user", "content": prompt}])
    except Exception:
        return None
