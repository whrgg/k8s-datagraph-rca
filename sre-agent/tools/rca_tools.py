"""RCA 专用工具（含最终诊断提交）。"""
from typing import Annotated
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId


@tool
def submit_final_diagnosis(
    diagnosis: str,
    reasoning: str,
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """调查完成时提交最终诊断。
    
    参数：
        diagnosis: 识别出的问题（不含修复方案）
        reasoning: 诊断背后的推理过程（保持简洁）
        tool_call_id: LangChain 注入的工具调用 ID
    
    返回：
        更新状态并结束工作流的 Command
    """
    final_response = {
        "diagnosis": diagnosis,
        "reasoning": reasoning
    }
    
    return Command(
        update={
            "rca_output": final_response,
            "messages": [
                ToolMessage(
                    content="最终诊断已提交，调查完成。",
                    tool_call_id=tool_call_id
                )
            ]
        },
        goto="format-output"  # 结束 ReAct 循环
    )
