"""K8s Datagraph RCA 通用辅助函数。"""
from langchain_core.messages import AIMessage
from collections import Counter
from typing import Optional
import logging


logger = logging.getLogger(__name__)


def get_insights_str(state) -> str:
    """返回调查过程中收集的洞见格式化字符串。
    
    参数：
        state: Agent state containing 'insights' list
        
    返回：
        格式化后的洞见字符串
    """
    if len(state["insights"]) > 0:
        return "\n- ".join([""] + state["insights"])
    else:
        return "暂无洞见"


def get_prev_steps_str(state) -> str:
    """返回调查过程中已执行步骤的格式化字符串。
    
    参数：
        state: Agent state containing 'prev_steps' list
        
    返回：
        格式化后的历史步骤字符串
    """
    if len(state["prev_steps"]) > 0:
        return "\n- ".join([""] + state["prev_steps"])
    else:
        return "暂无历史步骤"


def count_tool_calls(messages) -> dict:
    """统计消息历史中的工具调用次数（按工具名）。
    
    参数：
        messages: List of messages from agent state
        
    返回：
        工具名到调用次数的映射
    """
    tool_calls = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            if hasattr(msg, 'additional_kwargs'):
                if "tool_calls" in msg.additional_kwargs:
                    for call in msg.additional_kwargs['tool_calls']:
                        if "function" in call:
                            if "name" in call["function"]:
                                tool_calls.append(call["function"]["name"])

    counts = Counter(tool_calls)
    return dict(counts)


def count_non_submission_tool_calls(messages) -> int:
    """统计工具调用次数（不含 submit_final_diagnosis）。
    
    参数：
        messages: List of messages from agent state
        
    返回：
        工具调用次数（不含提交工具）
    """
    tool_call_count = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, 'additional_kwargs'):
            if "tool_calls" in msg.additional_kwargs:
                for call in msg.additional_kwargs.get('tool_calls', []):
                    if "function" in call:
                        tool_name = call.get("function", {}).get("name", "")
                        if tool_name != "submit_final_diagnosis":
                            tool_call_count += 1
    return tool_call_count


def get_system_prompt(state: dict, agent_name: str, default_prompt: str, state_key: Optional[str] = "prompts_config") -> str:
    """确定使用的 system prompt（默认或配置覆盖）。
    
    参数：
        state: Agent state containing potential 'prompts_config'
        agent_name: Key name for the agent in the config (e.g., 'triage_agent')
        default_prompt: 默认 system prompt
        state_key: 状态中存放 prompt 配置的键，默认 prompts_config
        
    返回：
        选定的 system prompt 字符串
    """
    system_prompt = default_prompt
    prompt_configs = state.get(state_key, {})
    
    if isinstance(prompt_configs, dict):
        custom_prompt = prompt_configs.get(agent_name)
        if custom_prompt:
            system_prompt = custom_prompt
            logger.info(f"使用 {agent_name} 的自定义系统提示词。")
        else:
            logger.info(f"未找到 {agent_name} 的自定义提示词，使用默认提示词。")
    
    return system_prompt
