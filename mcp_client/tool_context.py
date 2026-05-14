class ToolContext:

    def __init__(self, mcp_client):
        self.mcp = mcp_client
        self.tools = []

    async def refresh(self):
        res = await self.mcp.list_tools()
        self.tools = res["tools"]

    def get_tool_schema(self):
        return self.tools