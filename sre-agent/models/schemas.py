"""K8s Datagraph RCA 的 Pydantic 数据模型。"""
from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class Symptom(BaseModel):
    """集群中观察到的一条症状（Triage 的输出单元）"""
    # 症状类型/现象描述
    # 例: "Pod CrashLoopBackOff" / "High latency" / "MongoDB authentication failure"
    potential_symptom: str = Field(..., description="观察到的症状类型")
    # 出问题的资源类别：只能是 pod 或 service
    # 例: "pod" 或 "service"
    resource_type: Literal["pod", "service"] = Field(..., description="出现问题的资源类型")
    # 出问题的资源确切名字（不含 namespace、不含多余装饰）
    # 例: "geo-7d9f8c6b5-xk2pq"（pod）或 "rate"（service）
    affected_resource: str = Field(..., description="出现问题的资源精确名称（不含 namespace 或装饰符）")
    # 支撑该症状判断的证据（来自指标/日志/链路等）
    # 例: "Prometheus: error rate >5%; Jaeger trace shows 401 Unauthorized calling mongodb-rate"
    evidence: str = Field(..., description="支撑该症状判断的证据")


class SymptomList(BaseModel):
    """症状列表（LLM structured_output 的包装容器）"""
    # 本轮 Triage 识别出的全部症状；无问题时可为 []
    # 例: [Symptom(...), Symptom(...)] 或 []
    symptoms: List[Symptom] = Field(default_factory=list, description="集群中观察到的症状列表")


class RCATask(BaseModel):
    """一条根因调查任务（Planner 的输出单元，交给 RCA Worker 执行）"""
    # 执行优先级/序号；越小通常越先查；Supervisor 回环时也用它点名任务
    # 例: 1, 2, 3
    priority: int = Field(..., description="该 RCA 任务的执行顺序")
    # 任务生命周期：待执行 / 执行中 / 已完成
    # 例: "pending" → "in_progress" → "completed"
    status: Literal["pending", "in_progress", "completed"] = Field(default="pending", description="RCA 任务状态")
    # 本任务要查清什么（调查目标陈述）
    # 例: "Determine why geo pods fail to connect to MongoDB"
    investigation_goal: str = Field(..., description="调查目标")
    # 要调查的目标资源名
    # 例: "geo" 或 "geo-7d9f8c6b5-xk2pq"
    target_resource: str = Field(..., description="待调查的资源名称")
    # 目标资源类型：pod 或 service
    # 例: "service"
    resource_type: Literal["pod", "service"] = Field(..., description="待调查的资源类型")
    # 建议使用的工具名列表（给 RCA Worker 的提示，非强制）
    # 例: ["kubectl_get", "get_logs", "get_traces"]
    suggested_tools: List[str] = Field(default_factory=list, description="建议使用的调查工具列表")


class RCATaskList(BaseModel):
    """RCA 任务列表（LLM structured_output 的包装容器）"""
    # Planner 生成的全部调查任务
    # 例: [RCATask(priority=1, ...), RCATask(priority=2, ...)]
    rca_tasks: List[RCATask] = Field(default_factory=list, description="待执行的 RCA 任务列表")


class RCAAgentExplaination(BaseModel):
    """RCA Worker 调查结束后的步骤与洞见汇总"""
    # 按时间顺序的调查动作/分析步骤
    # 例: ["Checked pod status via kubectl_get", "Fetched logs showing auth error", "Submitted diagnosis"]
    steps: List[str] = Field(..., description="调查过程中按时间顺序执行的全部动作或分析")
    # 调查过程中提炼出的关键发现
    # 例: ["MongoDB admin user missing", "geo service restart count increasing"]
    insights: List[str] = Field(..., description="调查过程中发现的关键结论或洞见")


class FinalReport(BaseModel):
    """Supervisor 产出的最终诊断报告"""
    # 认定的根因描述
    # 例: "geo service MongoDB admin user was deleted, causing DB connection failures"
    root_cause: str = Field(..., description="识别出的事故根因")
    # 受本次事故影响的资源列表
    # 例: ["geo", "frontend"]
    affected_resources: List[str] = Field(..., description="受事故影响的所有资源")
    # 各 RCA Worker 证据的汇总摘要
    # 例: "Logs show authentication failed; pod restarts correlate with DB errors"
    evidence_summary: str = Field(..., description="各 RCA Worker 证据的汇总")
    # 整个调查过程与发现的概述
    # 例: "Investigated geo and rate services; confirmed DB auth failure on geo only"
    investigation_summary: str = Field(..., description="调查过程与发现的概述")
    # 是否检测到集群存在问题（对应评测 Detection）
    # 例: True（有故障）/ False（无故障场景）
    detection: bool = Field(..., description="是否检测到集群存在问题")
    # 定位到的故障组件（服务名列表）；无则可为 None（对应评测 Localization）
    # 例: ["geo"] 或 None
    localization: Optional[List[str]] = Field(
        None,
        description="定位到的故障组件列表（如服务名），无则可为空"
    )

class SupervisorDecision(BaseModel):
    """Supervisor 的二选一决策：结案 或 要求继续调查"""
    # 下一轮要执行的任务 priority 列表；仅在证据不足、调查未完成时填写
    # 例（继续查）: [2, 5] ；例（结案）: []
    tasks_to_be_executed: List[int] = Field(
        default_factory=list,
        description="下一轮要执行的任务优先级列表；仅在调查未完成且确实需要更多数据时填写"
    )
    # 最终报告；仅在证据充足、调查完成时填写（与上一字段互斥语义）
    # 例（结案）: FinalReport(...) ；例（继续查）: None
    final_report: Optional[FinalReport] = Field(
        default=None,
        description="最终根因报告；仅在调查完成且证据充分时填写"
    )

class EvaluationResult(BaseModel):
    """LLM-as-Judge 对 RCA 诊断质量的评分结果"""
    # 分数 1–5
    # 例: 4
    score: int = Field(..., ge=1, le=5, description="数值评分（1-5）")
    # 极短打分理由（1–2 句）
    # 例: "Root cause matches GT on DB auth failure; missing mention of revoked roles nuance."
    reasoning: str = Field(..., description="极短评分理由（1-2 句）")
