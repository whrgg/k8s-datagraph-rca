"""
K8s Datagraph RCA - Kubernetes 微服务根因分析实验入口

单次实验启动脚本，作为多 Agent 工作流的主入口。
详细说明见 README.md
"""

import asyncio
import time
import json
from typing import Optional
from langsmith import Client
import os
from datetime import datetime
import logging
from dotenv import load_dotenv
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)

# 导入编译后的父图
from graph import parent_graph

async def run_sre_agent(
    app_name: str,
    fault_name: str,
    app_summary: str,
    target_namespace: str,
    trace_service_starting_point: str,
    trace_name: Optional[str] = None,
    agent_configuration_name: Optional[str] = None,
    agent_id: Optional[str] = None,
    prompts_config: Optional[dict[str, str]] = None
) -> tuple[dict, float]:
    """执行完整 RCA 工作流。
    
    参数：
        app_name: 被诊断应用名称
        app_summary: 应用架构摘要
        target_namespace: 目标 Kubernetes namespace
        trace_service_starting_point: 链路分析起始服务
        trace_name: 可选的执行 trace 名称
        
    返回：
        (结果字典, 执行耗时秒数)
    """
    
    from graph import SreParentState

    if not prompts_config:
        prompts_config = {}

    initial_state = SreParentState(
        app_name=app_name,
        app_summary=app_summary,
        target_namespace=target_namespace,
        trace_service_starting_point=trace_service_starting_point,
        problematic_pods={},
        slow_traces={},
        problematic_traces={},
        problematic_metrics={},
        tasks_to_be_executed=[],
        symptoms=[],
        rca_tasks=[],
        rca_analyses_list=[],
        final_report={},
        prompts_config=prompts_config
    )

    if not agent_configuration_name:
        agent_configuration_name = "Default"

    if not agent_id:
        agent_id = "Z"
    
    start_time = time.time()

    config = {
        "recursion_limit": 100,
        "metadata": {
            "app_name": app_name,
            "namespace": target_namespace,
            "starting_service": trace_service_starting_point,
            "experiment_name": trace_name or app_name,
            "fault_name" : fault_name,
            "agent_configuration": agent_configuration_name,
            "agent_id" : agent_id,
            "parallel_rca_tasks": os.environ.get("RCA_TASKS_PER_ITERATION","Unknown"),
            "max_tool_calls": os.environ.get("MAX_TOOL_CALLS","Unknown")
        }
    }
    if trace_name:
        config["run_name"] = trace_name  # type: ignore

    result = await parent_graph.ainvoke(initial_state, config) #type: ignore
    
    execution_time = time.time() - start_time
    
    return result, execution_time

def get_experiment_metrics(experiment_name: str, exec_time: float | int) -> dict:
    """
    获取 LangSmith 实验的综合指标。
    
    参数：
        experiment_name: 实验名称
    
    返回：
        含实验 ID、耗时、总 token 及各 Agent token 分布的字典
    """
    langsmith_client = Client()
    
    # 获取实验运行记录，优先按 session 名称搜索
    runs = langsmith_client.list_runs(
    project_name=os.environ.get("LANGSMITH_PROJECT"),
    filter=f'eq(name, "{experiment_name}")',
    limit=1
    )
    
    run = next(iter(runs), None)
    
    if not run:
        return {"error": f"Experiment '{experiment_name}' not found"}
    
    # 计算执行时间
    execution_time = (run.end_time - run.start_time).total_seconds() if run.end_time else exec_time
    
    # 获取所有子运行记录
    child_runs = list(langsmith_client.list_runs(parent_run_id=run.id))
    
    # 按 agent 名称聚合 token 使用情况
    agent_stats = {}
    
    for agent_run in child_runs:
        agent_name = agent_run.name
        
        if agent_name not in agent_stats:
            agent_stats[agent_name] = {
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "runs_count": 0
            }
        
        agent_stats[agent_name]["total_tokens"] += agent_run.total_tokens or 0
        agent_stats[agent_name]["input_tokens"] += (agent_run.input_tokens or 0)
        agent_stats[agent_name]["output_tokens"] += (agent_run.output_tokens or 0)
        agent_stats[agent_name]["cost"] += float((agent_run.completion_cost or 0.0))
        agent_stats[agent_name]["runs_count"] += 1
    
    run_url = getattr(run, "url", None)

    # 构建最终指标字典
    return {
        "run_id": str(run.id),
        "experiment_name": run.name,
        "status": run.status,
        "execution_time_seconds": execution_time,
        "total_tokens": run.total_tokens or 0,
        "total_cost": sum(s["cost"] for s in agent_stats.values()),
        "langsmith_url": run_url,
        "agent_stats": agent_stats
    }

def export_json_results(
        result: dict,
        experiment_name: str,
        exec_time: float | int,
        fault_name: str,
        application_name: str,
        target_namespace: str,
        trace_service_starting_point: str,
        agent_configuration_name: Optional[str] = None,
        agent_id: Optional[str] = None
        ) -> dict:

    export = result

    export["experiment_name"] = experiment_name

    if agent_id:
        export["agent_id"] = agent_id
    
    if agent_configuration_name:
        export["agent_configuration_name"] = agent_configuration_name

    # 将 symptom 的 Pydantic 对象转换为字典
    symptoms = []
    for s in result["symptoms"]:
        symptoms.append(s.model_dump())
    export["symptoms"] = symptoms

    # 将 rca_task 的 Pydantic 对象转换为字典
    rca_tasks = []
    for t in result["rca_tasks"]:
        rca_tasks.append(t.model_dump())
    export["rca_tasks"] = rca_tasks

    export["stats"] = get_experiment_metrics(experiment_name, exec_time)

    testbed = {}
    testbed["application_name"] = application_name,
    testbed["fault_name"] = fault_name
    testbed["target_namespace"] = target_namespace
    testbed["trace_service_starting_point"] = trace_service_starting_point
    # 添加分治参数
    testbed["rca_tasks_per_iteration"] = os.environ.get("RCA_TASKS_PER_ITERATION", "")
    # 添加工具调用预算参数
    testbed["max_tool_calls"] = os.environ.get("MAX_TOOL_CALLS", "")

    export["testbed"] = testbed
    
    return export

async def main():

    load_dotenv(dotenv_path="../.env")

    # 获取实验名称
    experiment_name = input("请输入实验名称（直接回车使用默认）：").strip()
    if not experiment_name:
        experiment_name = "K8s Datagraph RCA Test"

    # 提示输入故障名称（AIOpsLab 实验名）
    fault_name = ""
    while not fault_name:
        fault_name = input("请输入故障名称（AIOpsLab 实验名）：").strip()

    # 提示输入 agent ID
    agent_id = ""
    while not agent_id:
        agent_id = input("请输入 Agent 配置 ID：").strip()
    
    # 应用配置
    app_summary = """
        该应用为酒店预订微服务，基于 Go 与 gRPC 构建，包含内存/持久化数据库、推荐系统与下单能力。
    """
    target_namespace = "test-hotel-reservation"
    service_starting_point = "frontend"
    app_name = "Hotel Reservation"
    
    print(f"\n🚀 启动 K8s Datagraph RCA：{experiment_name}")
    print(f"📦 应用：{app_name}")
    print(f"🎯 命名空间：{target_namespace}")
    print(f"🔍 链路起始服务：{service_starting_point}\n")
    
    # 运行 agent
    result, exec_time = await run_sre_agent(
        app_name=app_name,
        fault_name=fault_name,
        app_summary=app_summary,
        target_namespace=target_namespace,
        trace_service_starting_point=service_starting_point,
        trace_name=experiment_name,
        agent_configuration_name="Plain ReAct",
        agent_id=agent_id,

    )

    # 展示结果
    print(f"\n✅ 分析完成！")
    print(f"⏱️  执行耗时：{exec_time:.2f} 秒\n")
    
    final_report = result.get("final_report", {})
    if final_report:
        print("📋 最终报告：")
        print(f"  根因：{final_report.get('root_cause', 'N/A')}")
        print(f"  受影响资源：{', '.join(final_report.get('affected_resources', []))}")
        print(f"\n  证据摘要：\n  {final_report.get('evidence_summary', 'N/A')}")
    
    # 保存结果
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_experiment_name = experiment_name.replace(" ", "-")
    output_file = f"{date_str}_{safe_experiment_name}.json"

    enriched_result = export_json_results(
        result=result,
        experiment_name=experiment_name,
        exec_time = exec_time,
        fault_name=fault_name,
        application_name=app_name,
        target_namespace=target_namespace,
        trace_service_starting_point=service_starting_point,
        agent_id=agent_id
    )

    output_dir = os.environ.get("RESULTS_PATH", "results")
    output_dir_path = Path(output_dir)
    if not output_dir_path.is_absolute():
        output_dir_path = Path.cwd() / output_dir_path
    output_dir_path.mkdir(parents=True, exist_ok=True)
    output_file_path = output_dir_path / output_file

    with open(output_file_path, "w") as f:
        json.dump(enriched_result, f, indent=2, default=str)
    
    print(f"\n💾 结果已保存至：{output_file_path}")
    
    return result

if __name__ == "__main__":
    asyncio.run(main())