"""MCP Client 呼叫層：封裝與 MCP Server 的連線。"""
from fastmcp.client import Client

from config import settings


def get_client() -> Client:
    """建立連往 MCP Server 的 client。"""
    return Client(settings.MCP_URL)
