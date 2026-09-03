"""K8s Datagraph RCA 父工作流图组装模块。"""
from langgraph.graph import START, END, StateGraph
from langgraph.types import Send
import logging
from config import settings as config_settings

from models import SreParentState
from agents import (
    triage_agent_graph,
    planner_agent_graph,
    rca_agent_graph,
    supervisor_agent_graph
)

logger = logging.getLogger(__name__)

def update_rca_task_status(state: SreParentState) -> dict:
    """在派发给 RCA Agent 之前，将 RCA 任务状态从 pending 更新为 in_progress。
    
    采用分而治之策略更新 RCA 任务状态：
    - 首轮：将前 RCA_TASKS_PER_ITERATION 个任务标记为 in_progress
    - 后续轮次：仅将 Supervisor 通过 tasks_to_be_executed 指定的任务标记为 in_progress
    
    rca_tasks 列表长度保持不变，仅更新状态；尚未调度的任务保持 pending。
    
    参数：
        state: 父图状态，包含 rca_tasks 与 tasks_to_be_executed
        
    返回：
        更新后的 rca_tasks 列表（选中任务 status=in_progress）
    """
    rca_tasks = state.get("rca_tasks", [])
    rca_tasks_to_be_executed = state.get("tasks_to_be_executed", [])

    if not rca_tasks:
        return {}

    # 找出已完成分析的优先级，避免被重复调度
    completed_priorities: set[int] = set()
    for analysis in state.get("rca_analyses_list", []):
        task_info = analysis.get("task") if isinstance(analysis, dict) else None
        priority = None
        if isinstance(task_info, dict):
            priority = task_info.get("priority")
        elif hasattr(task_info, "priority"):
            priority = getattr(task_info, "priority")
        if isinstance(priority, int):
            completed_priorities.add(priority)

    # 规范化任务状态，将已完成的历史任务标记为 completed
    normalised_tasks = []
    for task in rca_tasks:
        if task.priority in completed_priorities and task.status != "completed":
            normalised_tasks.append(task.model_copy(update={"status": "completed"}))
        else:
            normalised_tasks.append(task)

    rca_tasks = normalised_tasks

    selected_tasks: list = []
    priorities_to_execute = {priority for priority in rca_tasks_to_be_executed if isinstance(priority, int)}

    if priorities_to_execute:
        # 后续迭代：只执行 supervisor 指定的任务
        logger.info(f"更新任务状态：{priorities_to_execute}")
        selected_tasks = [task for task in rca_tasks if task.priority in priorities_to_execute and task.status != "completed"]
        missing_priorities = priorities_to_execute.difference({task.priority for task in selected_tasks})
        if missing_priorities:
            logger.warning(f"请求的 RCA 任务已完成或不存在：{sorted(missing_priorities)}")
    else:
        # 首轮迭代：选择最前面的 pending 任务并行执行
        batch_size = config_settings.RCA_TASKS_PER_ITERATION
        logger.info(f"更新前 {batch_size} 个任务的状态。")
        pending_tasks = [task for task in rca_tasks if task.status == "pending"]
        selected_tasks = pending_tasks[:batch_size]

    # 将选中的任务标记为 in_progress，并保留其他状态变更
    updated_tasks = []
    selected_priorities = {task.priority for task in selected_tasks}

    for task in rca_tasks:
        if task.priority in selected_priorities and task.status != "in_progress":
            updated_tasks.append(task.model_copy(update={"status": "in_progress"}))
        elif task.priority in completed_priorities and task.status != "completed":
            updated_tasks.append(task.model_copy(update={"status": "completed"}))
        elif task.priority not in selected_priorities and task.status == "in_progress":
            updated_tasks.append(task.model_copy(update={"status": "pending"}))
        else:
            updated_tasks.append(task)

    return {"rca_tasks": updated_tasks}

def rca_router(state: SreParentState) -> list[Send]:
    """根据任务可用性，将 RCA 任务路由至并行 RCA Agent，或跳过至 Supervisor。
    
    采用分而治之策略派发 RCA 任务：
    - 首轮：将前 RCA_TASKS_PER_ITERATION 个任务路由至并行 RCA Agent
    - 后续轮次：仅路由 Supervisor 指定的任务（tasks_to_be_executed）
    - 无剩余任务时直接进入 Supervisor 生成最终诊断
    
    每个任务使用重命名字段（rca_app_summary、rca_target_namespace），避免与父状态键冲突。
    
    参数：
        state: 父图状态（rca_tasks、tasks_to_be_executed、symptoms 等）
        
    返回：
        并行 RCA Agent 的 Send 列表；无任务时 Send 至 Supervisor
    """
    rca_tasks = state.get("rca_tasks", [])
    tasks_to_be_executed = [priority for priority in state.get("tasks_to_be_executed", []) if isinstance(priority, int)]
    
    if not rca_tasks:
        # 没有 RCA 任务时，带着当前 symptoms 直接进入 supervisor
        logger.info("RCA Router：未找到 RCA 任务，路由至 Supervisor。")
        supervisor_input = {
            "app_name": state.get("app_name"),
            "app_summary": state.get("app_summary"),
            "symptoms": state.get("symptoms", []),
            "rca_tasks": [],
            "rca_analyses_list": [],
            "prompts_config": state.get("prompts_config", {})
        }
        return [Send("supervisor_agent", supervisor_input)]

    # 确定本轮要执行的任务
    if tasks_to_be_executed:
        # 后续迭代：严格遵循 supervisor 的指令
        requested_priorities = set(tasks_to_be_executed)
        selected_tasks = [task for task in rca_tasks if task.priority in requested_priorities and task.status != "completed"]
        missing_priorities = requested_priorities.difference({task.priority for task in selected_tasks})
        if missing_priorities:
            logger.warning(f"RCA Router：请求的任务已完成或不可用：{sorted(missing_priorities)}")
    else:
        # 首轮兜底：执行已标记为 in_progress 的任务
        selected_tasks = [task for task in rca_tasks if task.status == "in_progress"]

    # 检查任务是否已在之前的迭代中全部完成
    pending_tasks = [task for task in rca_tasks if task.status == "pending"]
    
    if not selected_tasks and not pending_tasks:
        # 所有任务都已完成，但 router 仍被调用，直接进入 supervisor
        logger.info("RCA Router：所有任务已完成，路由至 Supervisor 生成最终报告。")
        supervisor_input = {
            "app_name": state.get("app_name"),
            "app_summary": state.get("app_summary"),
            "symptoms": state.get("symptoms", []),
            "rca_tasks": rca_tasks, # 传入全部任务
            "rca_analyses_list": state.get("rca_analyses_list", []), # 传入已有分析结果
            "prompts_config": state.get("prompts_config", {})
        }
        return [Send("supervisor_agent", supervisor_input)]
    
    if not selected_tasks:
        # 当 tasks_to_be_executed 为空且所有任务仍为 pending 时会出现该情况
        # 这是第一次迭代的入口
        logger.info("RCA Router：未找到 in_progress 任务，首轮选择 pending 任务。")
        batch_size = config_settings.RCA_TASKS_PER_ITERATION
        selected_tasks = pending_tasks[:batch_size]
        if not selected_tasks:
            logger.warning("RCA Router：无可执行任务，路由至 Supervisor。")
            supervisor_input = {
                "app_name": state.get("app_name"),
                "app_summary": state.get("app_summary"),
                "symptoms": state.get("symptoms", []),
                "rca_tasks": rca_tasks,
                "rca_analyses_list": state.get("rca_analyses_list", []),
                "prompts_config": state.get("prompts_config", {})
            }
            return [Send("supervisor_agent", supervisor_input)]


    # 为选中的任务创建并行 RCA 调查
    parallel_rca_calls = []
    for task in selected_tasks:
        # 传入重命名后的字段，避免与父状态冲突并触发 InvalidUpdateError
        rca_input_state = {
            "rca_task": task,
            "rca_app_summary": state.get("app_summary", ""), 
            "rca_target_namespace": state.get("target_namespace", ""),
            "messages": [],
            "insights": [],
            "prev_steps": [],
            "rca_analyses_list": [],
            "rca_prompts_config": state.get("prompts_config", {})
        }
        parallel_rca_calls.append(Send("rca_agent", rca_input_state))

    logger.info(f"RCA Router：启动 {len(parallel_rca_calls)} 个并行 RCA Worker，任务优先级：{[t.priority for t in selected_tasks]}")

    return parallel_rca_calls


def supervisor_router(state: SreParentState) -> str:
    """决定 Supervisor 执行后的下一步路由。
    
    参数：
        state: 当前父图状态
        
    返回：
        下一步节点名称
    """
    tasks_to_be_executed = state.get("tasks_to_be_executed", [])
    
    if len(tasks_to_be_executed) > 0:
        # supervisor 请求执行更多任务
        logger.info(f"Supervisor Router：回环至 schedule_rca_tasks，任务：{tasks_to_be_executed}")
        return "schedule_rca_tasks"
    else:
        # 没有更多任务，调查结束
        logger.info("Supervisor Router：调查完成，结束工作流。")
        return END


def build_parent_graph():
    """构建并编译完整的 RCA 工作流图。
    
    返回：
        包含全部 Agent 的已编译父图
    """
    builder = StateGraph(SreParentState)

    # 添加 agent 节点
    builder.add_node(
        "triage_agent",
        triage_agent_graph,
        metadata={
            "name": "Triage Agent",
            "description": "聚合遥测数据并提取症状，作为调查起点。"
        },
    )
    builder.add_node(
        "planner_agent",
        planner_agent_graph,
        metadata={
            "name": "Planner Agent",
            "description": "评估症状并为当前事故生成 RCA 任务。"
        },
    )
    builder.add_node(
        "schedule_rca_tasks",
        update_rca_task_status,
        metadata={
            "name": "Schedule RCA Tasks",
            "description": "更新任务执行状态，并选择下一轮 RCA 迭代的工作项。"
        },
    )
    builder.add_node(
        "rca_agent",
        rca_agent_graph,
        metadata={
            "name": "RCA Agent",
            "description": "为每个已调度任务并行执行聚焦式 RCA 工作流。"
        },
    )
    builder.add_node(
        "supervisor_agent",
        supervisor_agent_graph,
        metadata={
            "name": "Supervisor Agent",
            "description": "审阅 RCA 结论，请求补充任务，或输出最终报告。"
        },
    )

    # 构建工作流
    builder.add_edge(START, "triage_agent")
    builder.add_edge("triage_agent", "planner_agent")
    builder.add_edge("planner_agent", "schedule_rca_tasks")

    # 使用 rca_router 动态分发任务到并行 RCA agent
    # 若无任务则跳过并进入 supervisor
    builder.add_conditional_edges(
        "schedule_rca_tasks",
        rca_router,
        ["rca_agent", "supervisor_agent"]
    )

    # RCA 完成后进入 supervisor
    # （rca_analyses_list 会通过 operator.add 自动聚合）
    builder.add_edge("rca_agent", "supervisor_agent")
    
    # 在 supervisor 后添加条件边，用于继续循环或结束
    builder.add_conditional_edges(
        "supervisor_agent",
        supervisor_router,
        {
            "schedule_rca_tasks": "schedule_rca_tasks",
            END: END
        }
    )

    return builder.compile()

parent_graph = build_parent_graph()