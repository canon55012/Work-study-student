import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from config import settings  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="probe_")
settings.TOOL_CALL_LOG = os.path.join(_TMP, "tool_calls.jsonl")
settings.FAQ_MISS_LOG = os.path.join(_TMP, "faq_misses.jsonl")

from agent import providers, tools as agent_tools        # noqa: E402
from agent.core import build_messages, call_and_parse    # noqa: E402
from mcp_client.client import get_client                 # noqa: E402

_ORIGINAL_LLM = providers.active_id()
settings.LLM_STATE_FILE = os.path.join(_TMP, "llm_state.json")
providers.set_active(_ORIGINAL_LLM)

USER = "_probe_user"
MAX_ROUNDS = 6

CASES = [
    ("5 萬預算能跑 H100.small 幾天？", "plan_budget",
     "預算反向試算：不可自己用預算除以時價"),
    ("加購 500GB SSD 一個月要多少錢？", "estimate_storage_cost",
     "磁碟加購：內含分區折扣規則，自己乘會算錯"),
    ("H200 哪一區比較便宜？", "compare_regions",
     "跨區比價：需套身分折扣，非單純比牌價"),
    ("幫我看看哪裡可以省錢", "suggest_savings",
     "成本健檢：要算出可省金額，不是給籠統建議"),
    ("我還剩多少錢、還能用幾天？", "get_wallet_balance",
     "觸發詞碰撞：『還剩多少』要走錢包"),
    ("我的計畫額度還剩多少？", "get_quota",
     "觸發詞碰撞：『額度還剩多少』要走 quota"),
    ("幫我開一台 H100.small", "create_vm",
     "動作類：不可只用報價工具帶過"),
    ("H100 適合拿來做什麼？", "search_faq",
     "說明類：概念問題要查知識庫，不可憑記憶答"),
]


def seed_state():
    from datetime import datetime, timedelta
    from common import storage, wallet
    from mcp_server.tools import vm_lifecycle as vm

    shutil.rmtree(settings.user_dir(USER), ignore_errors=True)
    wallet.add_funds(USER, 50000, "探測用儲值")
    vm.create_vm("H100.small", "probe-box", region="AI-Trust", user_id=USER)
    with storage.file_lock(vm._vm_csv(USER)):
        rows = vm._read_vms(USER)
        rows[0]["計費起點"] = (datetime.now() - timedelta(hours=48)).strftime(vm._FMT)
        vm._write_vms(USER, rows)


async def run_one(client, question):
    messages = build_messages(question, [])
    used = []
    loop = asyncio.get_event_loop()
    for _ in range(MAX_ROUNDS):
        try:
            d = await loop.run_in_executor(None, call_and_parse, messages)
        except Exception as e:
            return used, f"<推理失敗：{type(e).__name__}>"
        action = d.get("action", "")
        if action == "FINISH":
            return used, d.get("answer", "")
        used.append(action)
        _, result = await agent_tools.call_tool(client, action, d.get("params", {}), USER)
        messages += [
            {"role": "assistant", "content": json.dumps(d, ensure_ascii=False)},
            {"role": "user", "content": f"Tool {action} 回傳：\n{result}\n請繼續推理。"},
        ]
    return used, "<達最大推理輪數>"


async def main():
    argv = sys.argv[1:]
    if "--llm" in argv:
        pid = argv[argv.index("--llm") + 1]
        ok, msg = providers.set_active(pid)
        if not ok:
            print(f"❌ 無法切換到 {pid}：{msg}")
            return 1

    print("=" * 60)
    print("  工具選擇正確率探測")
    print(f"  LLM：{providers.active_label()}")
    print("=" * 60)

    seed_state()
    print("  已布置探測帳號：儲值 $50,000 ＋ 一台連續運行 48h 的 H100.small\n")

    hits = 0
    async with get_client() as client:
        for question, expect, why in CASES:
            used, answer = await run_one(client, question)
            ok = expect in used
            hits += ok
            print(f"\n{'✅' if ok else '❌'} 「{question}」")
            print(f"   驗什麼：{why}")
            print(f"   期望　：{expect}")
            print(f"   實際　：{used or '（完全沒呼叫工具，直接回答）'}")
            if not ok:
                print(f"   回答　：{answer[:120].replace(chr(10), ' ')}")

    print("\n" + "=" * 60)
    print(f"  工具選擇正確：{hits}/{len(CASES)}")
    print("=" * 60)
    if hits < len(CASES):
        print("  選錯的題目請回頭檢查 prompt/system_prompt.py 的工具描述與使用時機，")
        print("  特別是該工具是否寫清楚「內含什麼規則、為何不能自己算」。")
    return 0 if hits == len(CASES) else 1


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
        shutil.rmtree(settings.user_dir(USER), ignore_errors=True)
    sys.exit(code)
