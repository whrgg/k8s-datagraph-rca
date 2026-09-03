"""Triage Agent：采集集群健康数据并识别症状。"""
import json
import sys
from pathlib import Path
from langgraph.graph import START, END, StateGraph
import logging
from langchain_core.prompts import ChatPromptTemplate


logger = logging.getLogger(__name__)

# 将 MCP-server 加入路径，以便导入 API
mcp_server_path = str(Path(__file__).parent.parent.parent / "MCP-server")
if mcp_server_path not in sys.path:
    sys.path.insert(0, mcp_server_path)

from api.jaeger_api import JaegerAPI
from api.k8s_api import K8sAPI
from api.prometheus_api import PrometheusAPI

from models import TriageAgentState, SymptomList
from prompts import TRIAGE_SYSTEM_PROMPT, TRIAGE_HUMAN_PROMPT
from config import GPT5_MINI
from utils import get_system_prompt


def get_triage_data(state: TriageAgentState) -> dict:
    """从集群监控系统采集 Triage 数据。
    
    参数：
        state: Current triage agent state
        
    返回：
        Dictionary with problematic pods, traces, and metrics
    """
    jaeger_api = JaegerAPI()
    k8s_api = K8sAPI(state["target_namespace"])
    prometheus_api = PrometheusAPI(namespace=state["target_namespace"])
    
    # 获取状态异常的 Pod
    problematic_pods = k8s_api.get_problematic_pods()

    # 获取包含错误的链路追踪
    problematic_traces = jaeger_api.get_processed_traces(
        service=state["trace_service_starting_point"], 
        only_errors=True
    )

    # 过滤出耗时超过 2 秒的链路追踪
    slow_traces = jaeger_api.get_slow_traces(
        service=state["trace_service_starting_point"], 
        min_duration_ms=2000
    )

    # 获取异常指标
    problematic_pods_metrics: dict = {
        "problematic_metrics": []
    }

    pods = k8s_api.get_pods_list()

    for pod in pods:
        triage_metric_report = prometheus_api.get_pod_triage_metrics(pod)
        if triage_metric_report["is_anomalous"]:
            problematic_pods_metrics["problematic_metrics"].append(triage_metric_report)
    
    if len(problematic_pods_metrics["problematic_metrics"]) > 0:
        problematic_pods_metrics["pods_count"] = len(problematic_pods_metrics["problematic_metrics"])
    else:
        problematic_pods_metrics["info"] = "所有监控指标正常，未检测到异常值。"

    return {
        "problematic_pods": problematic_pods,
        "problematic_traces": problematic_traces,
        "slow_traces": slow_traces,
        "problematic_metrics": problematic_pods_metrics
    }


def triage_agent(state: TriageAgentState) -> dict:
    """分析 Triage 数据并识别症状。
    
    参数：
        state: Current triage agent state with gathered data
        
    返回：
        Dictionary with identified symptoms
    """
    # 辅助函数：格式化数据，或返回提示信息
    def format_data(data, label):
        if "info" in data:
            return data["info"]
        if "error" in data:
            return f"获取{label}时出错：{data['error']}"
        return f"```json\n{json.dumps(data, indent=2)}\n```"

    problematic_pods_str = format_data(state["problematic_pods"], "pods")
    problematic_metrics_str = format_data(state["problematic_metrics"], "metrics")
    slow_traces_str = format_data(state["slow_traces"], "slow traces")
    
    # 检查是否存在主要问题（Pod、指标、慢链路）
    has_problems = (
        "info" not in state["problematic_pods"] and "error" not in state["problematic_pods"]
    ) or (
        "info" not in state["problematic_metrics"] and "error" not in state["problematic_metrics"]
    ) or (
        "info" not in state["slow_traces"] and "error" not in state["slow_traces"]
    )
    
    # 仅在未发现其他问题时再分析错误链路（兜底）
    if has_problems:
        problematic_traces_str = "未分析错误链路（已检测到其他问题）。"
    else:
        logger.warning("未检测到主要问题（Pod/指标/慢链路），回退到分析错误链路。")
        problematic_traces_str = format_data(state["problematic_traces"], "error traces")

    # 确定要使用的 system prompt
    triage_system_prompt = get_system_prompt(state, "triage_agent", TRIAGE_SYSTEM_PROMPT) #type: ignore

    triage_prompt_template = ChatPromptTemplate.from_messages(
        [
            ("system", triage_system_prompt),
            ("human", TRIAGE_HUMAN_PROMPT),
        ]
    )

    llm_for_symptoms = GPT5_MINI.with_structured_output(SymptomList)
    triage_chain = triage_prompt_template | llm_for_symptoms

    logger.info("Triage Agent 正在分析遥测数据以识别症状。")

    symptom_list = triage_chain.invoke({
        "app_name": state["app_name"],
        "app_summary": state["app_summary"],
        "problematic_pods": problematic_pods_str,
        "problematic_metrics": problematic_metrics_str,
        "slow_traces": slow_traces_str,
        "problematic_traces": problematic_traces_str
    })

    return {"symptoms": symptom_list.symptoms}  # type: ignore


def build_triage_graph():
    """构建并编译 Triage Agent 子图。
    
    返回：
        已编译的 Triage Agent 子图
    """
    builder = StateGraph(TriageAgentState)

    # 添加节点
    builder.add_node("gather-triage-data", get_triage_data)
    builder.add_node("triage-agent", triage_agent)

    # 添加边
    builder.add_edge(START, "gather-triage-data")
    builder.add_edge("gather-triage-data", "triage-agent")
    builder.add_edge("triage-agent", END)

    return builder.compile().with_config(run_name="Triage Agent")


# 导出编译后的图
triage_agent_graph = build_triage_graph()
