import csv
import os
import time

from config import settings

_TFIDF_MIN_SIM = 0.18
_KEYWORD_MIN_SCORE = 2.0

_VECTORIZER = None
_DOC_MATRIX = None
_TFIDF_ITEMS = None
_EMB_MATRIX = None
_EMB_ITEMS = None
_EMB_COOLDOWN_UNTIL = 0.0

_LAST_BACKEND = None


def _load_faq() -> list:
    if not os.path.exists(settings.FAQ_CSV):
        return []
    items = []
    with open(settings.FAQ_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kws = [k.strip() for k in (row.get("關鍵字") or "").split("|") if k.strip()]
            items.append({
                "question": (row.get("問題") or "").strip(),
                "answer": (row.get("答案") or "").strip(),
                "keywords": kws,
            })
    return items


def _doc_text(item: dict) -> str:
    return item["question"] + " " + " ".join(item["keywords"] * 2)


_SYNONYM_GROUPS = {
    "GPU": ["gpu", "顯卡", "顯示卡", "繪圖卡", "圖形卡", "顯示晶片"],
    "VRAM": ["vram", "顯存", "視訊記憶體", "顯卡記憶體", "顯卡的記憶體"],
    "H100": ["h100", "高階gpu", "高階顯卡"],
    "訓練": ["訓練", "train", "training", "練模型"],
    "推論": ["推論", "推理", "inference", "部署上線"],
    "便宜": ["便宜", "划算", "省錢", "cp值", "經濟實惠", "預算有限", "花最少"],
    "disk+": ["disk+", "硬碟", "大硬碟", "加大硬碟", "大容量", "儲存空間不夠"],
    "記憶體優化": ["記憶體優化", "吃記憶體", "大記憶體", "ram優化"],
    "CPU優化": ["cpu優化", "運算密集", "高運算", "算力密集"],
    "關機": ["關機", "關掉", "關起來", "停機", "停掉"],
    "開機": ["開機", "啟動", "開啟", "開起來", "重開"],
    "維護": ["維護", "維護模式", "維修", "保養", "檢修"],
    "刪除": ["刪除", "刪掉", "移除", "砍掉", "銷毀", "清除"],
    "VM": ["vm", "虛擬機", "虛擬主機", "instance", "主機", "機台"],
    "月費": ["月費", "每月", "一個月", "月租"],
}


def _synonym_tail(text: str) -> str:
    low = text.lower()
    hits = [canon for canon, variants in _SYNONYM_GROUPS.items()
            if any(v in low for v in variants)]
    return " ".join(hits)


def _expand(text: str) -> str:
    tail = _synonym_tail(text)
    return f"{text} {tail}" if tail else text


def _char_bigrams(text: str) -> set:
    text = "".join(text.split())
    return {text[i:i + 2] for i in range(len(text) - 1)} if len(text) >= 2 else set(text)


def _keyword_score(query: str, item: dict) -> float:
    q = _expand(query).lower()
    kw_hits = sum(1 for kw in item["keywords"] if kw.lower() in q)
    q_grams = _char_bigrams(_expand(query))
    item_grams = _char_bigrams(_expand(item["question"]))
    overlap = len(q_grams & item_grams) / len(q_grams) if q_grams else 0
    return kw_hits * 2 + overlap


def _keyword_retrieve(query: str, items: list, top_k: int) -> list:
    scored = [(it, _keyword_score(query, it)) for it in items]
    scored = [(it, s) for it, s in scored if s > _KEYWORD_MIN_SCORE]
    scored.sort(key=lambda x: -x[1])
    return [it for it, _ in scored[:top_k]]


def _build_tfidf(items: list):
    global _VECTORIZER, _DOC_MATRIX, _TFIDF_ITEMS
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3))
    matrix = vec.fit_transform([_expand(_doc_text(it)) for it in items])
    _VECTORIZER, _DOC_MATRIX, _TFIDF_ITEMS = vec, matrix, items
    return vec, matrix


def _tfidf_retrieve(query: str, items: list, top_k: int) -> list:
    from sklearn.metrics.pairwise import linear_kernel
    if _VECTORIZER is None or _TFIDF_ITEMS is not items:
        vec, matrix = _build_tfidf(items)
    else:
        vec, matrix = _VECTORIZER, _DOC_MATRIX
    q_vec = vec.transform([_expand(query)])
    sims = linear_kernel(q_vec, matrix)[0]
    ranked = sorted(range(len(items)), key=lambda i: -sims[i])
    return [items[i] for i in ranked[:top_k] if sims[i] >= _TFIDF_MIN_SIM]


def _emb_timeout():
    try:
        import httpx
        return httpx.Timeout(settings.EMBEDDING_TIMEOUT,
                             connect=settings.LLM_CONNECT_TIMEOUT)
    except Exception:
        return settings.EMBEDDING_TIMEOUT


def _embed_texts(texts: list):
    global _EMB_COOLDOWN_UNTIL
    if not settings.EMBEDDING_ENABLED:
        raise RuntimeError("embedding 已關閉")
    if time.time() < _EMB_COOLDOWN_UNTIL:
        raise RuntimeError("embedding 端點稍早連不上，冷卻中")
    from openai import OpenAI
    import numpy as np
    client = OpenAI(base_url=settings.EMBEDDING_BASE_URL,
                    api_key=settings.EMBEDDING_API_KEY or "none",
                    max_retries=0, timeout=_emb_timeout())
    try:
        resp = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
    except Exception:
        _EMB_COOLDOWN_UNTIL = time.time() + settings.LLM_COOLDOWN_SECONDS
        raise
    _EMB_COOLDOWN_UNTIL = 0.0
    mat = np.array([d.embedding for d in resp.data], dtype="float32")
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return mat / (norms + 1e-8)


def _embed_retrieve(query: str, items: list, top_k: int) -> list:
    global _EMB_MATRIX, _EMB_ITEMS
    import numpy as np
    if _EMB_MATRIX is None or _EMB_ITEMS is not items:
        _EMB_MATRIX = _embed_texts([_doc_text(it) for it in items])
        _EMB_ITEMS = items
    q_vec = _embed_texts([_expand(query)])[0]
    sims = _EMB_MATRIX @ q_vec
    ranked = sorted(range(len(items)), key=lambda i: -sims[i])
    return [items[i] for i in ranked[:top_k] if sims[i] >= settings.EMBEDDING_MIN_SIM]


_TIERS = [
    ("embedding", _embed_retrieve),
    ("tfidf", _tfidf_retrieve),
    ("keyword", _keyword_retrieve),
]


def active_backend() -> str:
    if settings.EMBEDDING_ENABLED:
        try:
            import openai  # noqa: F401
            return "embedding"
        except Exception:
            pass
    try:
        import sklearn  # noqa: F401
        return "tfidf"
    except Exception:
        return "keyword"


def last_backend() -> str:
    return _LAST_BACKEND


def retrieve(query: str, top_k: int = 2) -> list:
    global _LAST_BACKEND
    items = _load_faq()
    if not items:
        return []
    for name, fn in _TIERS:
        try:
            hits = fn(query, items, top_k)
            _LAST_BACKEND = name
            return hits
        except Exception:
            continue
    return []


def search_faq(question: str, top_k: int = 2, user_id: str = "anon") -> str:
    if not os.path.exists(settings.FAQ_CSV):
        return "找不到 FAQ 知識庫，請確認 data/faq.csv 路徑正確"

    hits = retrieve(question, top_k=top_k)
    if not hits:
        try:
            from common.observability import log_faq_miss
            log_faq_miss(question, last_backend(), user_id)
        except Exception:
            pass
        return ("知識庫中查無相關說明。請老實告知使用者目前沒有這方面的資料，"
                "不要自行編造；可引導改用 query_pricing 查報價，或請使用者描述得更具體。")

    lines = [
        "以下是知識庫中最相關的說明。請『僅根據』下列內容回答，"
        "不要補充這裡沒有提到的細節，也不要自行杜撰：",
    ]
    for i, item in enumerate(hits, 1):
        lines.append(f"\nQ{i}：{item['question']}")
        lines.append(f"A{i}：{item['answer']}")
    return "\n".join(lines)


def _split_segments(text: str) -> list:
    import re
    return [s.strip() for s in re.split(r"[。\n！？!?；;，,、]", text) if len(s.strip()) >= 4]


def check_grounding(answer: str, context: str, min_overlap: float = 0.45,
                    min_score: float = 0.6) -> dict:
    segs = _split_segments(answer)
    if not segs:
        return {"score": 1.0, "ok": True, "flagged": []}
    ctx = _char_bigrams(context)
    flagged, supported = [], 0
    for s in segs:
        g = _char_bigrams(s)
        overlap = len(g & ctx) / len(g) if g else 1.0
        if overlap >= min_overlap:
            supported += 1
        else:
            flagged.append(s)
    score = supported / len(segs)
    return {"score": round(score, 2), "ok": score >= min_score, "flagged": flagged}
