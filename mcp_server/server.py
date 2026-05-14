from fastapi import FastAPI
from pydantic import BaseModel

from mcp_server.registry import get_tool, list_tools
import mcp_server.tools  # noqa

app = FastAPI()


class ToolRequest(BaseModel):
    input: dict


@app.get("/tools")
def tools():
    return {"tools": list_tools()}


@app.post("/run/{tool_name}")
async def run_tool(tool_name: str, req: ToolRequest):

    tool = get_tool(tool_name)

    if tool is None:
        return {"error": "tool not found"}

    try:
        result = await tool.run(req.input)
        return result
    except Exception as e:
        return {"error": "tool_execution_failed", "detail": str(e)}