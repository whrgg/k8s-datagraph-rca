"""OpenAI 用量查询工具。"""
from __future__ import annotations

import datetime
import logging
import os
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


def get_today_completions_usage(
    bucket_width: str = "1d",
    raw_output: Optional[bool] = False,
    by_model: bool = False,
) -> Dict[str, int] | Dict[str, Dict[str, int]]:
    """返回今日 completions 端点的组织级用量。

    参数：
        bucket_width: API 聚合桶宽度（如 "1d"、"1h"）。
        raw_output: 为 True 时返回 API 原始 JSON。
        by_model: 为 True 时按模型分组返回用量。

    返回：
        - 默认：含 input_tokens、output_tokens、total_tokens 的字典
        - by_model=True：模型名 -> token 明细 的嵌套字典
    """
    api_key = os.getenv("OPENAI_ADMIN_API_KEY")

    if not api_key:
        logger.error("缺少环境变量 OPENAI_ADMIN_API_KEY。")

    start_dt = datetime.datetime.now(datetime.UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_dt = start_dt + datetime.timedelta(days=1)

    params: list[tuple[str, int | str]] = [
        ("start_time", int(start_dt.timestamp())),
        ("end_time", int(end_dt.timestamp())),
        ("bucket_width", bucket_width),
    ]

    # 如有需要，按模型分组请求数据（API 可能返回按模型聚合后的结果）
    if by_model:
        params.append(("group_by", "model"))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.get(
        "https://api.openai.com/v1/organization/usage/completions",
        params=params,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()
    json_response = response.json()

    if raw_output:
        return json_response

    # 以防御式方式解析结果
    data = json_response.get("data", [])
    if not data:
        # 无数据
        if by_model:
            return {}
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    results = data[0].get("results", [])

    if by_model:
        # 按模型汇总使用量（若有多个 bucket 则累加）
        usage_by_model: Dict[str, Dict[str, int]] = {}
        for r in results:
            model_name = (
                r.get("model")
                or r.get("name")
                or r.get("model_name")
                or "unknown"
            )
            in_toks = int(r.get("input_tokens", 0) or 0)
            out_toks = int(r.get("output_tokens", 0) or 0)
            if model_name not in usage_by_model:
                usage_by_model[model_name] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                }
            usage_by_model[model_name]["input_tokens"] += in_toks
            usage_by_model[model_name]["output_tokens"] += out_toks
            usage_by_model[model_name]["total_tokens"] += in_toks + out_toks
        return usage_by_model

    # 默认行为：若可用则返回聚合后的统计值
    if len(results) > 0:
        input_tokens = int(results[0].get("input_tokens", 0) or 0)
        output_tokens = int(results[0].get("output_tokens", 0) or 0)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

    # 如果没有结果，则返回零使用量
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


def get_today_model_usage(model_name: str, bucket_width: str = "1d") -> Dict[str, int]:
    """返回指定模型今日的 token 用量。

    通过 ``get_today_completions_usage(by_model=True)`` 按模型聚合；
    若模型不存在或 API 无数据，返回全零字典。

    参数：
        model_name: 模型标识（如 "gpt-5-mini"）。
        bucket_width: 聚合桶宽度，默认 "1d"。

    返回：
        含 input_tokens、output_tokens、total_tokens 的字典。
    """
    try:
        usage = get_today_completions_usage(bucket_width=bucket_width, by_model=True)
    except Exception as exc:
        logger.error("获取用量数据失败：%s", exc)
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    if not isinstance(usage, dict):  # Defensive: unexpected type
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    # 允许部分匹配，例如 "gpt-5-mini" 可匹配 "gpt-5-mini-2025-08-07"
    # 对所有命中的 key 做聚合（大小写不敏感的子串匹配）
    target_lower = model_name.lower()
    aggregate = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for key, stats in usage.items():
        if not isinstance(stats, dict):
            continue
        if target_lower in key.lower():
            aggregate["input_tokens"] += int(stats.get("input_tokens", 0) or 0)
            aggregate["output_tokens"] += int(stats.get("output_tokens", 0) or 0)
            aggregate["total_tokens"] += int(stats.get("total_tokens", 0) or 0)

    # 如果没有任何匹配项，则返回零值
    return aggregate

