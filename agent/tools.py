"""Agent 端的工具呼叫封裝：注入使用者身分 + 記錄可觀測性"""
import time

from common import observability

USER_SCOPED_TOOLS = {
    "log_query", "get_user_history", "get_recommendations", "analyze_usage",
    "create_vm", "start_vm", "stop_vm", "maintain_vm", "delete_vm",
    "list_vms", "get_vm",
    "get_vm_bill", "get_account_bill", "suggest_savings",
    "get_wallet_balance", "top_up_wallet", "list_transactions",
    "list_projects", "get_project", "get_quota",
    "estimate_cost", "estimate_storage_cost", "plan_budget", "compare_regions",
    "optimize_plan_mix",
    "search_faq",
}

REGION_SCOPED_TOOLS = {
    "query_pricing", "recommend_server", "compare_plans", "estimate_cost",
    "estimate_storage_cost", "plan_budget", "create_vm", "optimize_plan_mix",
}


async def call_tool(client, tool: str, params: dict, user_id: str = "default",
                    region: str = None) -> tuple:
    """呼叫 MCP 工具，回傳 (ok, text)。"""
    display_params = dict(params or {})
    send_params = dict(params or {})
    if tool in USER_SCOPED_TOOLS:
        send_params["user_id"] = user_id
    if region and tool in REGION_SCOPED_TOOLS and not send_params.get("region"):
        send_params["region"] = region

    t0 = time.time()
    try:
        res = await client.call_tool(tool, send_params)
        text = res.content[0].text
        ok = True
    except Exception as e:
        text = f"失敗：{e}"
        ok = False
    latency_ms = (time.time() - t0) * 1000

    try:
        observability.log_tool_call(user_id, tool, display_params, ok, latency_ms, text)
    except Exception:
        pass

    return ok, text
