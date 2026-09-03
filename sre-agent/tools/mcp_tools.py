"""MCP 工具初始化与配置。"""
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from config import MCP_CONFIG, TOOLS_ALLOWED


async def get_mcp_tools(mcp_client: MultiServerMCPClient) -> list:
    """根据白名单获取并过滤 MCP 工具。
    
    参数：
        mcp_client: 已初始化的 MCP 客户端
        
    返回：
        过滤后的工具对象列表
    """
    mcp_tools = await mcp_client.get_tools()
    
    tools = []
    for tool in mcp_tools:
        if tool.name in TOOLS_ALLOWED:
            tools.append(tool)
    
    return tools


_mcp_client = MultiServerMCPClient(MCP_CONFIG)
TOOLS = asyncio.run(get_mcp_tools(_mcp_client))