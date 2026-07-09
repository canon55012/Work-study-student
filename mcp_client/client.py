import httpx


class MCPClient:

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.timeout = httpx.Timeout(None)

    async def call_tool(self, tool_name: str, input_data: dict):
        print("MCPClient timeout =", self.timeout)

        # async with httpx.AsyncClient(timeout=6) as client:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            print("POST start")

            r = await client.post(
                f"{self.base_url}/run/{tool_name}",
                json={"input": input_data}
            )
            print("POST done")
            print("HTTP Status:", r.status_code)
            print("Response Text:", r.text)

            r.raise_for_status()
            return r.json()

    async def list_tools(self):
        # async with httpx.AsyncClient(timeout=6) as client:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/tools")
            r.raise_for_status()
            return r.json()
