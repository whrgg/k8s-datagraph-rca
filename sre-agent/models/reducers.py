# RCA 分析结果归并器
def merge_rca_analyses(left: list[dict], right: list[dict]) -> list[dict]:
    """归并 RCA 分析列表，按任务 priority 去重。
    
    参数：
        left: 已有分析结果
        right: 待合并的新分析结果
        
    返回：
        按 priority 去重后的合并列表
    """
    # 构建从优先级到分析结果的映射
    priority_map = {}
    for analysis in left + right:
        if isinstance(analysis, dict):
            task = analysis.get("task", {})
            priority = task.get("priority") if isinstance(task, dict) else None
            if priority is not None:
                priority_map[priority] = analysis
    
    # 按优先级排序后返回
    return [priority_map[p] for p in sorted(priority_map.keys())]