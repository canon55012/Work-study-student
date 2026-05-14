class BaseTool:
    async def run(self, input_data: dict):
        raise NotImplementedError