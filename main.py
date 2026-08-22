import asyncio
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from agent.llm import init_llm            # noqa: E402
from agent.core import build_messages, call_and_parse  # noqa: E402
from agent import providers, tools as agent_tools      # noqa: E402
from mcp_client.client import get_client  # noqa: E402

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

USER_ID = "default"


def sep(c="─", w=55):
    print(c * w)


async def run(user_input: str, client, history: list):
    print(f"\n  👤 {user_input}")
    sep()

    messages = build_messages(user_input, history)
    faq_context = None
    selected = providers.active_label()

    for step in range(1, 8):
        print(f"\n  ── 第 {step} 輪 ──")
        try:
            d = call_and_parse(messages)
        except Exception as e:
            print(f"  ❌ 解析失敗：{e}")
            break

        used = providers.LAST_USED
        if used and used[1] != selected:
            print(f"  🔀 選用的 {selected} 無法使用，已自動改用 {used[1]}")
            selected = used[1]

        print(f"  💭 {d.get('thought', '')}")

        if d.get("action") == "FINISH":
            answer = d.get("answer", "")

            g = None
            if faq_context:
                from agent.core import enforce_grounding
                answer, g, attempts = enforce_grounding(messages, d, faq_context)
                if attempts:
                    print(f"\n  🔁 忠實度檢核未過，已自動依知識庫重答 {attempts} 次"
                          f"（支持度回到 {g['score']}）")
                from common.observability import maybe_log_weak_faq_miss
                if maybe_log_weak_faq_miss(user_input, faq_context, g, USER_ID):
                    print("  📝 已記錄 FAQ 未命中：知識庫無法支持此題")

            sep()
            print(f"  🤖 回答（由 {selected} 生成）：")
            sep()
            for line in answer.split("\n"):
                print(f"  {line}")
            sep()

            if g and not g["ok"]:
                print(f"  ⚠️ 重答後支持度仍為 {g['score']}，以下內容可能超出知識庫：")
                for seg in g["flagged"][:3]:
                    print(f"     ・{seg}")
                sep()

            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": answer})
            if len(history) > 20:
                del history[:2]
            return

        tool, params = d.get("action", ""), d.get("params", {})
        print(f"  🔧 呼叫：{tool}　參數：{params}")
        ok, result = await agent_tools.call_tool(client, tool, params, USER_ID)
        if ok:
            print(f"  📤 結果：{result[:120]}{'...' if len(result) > 120 else ''}")
            if tool == "search_faq":
                faq_context = result
        else:
            print(f"  ❌ {result}")

        messages += [
            {"role": "assistant", "content": json.dumps(d, ensure_ascii=False)},
            {"role": "user", "content": f"Tool {tool} 回傳：\n{result}\n請繼續推理。"},
        ]
    print("  ⚠️ 已達最大推理輪數")


def _local_llm_status():
    from config import settings
    p = providers.get_provider("local")
    if not p or not p["enabled"]:
        print("  ⓘ 本地 LLM 未啟用（.env 的 LOCAL_LLM_ENABLED=0）")
        return
    st = providers.probe("local")
    icon = "🟢" if st.get("status") == providers.OK else "🔴"
    print(f"  {icon} 本地 LLM：{st.get('detail', '')}")
    print(f"     端點 {settings.LOCAL_LLM_BASE_URL}　模型 {settings.LOCAL_LLM_MODEL}")
    if st.get("status") == providers.UNREACHABLE:
        print("     連不到通常是 VPN 未連（此端點為內網位址）；")
        print("     本輪對話會自動退回其他供應商，回答時會標示實際由誰生成。")


async def main():
    sep("═")
    print("  可信賴雲 AI Agent (CMD版)")
    sep("═")

    init_llm()
    _local_llm_status()
    history = []

    async with get_client() as client:
        tools = await client.list_tools()
        print(f"  ✅ 連線成功，載入 {len(tools)} 個工具")
        print("  " + "  ".join([t.name for t in tools]))
        print("  輸入 clear 清除對話記憶，輸入 exit 離開\n")

        while True:
            sep()
            q = input("  請輸入需求：").strip()

            if q.lower() in ["exit", "quit", "離開"]:
                print("\n  👋 再見！")
                break

            if q.lower() == "clear":
                history.clear()
                print("  🗑 對話記憶已清除")
                continue

            if not q:
                continue

            await run(q, client, history)
            input("\n  按 Enter 繼續...")


if __name__ == "__main__":
    asyncio.run(main())
