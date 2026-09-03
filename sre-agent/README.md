# 核心模块说明

本目录包含 K8s Datagraph RCA 多 Agent 系统的完整实现。

## 目录结构

```
sre-agent/
├── graph.py                  # 父图组装、路由与编译
├── langgraph.json            # LangGraph Studio 注册
├── launch_experiment.py      # 单次实验入口
├── automated_experiment.py   # 批量实验入口
├── config/
│   └── settings.py           # 环境变量与运行时配置
├── models/
│   ├── states.py             # LangGraph 状态定义
│   ├── schemas.py            # Pydantic 模型
│   └── reducers.py           # 并行结果归并
├── agents/
│   ├── triage_agent.py       # 症状采集与结构化
│   ├── planner_agent.py      # Datagraph 感知任务规划
│   ├── rca_agent.py          # ReAct + MCP 工具调查
│   └── supervisor_agent.py   # 汇总诊断与反馈回环
├── prompts/                  # 各 Agent 提示词模板
├── tools/
│   ├── mcp_tools.py          # MCP 客户端与工具白名单
│   └── rca_tools.py          # RCA 专用工具
├── utils/                    # 辅助函数
├── evaluation/               # 检测 / 定位 / LLM-Judge
└── experiments_runner/       # 实验编排与场景配置
```

## LangGraph Studio

```bash
cd sre-agent
poetry run langgraph dev
```

图注册见 `langgraph.json`，入口为 `./graph.py:parent_graph`。

## 单次调用

```python
from graph import parent_graph

result = await parent_graph.ainvoke(initial_state)
```

## 关键模块

### `config/settings.py`
- LLM 配置与工具预算（`MAX_TOOL_CALLS`）
- MCP 工具白名单
- Prometheus / Jaeger / Neo4j 连接参数

### `models/states.py`
- `SreParentState`：父图全局状态
- 各子图状态：`TriageAgentState`、`PlannerAgentState`、`RcaAgentState`、`SupervisorAgentState`

### `models/reducers.py`
- `merge_rca_analyses`：并行 RCA 结果按 priority 去重归并

### `agents/`
每个 Agent 导出已编译子图（`*_agent_graph`），由父图挂载为节点。

### `tools/`
- `mcp_tools.py`：MCP 客户端初始化与工具过滤
- `rca_tools.py`：自定义工具（如 `submit_final_diagnosis`）

## 调试单个 Agent

```python
from agents.triage_agent import triage_agent_graph

result = await triage_agent_graph.ainvoke(test_state)
```

## 常见修改点

| 需求 | 修改位置 |
|------|----------|
| 调整提示词 | `prompts/` 对应文件 |
| 修改 Agent 逻辑 | `agents/` 对应文件 |
| 调整工具预算 | `config/settings.py` |
| 新增工具 | `tools/rca_tools.py` |
| 修改调度拓扑 | `graph.py` |
