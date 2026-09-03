from models import EvaluationResult
from prompts import EVALUATION_PROMPT
from config import GPT5_1
from utils import get_today_model_usage
import logging
from typing import Optional

GPT5_1_NAME = "gpt-5-2025-08-07"
GPT5_1_TOKEN_DAILY_LIMIT = 240_000

logger = logging.getLogger(__name__)

def evaluate_detection(fault_scenario: dict, detection: bool)->bool:
    # 判断是否存在故障
    """
    评估 detection 结果是否与故障场景 Ground Truth 一致。

    参数：
        fault_scenario: 故障场景字典，含 target 字段
        detection: 待评估的 detection 结果

    返回：
        bool: 是否与 Ground Truth 一致
    """
    target = fault_scenario.get("target", None)
    gt_detection = True if target else False
    return gt_detection == detection

def evaluate_localization(fault_scenario: dict, localization: str) -> bool:
    # 判断故障定位是否正确
    """
    评估 localization 是否与故障场景 target 一致。

    参数：
        fault_scenario: 故障场景字典
        localization: 待评估的定位结果

    返回：
        bool: True if the localization matches the ground truth, False otherwise.
    """
    target = fault_scenario.get("target", None)

    # 如果未定义 target（即无故障场景），则在 localization 也为空时返回 True
    if target is None:
        return localization is None or localization == ''

    # 如果 localization 为 None 或不是字符串，则无法匹配
    if not isinstance(localization, str):
        return False

    # 检查 localization 字符串中是否包含 target
    return target in localization

def evaluate_rca_analysis(fault_scenario: dict, rca_analysis: str, langsmith_metadata: Optional[dict] = None) -> tuple[Optional[int], str]:
    # 判断根因分析是否正确
    """
    使用 LLM 评估 RCA 分析质量，返回分数与理由。

    参数：
        fault_scenario: 故障场景字典，含 RCA_gt
        rca_analysis: 待评估的 RCA 分析文本

    返回：
        tuple: (评分或 None, 评分理由)
    """
    token_usage = get_today_model_usage(model_name=GPT5_1_NAME)

    if token_usage["total_tokens"] > GPT5_1_TOKEN_DAILY_LIMIT:
        logger.error("模型 %s 已超过每日 token 限额", GPT5_1_NAME)
        return None, "错误：已超过每日 token 限额"
    
    llm_judge = GPT5_1.with_structured_output(EvaluationResult)
    prompt = EVALUATION_PROMPT.format(
        ground_truth=fault_scenario.get("RCA_gt", ""),
        rca_analysis=rca_analysis
    )
    try:

        config = {
            "run_name" : "LLM as a Judge",
            "tags": ["evaluation"]
        }

        if langsmith_metadata:
            config["metadata"] = langsmith_metadata

        result = llm_judge.invoke(prompt, config) # type: ignore
        score = getattr(result, "score", None)
        explanation = getattr(result, "reasoning", "")
        return score, explanation
    except Exception as e:
        logger.error("LLM 评测失败：%s", str(e))
        return None, f"错误：LLM 评测失败：{str(e)}"
    
def evaluate_experiment(fault_scenario: dict, report: dict)-> dict:
    # report 是实验结果，包含检测、定位和根因分析结果
    agent_conf_name = report.get("agent_configuration_name", "N/A")
    formatted_scenario = f"{fault_scenario.get('scenario')} - {fault_scenario.get('fault_type')}"
    logger.info(
        "正在评测实验，Agent 配置：%s，场景：%s",
        agent_conf_name,
        formatted_scenario
    )
    # llmJudge_metadata 是实验元数据，包含 agent 配置、agent id、场景和故障类型
    # 供后续的 LLM 评估 evaluate_rca_analysis 使用
    llmJudge_metadata = {
        "agent_configuration_name" : report.get("agent_configuration_name"),
        "agent_id" : report.get("agent_id"),
        "scenario" : fault_scenario.get("scenario"),
        "fault_type" : fault_scenario.get("fault_type")
    }

    evaluation = {}

    # detection 是实验结果中的检测结论
    detection = report.get("final_report", {}).get("detection", False)

    # localization 是实验结果中的定位结论
    localization = report.get("final_report", {}).get("localization", [])
    if isinstance(localization, list):
        localization_str = ", ".join(localization)
    else:
        localization_str = ""

    # rca_analtysis 是实验结果中的根因分析结论
    rca_analtysis = report.get("final_report", {}).get("root_cause", "")

    evaluation["detection"] = evaluate_detection(fault_scenario, detection)
    evaluation["localization"] = evaluate_localization(fault_scenario, localization_str)
    evaluation["rca_score"], evaluation["rca_motivation"] = evaluate_rca_analysis(fault_scenario, rca_analtysis, llmJudge_metadata)

    # 返回评估结果
    return evaluation
