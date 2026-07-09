from fastapi import FastAPI
from pydantic import BaseModel
import traceback

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
    print("=" * 50)
    print("Receive:", tool_name)
    print(req.input)
    tool = get_tool(tool_name)

    if tool is None:
        print("tool not found")
        return {"error": "tool not found"}

    try:
        result = await tool.run(req.input)
        print("finish")
        return result
    except Exception as e:
        import traceback

        print("=" * 80)
        traceback.print_exc()
        print("=" * 80)

        return {
            "error": "tool_execution_failed",
            "detail": str(e)
        }