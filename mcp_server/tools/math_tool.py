from sympy import symbols, sympify, integrate
from mcp_server.registry import register_tool


@register_tool("math_tool")
class MathTool:

    async def run(self, input_data: dict):

        expr = input_data["expression"]

        x = symbols("x")

        # 只允許 sympy parse（不要 eval）
        parsed = sympify(expr)

        result = integrate(parsed, x)

        return {
            "tool": "math_tool",
            "input": expr,
            "result": str(result)
        }