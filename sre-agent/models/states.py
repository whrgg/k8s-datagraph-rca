"""LangGraph Agent 的 TypedDict 状态定义。"""
from typing import TypedDict, List, Annotated, Dict
from langgraph.graph.message import add_messages, AnyMessage
from .schemas import Symptom, RCATask
from .reducers import merge_rca_analyses


class TriageAgentState(TypedDict):
    """Triage Agent 状态"""
    app_name: str
    app_summary: str
    target_namespace: str
    trace_service_starting_point: str
    problematic_pods: dict
    slow_traces: dict
    problematic_metrics: dict
    problematic_traces: dict
    symptoms: List[Symptom]
    prompts_config: Dict[str, str]


class PlannerAgentState(TypedDict):
    """Planner Agent 状态"""
    app_name: str
    app_summary: str
    target_namespace: str
    symptoms: List[Symptom]
    rca_tasks: List[RCATask]
    prompts_config: Dict[str, str]


class RcaAgentState(TypedDict):
    """RCA Worker Agent 状态"""
    messages: Annotated[list[AnyMessage], add_messages]
    rca_app_summary: str
    rca_target_namespace: str
    rca_task: RCATask
    insights: list[str]
    prev_steps: list[str]
    rca_output: dict
    rca_analyses_list: list[dict]
    rca_prompts_config: Dict[str, str]
    

class SupervisorAgentState(TypedDict):
    """Supervisor Agent 状态"""
    app_name: str
    app_summary: str
    symptoms: List[Symptom]
    rca_analyses_list: List[dict]
    final_report: dict
    rca_tasks: List[RCATask]
    tasks_to_be_executed: List[int]
    prompts_config: Dict[str, str]


class SreParentState(TypedDict):
    """完整 RCA 工作流的父图状态"""
    app_name: str
    app_summary: str
    target_namespace: str
    trace_service_starting_point: str

    # Triage 阶段
    problematic_pods: dict
    slow_traces: dict
    problematic_metrics: dict
    problematic_traces: dict
    symptoms: List[Symptom]

    # Planner 阶段
    rca_tasks: List[RCATask]

    # RCA Worker 阶段
    rca_analyses_list: Annotated[list[dict], merge_rca_analyses]

    # 需要由 RCA agent 执行的任务
    tasks_to_be_executed: List[int]

    # Supervisor 阶段
    final_report: dict

    # Prompt 配置
    prompts_config: Dict[str, str]
