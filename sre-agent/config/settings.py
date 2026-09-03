"""K8s Datagraph RCA 配置与环境变量模块。"""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from typing import Any, Mapping

# 获取仓库根目录路径
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

# 从根目录的 .env 文件加载环境变量
load_dotenv(os.path.join(root_dir, '.env'), verbose=True)

# 将 MCP-server 加入路径
import sys
mcp_server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../MCP-server'))
sys.path.insert(0, mcp_server_path)

# 大模型配置
GPT5_MINI = ChatOpenAI(model="gpt-5-mini")

GPT5_1 = ChatOpenAI(model="gpt-5.1")

# 调查预算
MAX_TOOL_CALLS = int(os.environ.get("MAX_TOOL_CALLS", 8))

# 每轮 RCA 任务数
RCA_TASKS_PER_ITERATION = int(os.environ.get("RCA_TASKS_PER_ITERATION", 3))

# 调查时链路分析的起始服务
TRACE_SERVICE_STARTING_POINT = os.environ.get("TRACE_SERVICE_STARTING_POINT", "frontend")

# 每日 OpenAI token 限额
MAX_DAILY_OPENAI_TOKEN_LIMIT = int(os.environ.get("MAX_DAILY_OPENAI_TOKEN_LIMIT", 2_000_000))

AIOPSLAB_DIR = os.environ.get("AIOPSLAB_DIR")


def apply_config_overrides(overrides: Mapping[str, Any]) -> None:
    # 用于覆盖运行时配置的函数
    """更新运行时参数（每次启动 Agent 前调用）。"""
    global MAX_TOOL_CALLS, RCA_TASKS_PER_ITERATION, TRACE_SERVICE_STARTING_POINT

    if "MAX_TOOL_CALLS" in overrides:
        os.environ["MAX_TOOL_CALLS"] = str(overrides["MAX_TOOL_CALLS"])
    if "RCA_TASKS_PER_ITERATION" in overrides:
        os.environ["RCA_TASKS_PER_ITERATION"] = str(overrides["RCA_TASKS_PER_ITERATION"])
    if "TRACE_SERVICE_STARTING_POINT" in overrides:
        os.environ["TRACE_SERVICE_STARTING_POINT"] = str(overrides["TRACE_SERVICE_STARTING_POINT"])

    MAX_TOOL_CALLS = int(os.environ.get("MAX_TOOL_CALLS", MAX_TOOL_CALLS))
    RCA_TASKS_PER_ITERATION = int(os.environ.get("RCA_TASKS_PER_ITERATION", RCA_TASKS_PER_ITERATION))
    TRACE_SERVICE_STARTING_POINT = os.environ.get("TRACE_SERVICE_STARTING_POINT", TRACE_SERVICE_STARTING_POINT)

# MCP 服务配置 - 基于 stdio（由客户端自动拉起）
_MCP_SERVER_PATH = os.path.join(root_dir, "MCP-server", "mcp_server.py")
_MCP_SERVER_DIR = os.path.join(root_dir, "MCP-server")

def get_mcp_config() -> dict:
    """获取包含当前环境变量的 MCP 配置。
    
    This function builds the MCP config dynamically, ensuring all relevant
    environment variables are passed to the MCP server subprocess.
    """
    # 收集需要传给 MCP server 的环境变量
    env_vars = {
        "ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS": "true"
    }
    
    # 加入所有与可观测性相关的环境变量
    env_keys_to_pass = [
        "TARGET_NAMESPACE",
        "PROMETHEUS_SERVER_URL",
        "JAEGER_URL",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "TRACE_SERVICE_STARTING_POINT",
    ]
    
    for key in env_keys_to_pass:
        value = os.environ.get(key)
        if value is not None:
            env_vars[key] = value
    
    return {
        "kubernetes": {
            "command": "npx",
            "args": ["mcp-server-kubernetes"],
            "transport": "stdio",
            "env": {
                "ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS": "true"
            }
        },
        "cluster_api": {
            "command": "poetry",
            "args": ["run", "python", _MCP_SERVER_PATH],
            "transport": "stdio",
            "env": env_vars
        }
    }

# 初始 MCP 配置 - 创建客户端时会更新
MCP_CONFIG = get_mcp_config()

# 工具配置
K8S_TOOLS_ALLOWED = [
    "kubectl_get", 
    "kubectl_describe", 
    "explain_resource", 
    "list_api_resources", 
    "ping"
]

CUSTOM_TOOLS_ALLOWED = [
    "get_metrics", 
    "get_metrics_range", 
    "get_pods_from_service", 
    "get_cluster_pods_and_services", 
    "get_services_used_by", 
    "get_dependencies", 
    "get_logs", 
    "get_traces", 
    "get_trace"
]

TOOLS_ALLOWED = K8S_TOOLS_ALLOWED + CUSTOM_TOOLS_ALLOWED
