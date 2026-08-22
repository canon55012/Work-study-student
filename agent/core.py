"""Agent 推理核心：組裝對話訊息、解析 LLM 輸出的 JSON"""
import json

from prompt.system_prompt import SYSTEM_PROMPT


def build_messages(user_input: str, history: list) -> list:
    """組裝要送進 LLM 的訊息串"""
    return (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + history
        + [{"role": "user", "content": user_input}]
    )


def parse_llm(raw: str) -> dict:
    """從 LLM 回應文字中擷取並解析出 JSON 物件"""
    if "```" in raw:
        for part in raw.split("```"):
            if "{" in part:
                raw = part.replace("json", "").strip()
                break
    raw = raw.replace('\r', ' ').replace('\t', ' ').replace('\n', ' ')
    s = raw.find("{")
    if s == -1:
        raise ValueError("No JSON found")

    depth, in_str, escape = 0, False, False
    for i, c in enumerate(raw[s:], s):
        if escape:
            escape = False
            continue
        if c == '\\' and in_str:
            escape = True
            continue
        if c == '"' and not escape:
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return json.loads(raw[s:i + 1])
    raise ValueError("Incomplete JSON")


def call_and_parse(messages: list, max_retries: int = 2) -> dict:
    """call_llm + parse_llm，JSON 解析失敗時自動追加提示並重試"""
    from agent.llm import call_llm
    msgs = list(messages)
    last_raw = ""

    for attempt in range(max_retries + 1):
        last_raw = call_llm(msgs)
        try:
            return parse_llm(last_raw)
        except Exception:
            if attempt < max_retries:
                msgs = msgs + [
                    {"role": "assistant", "content": last_raw},
                    {"role": "user", "content": (
                        "你沒有回傳 JSON 格式，請重新回覆，只能回傳這個格式：\n"
                        '{"thought": "推理過程", "action": "tool名稱或FINISH",'
                        ' "params": {}, "answer": "最終回答(僅FINISH時填)"}'
                    )},
                ]

    raise ValueError(f"JSON 解析失敗（重試 {max_retries} 次）：{last_raw[:80]}")


def enforce_grounding(messages: list, finish_dict: dict, faq_context: str,
                      max_retries: int = 1) -> tuple:
    """忠實度檢核：回答超出知識庫時，自動要求 LLM『僅依知識庫』重答"""
    from rag.faq import check_grounding

    answer = finish_dict.get("answer", "")
    g = check_grounding(answer, faq_context)
    msgs = list(messages)
    prev = finish_dict
    attempts = 0

    while not g["ok"] and attempts < max_retries:
        attempts += 1
        flagged = "；".join(g["flagged"][:5])
        msgs = msgs + [
            {"role": "assistant", "content": json.dumps(prev, ensure_ascii=False)},
            {"role": "user", "content": (
                "忠實度檢核未通過：你上一則回答有部分內容超出知識庫範圍"
                "（疑似自行補充或杜撰）：\n"
                f"{flagged}\n"
                "請『僅根據』先前 search_faq 回傳的知識庫內容重新作答，"
                "移除知識庫沒有提到的細節、數字與規格，不要新增任何依據以外的內容；"
                "若知識庫確實沒有相關資訊，就老實說目前沒有這方面的資料。"
                "仍以 FINISH 的 JSON 格式回覆。"
            )},
        ]
        try:
            d = call_and_parse(msgs)
        except Exception:
            break
        new_answer = d.get("answer", "") or answer
        new_g = check_grounding(new_answer, faq_context)
        prev = d
        if new_g["score"] >= g["score"]:
            answer, g = new_answer, new_g
        else:
            break

    return answer, g, attempts
