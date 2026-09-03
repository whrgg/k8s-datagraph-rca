"""Supervisor Agent：汇总 RCA 结论并输出最终诊断。"""
import json
from langgraph.graph import START, END, StateGraph
from langchain_core.prompts import ChatPromptTemplate
from models import SupervisorAgentState, SupervisorDecision, FinalReport
from prompts import SUPERVISOR_SYSTEM_PROMPT, SUPERVISOR_HUMAN_PROMPT
from utils import get_system_prompt
from config import GPT5_MINI
import logging

logger = logging.getLogger(__name__)

def supervisor_agent(state: SupervisorAgentState) -> dict:
    """分析全部 RCA 结论并输出最终根因诊断。
    
    参数：
        state: Current supervisor agent state with symptoms and RCA analyses
        
    返回：
        Dictionary with final report
    """
    symptoms = state.get("symptoms", [])
    rca_analyses = state.get("rca_analyses_list", [])
    app_summary = state.get("app_summary", "")
    app_name = state.get("app_name", "")
    rca_tasks = state.get("rca_tasks", [])

    logger.info("Supervisor Agent 正在汇总调查结果并生成最终 RCA 诊断。")
    
    if not rca_analyses and not symptoms:
        return {
            "final_report": FinalReport(
                root_cause="无可用分析数据",
                affected_resources=[],
                evidence_summary="未提供症状或 RCA 分析结果",
                investigation_summary="调查未完成：数据不足",
                detection=False,
                localization=None
            ).model_dump()
        }
    
    # 以 Markdown 形式构建包含全部调查数据的 human prompt
    symptoms_info = ""
    if symptoms:
        symptoms_parts = []
        for i, symptom in enumerate(symptoms, 1):
            symptoms_parts.extend([
                f"## 症状 {i}\n\n",
                f"**类型**：{symptom.potential_symptom}\n\n",
                f"**资源**：`{symptom.affected_resource}`（{symptom.resource_type}）\n\n",
                f"**证据**：{symptom.evidence}\n\n"
            ])
        symptoms_info = "".join(symptoms_parts)
    
    # 添加 RCA 分析结果
    rca_findings_info = ""
    if rca_analyses:
        rca_parts = []
        for analysis in rca_analyses:
            # 为 prompt 创建一个不包含 message_history 的副本
            analysis_for_prompt = {k: v for k, v in analysis.items() if k != 'message_history'}
            rca_parts.extend([
                f"## 调查（优先级 #{analysis['task']['priority']}）\n\n",
                f"```json\n{json.dumps(analysis_for_prompt, indent=2)}\n```\n\n"
            ])
        rca_findings_info = "".join(rca_parts)
    
    # 添加待执行的 RCA 任务
    pending_tasks_info = ""
    if rca_tasks:
        pending_tasks = [task for task in rca_tasks if task.status in ("pending", "in_progress")]
        if not pending_tasks:
            pending_tasks_info = "所有已规划的 RCA 任务均已完成。\n"
        else:
            pending_parts = []
            for task in pending_tasks:
                pending_parts.extend([
                    f"- **优先级 #{task.priority}**：{task.investigation_goal}",
                    f"  - **目标**：{task.resource_type} `{task.target_resource}`",
                    f"  - **建议工具**：{', '.join(task.suggested_tools)}\n"
                ])
            pending_tasks_info = "\n".join(pending_parts)
    
    supervisor_system_prompt = get_system_prompt(state, "supervisor_agent", SUPERVISOR_SYSTEM_PROMPT) #type: ignore
    
    supervisor_prompt_template = ChatPromptTemplate.from_messages(
        [
            ("system", supervisor_system_prompt),
            ("human", SUPERVISOR_HUMAN_PROMPT),
        ]
    )
    # 创建并调用链
    llm_with_decision = GPT5_MINI.with_structured_output(SupervisorDecision)
    supervisor_chain = supervisor_prompt_template | llm_with_decision
    decision = supervisor_chain.invoke({
        "app_name": app_name,
        "app_summary": app_summary,
        "symptoms_info": symptoms_info,
        "rca_findings_info": rca_findings_info,
        "pending_tasks_info": pending_tasks_info
    })

    # 评估决策结果
    if decision.final_report: # type: ignore
        logger.info("Supervisor 决策：调查完成，正在生成最终报告。")
        # 返回最终报告，并清空待执行任务列表
        return {
            "final_report": decision.final_report.model_dump(), # type: ignore
            "tasks_to_be_executed": []
        }
    elif decision.tasks_to_be_executed: # type: ignore
        logger.info(f"Supervisor 决策：调查未完成，请求执行任务：{decision.tasks_to_be_executed}") # type: ignore
        # 返回需要执行的任务，并清空最终报告
        return {
            "final_report": {}, # 确保 final_report 为空
            "tasks_to_be_executed": decision.tasks_to_be_executed # type: ignore
        }
    else:
        # 兜底：如果 LLM 两者都没返回，则视为调查结束
        logger.warning("Supervisor 警告：LLM 未返回有效决策，默认输出不完整报告。")
        final_report = FinalReport(
            root_cause="调查结论不确定",
            affected_resources=[],
            evidence_summary="Supervisor 未能做出明确决策。",
            investigation_summary="未完成",
            detection=False,
            localization=None
        )
        return {"final_report": final_report.model_dump(), "tasks_to_be_executed": []}

def build_supervisor_graph():
    """构建并编译 Supervisor Agent 子图。
    
    返回：
        已编译的 Supervisor Agent 子图
    """
    builder = StateGraph(SupervisorAgentState)
    builder.add_node("supervisor", supervisor_agent)
    builder.add_edge(START, "supervisor")
    builder.add_edge("supervisor", END)
    
    return builder.compile().with_config(run_name="Supervisor Agent")


# 导出编译后的图
supervisor_agent_graph = build_supervisor_graph()
