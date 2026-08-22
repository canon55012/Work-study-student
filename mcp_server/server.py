"""MCP Server：彙整所有工具，以 streamable HTTP 對外服務。"""
import sys
import asyncio

from mcp.server.fastmcp import FastMCP

from config import settings
from mcp_server.tools.pricing import (
    query_pricing,
    recommend_server,
    compare_plans,
    estimate_cost,
    estimate_storage_cost,
    plan_budget,
    compare_regions,
)
from mcp_server.tools.user_behavior import (
    log_query,
    get_user_history,
    get_recommendations,
    analyze_usage,
)
from mcp_server.tools.utils import get_current_time
from mcp_server.tools.vm_lifecycle import (
    create_vm,
    start_vm,
    stop_vm,
    maintain_vm,
    delete_vm,
    list_vms,
    get_vm,
    get_vm_bill,
    get_account_bill,
    suggest_savings,
)
from mcp_server.tools.wallet import (
    get_wallet_balance,
    top_up_wallet,
    list_transactions,
)
from mcp_server.tools.projects import (
    list_projects,
    get_project,
    get_quota,
)
from mcp_server.tools.optimize import optimize_plan_mix
from rag.faq import search_faq

mcp = FastMCP("可信賴雲助手")

mcp.tool()(query_pricing)
mcp.tool()(recommend_server)
mcp.tool()(compare_plans)
mcp.tool()(estimate_cost)
mcp.tool()(estimate_storage_cost)
mcp.tool()(plan_budget)
mcp.tool()(compare_regions)

mcp.tool()(optimize_plan_mix)

mcp.tool()(log_query)
mcp.tool()(get_user_history)
mcp.tool()(get_recommendations)
mcp.tool()(analyze_usage)

mcp.tool()(create_vm)
mcp.tool()(start_vm)
mcp.tool()(stop_vm)
mcp.tool()(maintain_vm)
mcp.tool()(delete_vm)
mcp.tool()(list_vms)
mcp.tool()(get_vm)

mcp.tool()(get_vm_bill)
mcp.tool()(get_account_bill)
mcp.tool()(suggest_savings)

mcp.tool()(get_wallet_balance)
mcp.tool()(top_up_wallet)
mcp.tool()(list_transactions)

mcp.tool()(list_projects)
mcp.tool()(get_project)
mcp.tool()(get_quota)

mcp.tool()(search_faq)

mcp.tool()(get_current_time)

if sys.platform == "win32":
    class _WinResetSuppressor:
        """攔截 ASGI lifespan startup，靜默忽略 WinError 10054。"""
        def __init__(self, inner):
            self._inner = inner
            self._patched = False

        async def __call__(self, scope, receive, send):
            if scope.get("type") == "lifespan" and not self._patched:
                self._patched = True

                async def _patched_receive():
                    msg = await receive()
                    if msg.get("type") == "lifespan.startup":
                        loop = asyncio.get_running_loop()
                        _prev = loop.get_exception_handler()

                        def _handler(loop, ctx):
                            exc = ctx.get("exception")
                            if (isinstance(exc, ConnectionResetError)
                                    and getattr(exc, "winerror", None) == 10054):
                                return
                            (_prev or loop.default_exception_handler)(loop, ctx)

                        loop.set_exception_handler(_handler)
                    return msg

                return await self._inner(scope, _patched_receive, send)
            return await self._inner(scope, receive, send)

    app = _WinResetSuppressor(mcp.streamable_http_app())
else:
    app = mcp.streamable_http_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.MCP_SERVER_HOST, port=settings.MCP_SERVER_PORT)
