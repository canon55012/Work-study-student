import httpx


class MCPClient:

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def call_tool(self, tool_name: str, input_data: dict):

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.base_url}/run/{tool_name}",
                json={"input": input_data}
            )
            return r.json()

    async def list_tools(self):

        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self.base_url}/tools")
            return r.json()