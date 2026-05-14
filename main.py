import asyncio
import json
import time

from rag.model_handler import ModelHandler
from prompt.prompt_formatter import PromptFormatter
from mcp_client.client import MCPClient


class VMAgentManager:

    def __init__(self, token: str):

        self.last_access_time = time.time()

        self.parameters_initializer()

        self.prompt_formatter = PromptFormatter()

        self.mcp = MCPClient("http://localhost:8000")

    def parameters_initializer(self):

        from ruamel.yaml import YAML

        yaml = YAML()

        with open("./config/settings.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.load(f)

        self.openai_base_url = cfg["openai_base_url"]
        self.api_key = cfg["api_key"]
        self.llm_model_name = [cfg["llm_model_name"]]
        self.prompt_style = cfg["prompt_style"]
        self.temperature = cfg["temperature"]

        self.model_handler = ModelHandler(
            self.temperature,
            self.api_key,
            self.llm_model_name,
            self.openai_base_url
        )

        self.llm = self.model_handler.initialize_llm_openai(self.api_key)

    async def chat(self, user_input: str):

        messages = self.prompt_formatter.format_prompt(
            "",
            user_input,
            self.prompt_style
        )

        response = self.model_handler.ask_openai(
            self.llm,
            messages,
            stream=False
        )

        content = response.choices[0].message.content.strip()

        print("\n📌 LLM:", content)

        try:
            tool_data = json.loads(content)

            tool_name = tool_data["tool"]
            tool_input = tool_data["input"]

            print("\n🔧 MCP CALL:", tool_name, tool_input)

            result = await self.mcp.call_tool(tool_name, tool_input)

            return result

        except Exception as e:

            print("\n⚠️ no tool call:", e)

            return content


async def main():

    agent = VMAgentManager("demo")

    print("MCP Agent started")

    while True:

        q = input("You: ")

        if q == "exit":
            break

        res = await agent.chat(q)

        print("\nAI:", res)


if __name__ == "__main__":
    asyncio.run(main())