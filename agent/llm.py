"""LLM 用戶端"""
from agent import providers

LLM_LABEL = ""


def init_llm(verbose: bool = True):
    global LLM_LABEL
    aid = providers.active_id()
    LLM_LABEL = providers.active_label()
    if verbose:
        st = providers.probe(aid) if aid else {"status": "error", "detail": "無可用供應商"}
        icon = "🟢" if st.get("status") == "ok" else "🟡"
        print(f"  {icon} 目前 LLM：{LLM_LABEL}（{st.get('detail', '')}）")
        others = [f"{r['label']}={r['detail']}"
                  for r in providers.probe_all() if not r.get("active")]
        if others:
            print("     其他供應商：" + "、".join(others))
    return providers.active_kind() == "openai", LLM_LABEL


def call_llm(messages: list, user_id: str = "") -> str:
    return providers.chat(messages, user_id)
