import json
from mcp_client.client import MCPClient
from prompt.prompt_formatter import PromptFormatter


class VMAgentManager:

    def __init__(self, llm, prompt_formatter: PromptFormatter):
        self.llm = llm
        self.prompt_formatter = prompt_formatter

        # MCP client（連 MCP server）
        self.mcp = MCPClient("http://localhost:8000")

    async def chat(self, user_input: str):

        # 1️⃣ 組 prompt
        messages = self.prompt_formatter.format_prompt(
            "",
            user_input,
            "basic"
        )

        # 2️⃣ 呼叫 LLM
        response = self.llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0
        )

        content = response.choices[0].message.content

        # 3️⃣ 嘗試解析 tool call
        try:
            tool_call = json.loads(content)

            tool_name = tool_call["tool"]
            tool_input = tool_call["input"]

            # 4️⃣ 呼叫 MCP
            result = await self.mcp.call(tool_name, tool_input)

            return result

        except Exception:
            # fallback：純文字回答
            return content