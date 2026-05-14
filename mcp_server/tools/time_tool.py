from datetime import datetime
from mcp_server.registry import register_tool


@register_tool("time_tool")
class TimeTool:

    async def run(self, input_data: dict):

        return {
            "tool": "time_tool",
            "now": datetime.now().isoformat()
        }