"""RCA Worker：执行聚焦式根因分析调查。"""
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import tools_condition, ToolNode
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from models import RcaAgentState, RCAAgentExplaination
from prompts import RCA_SYSTEM_PROMPT, RCA_HUMAN_PROMPT, EXPLAIN_ANALYSIS_PROMPT
from tools import TOOLS, submit_final_diagnosis
from utils import count_tool_calls, count_non_submission_tool_calls, get_system_prompt
from config import GPT5_MINI, settings as config_settings


# 将 MCP 工具与提交工具合并
tools_with_completion = TOOLS + [submit_final_diagnosis]

async def rcaAgent(state: RcaAgentState) -> dict:
    """执行一步 RCA 推理；可能产生工具调用或最终提交。"""

    # 统计工具调用次数（不含 submit_final_diagnosis）
    tool_call_count = count_non_submission_tool_calls(state["messages"])
    
    # 提取任务详情
    task = state["rca_task"]
    suggested_tools_str = ", ".join(task.suggested_tools) if task.suggested_tools else "请自行判断"

    # 构建预算状态提示信息
    budget_status = ""
    max_tool_calls = config_settings.MAX_TOOL_CALLS

    if tool_call_count >= max_tool_calls:
        budget_status = f"""
⚠️ **预算已用尽**：你已调用 {tool_call_count}/{max_tool_calls} 次工具。

你必须立即调用 submit_final_diagnosis，基于已有证据提交最佳结论。
不要再进行任何工具调用。
"""
    elif tool_call_count >= max_tool_calls - 2:
        budget_status = f"""
⚠️ **预算预警**：你已调用 {tool_call_count}/{max_tool_calls} 次工具，请准备提交诊断。
"""

    rca_system_prompt = get_system_prompt(state, "rca_agent", RCA_SYSTEM_PROMPT, state_key="rca_prompts_config") #type: ignore

    system_message = SystemMessage(content=rca_system_prompt)
    human_message = HumanMessage(content=RCA_HUMAN_PROMPT.format(
        app_summary=state["rca_app_summary"],
        target_namespace=state["rca_target_namespace"],
        investigation_goal=task.investigation_goal,
        resource_type=task.resource_type,
        target_resource=task.target_resource,
        suggested_tools=suggested_tools_str,
        investigation_budget=max_tool_calls,
        tool_calls_count=tool_call_count,
        budget_status=budget_status
    ))

    llm_with_completion_tools = GPT5_MINI.bind_tools(tools_with_completion, parallel_tool_calls=True)
    return {"messages": [llm_with_completion_tools.invoke([system_message, human_message] + state["messages"])]}


async def explain_analysis(state: RcaAgentState) -> dict:
    """将调查过程总结为有序步骤与合并洞见。"""
    # 使用具备结构化输出能力的 LLM 做总结
    llm_explain_steps = GPT5_MINI.with_structured_output(RCAAgentExplaination)

    prompt = SystemMessage(content=EXPLAIN_ANALYSIS_PROMPT)

    explaination = llm_explain_steps.invoke([prompt] + state["messages"])

    result = explaination.model_dump() #type: ignore

    return {
        "prev_steps": result["steps"],
        "insights": result["insights"]
    }

async def format_response(state: RcaAgentState) -> dict:
    """打包最终 RCA 输出（任务、洞见、步骤、统计与历史）。"""

    final_report = state["rca_output"]
    
    task = state["rca_task"]
    final_report["task"] = {
        "priority": task.priority,
        "status": "completed",
        "investigation_goal": task.investigation_goal,
        "target_resource": task.target_resource,
        "resource_type": task.resource_type,
        "suggested_tools": task.suggested_tools
    }
    
    final_report["insights"] = state["insights"]
    final_report["steps_performed"] = state["prev_steps"]
    final_report["tools_stats"] = count_tool_calls(state["messages"])
    
    # 将完整消息历史导出为 JSON
    message_history = []
    for msg in state["messages"]:
        message_dict = {
            "type": msg.__class__.__name__,
            "content": msg.content if hasattr(msg, 'content') else str(msg),
        }
        if isinstance(msg, AIMessage) and msg.tool_calls:
            message_dict["tool_calls"] = msg.tool_calls
        message_history.append(message_dict)
    
    final_report["message_history"] = message_history

    return {"rca_analyses_list": [final_report]}


def after_tools_condition(state: RcaAgentState) -> str:
    """决定下一节点：若已有诊断则总结，否则继续循环。"""

    if state.get("rca_output"):
        # 调查已完成，进入总结阶段
        return "explain-analysis"
    return "rca-agent"


def build_rca_graph():
    """构建并编译 RCA Agent 状态图。"""

    builder = StateGraph(RcaAgentState)

    # 添加节点
    builder.add_node("rca-agent", rcaAgent)
    builder.add_node("tools", ToolNode(tools_with_completion))
    builder.add_node("explain-analysis", explain_analysis)
    builder.add_node("format-output", format_response)

    # 添加边
    builder.add_edge(START, "rca-agent")

    # 从 rca-agent 出发的条件边
    builder.add_conditional_edges(
        "rca-agent",
        tools_condition,
    )

    # 工具调用后，决定继续 ReAct 循环还是总结整次分析
    builder.add_conditional_edges(
        "tools",
        after_tools_condition,
        {
            "rca-agent": "rca-agent",
            "explain-analysis": "explain-analysis"
        }
    )
    
    builder.add_edge("explain-analysis", "format-output")

    builder.add_edge("format-output", END)

    # 编译时指定输出键，仅返回分析结果
    return builder.compile().with_config(
        run_name="RCA Agent",
        output_keys=["rca_analyses_list"]
    )


# 导出编译后的图
rca_agent_graph = build_rca_graph()
